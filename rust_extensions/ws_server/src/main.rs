use axum::{
    extract::{
        ws::{Message, WebSocket, WebSocketUpgrade},
        State,
    },
    response::IntoResponse,
    routing::get,
    Router,
};
use futures_util::{SinkExt, StreamExt};
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use tokio::sync::broadcast;
use tower_http::cors::CorsLayer;
use tracing::{error, info};

#[derive(Clone, Debug, Serialize, Deserialize)]
struct ChatMessage {
    #[serde(rename = "type")]
    msg_type: String,
    content: String,
    session_id: Option<String>,
}

#[derive(Clone)]
struct AppState {
    tx: broadcast::Sender<String>,
}

#[tokio::main]
async fn main() {
    // 初始化日志
    tracing_subscriber::fmt::init();

    // 创建广播通道
    let (tx, _rx) = broadcast::channel::<String>(1000);

    let app_state = AppState { tx };

    // 构建路由
    let app = Router::new()
        .route("/ws", get(ws_handler))
        .route("/health", get(health_handler))
        .layer(CorsLayer::permissive())
        .with_state(Arc::new(app_state));

    // 启动服务器
    let addr = "0.0.0.0:9000";
    info!("WebSocket server listening on {}", addr);

    let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
    axum::serve(listener, app).await.unwrap();
}

async fn health_handler() -> impl IntoResponse {
    "OK"
}

async fn ws_handler(
    ws: WebSocketUpgrade,
    State(state): State<Arc<AppState>>,
) -> impl IntoResponse {
    ws.on_upgrade(|socket| handle_socket(socket, state))
}

async fn handle_socket(socket: WebSocket, state: Arc<AppState>) {
    let (mut sender, mut receiver) = socket.split();

    // 订阅广播通道
    let mut rx = state.tx.subscribe();

    // 发送任务
    let mut send_task = tokio::spawn(async move {
        while let Ok(msg) = rx.recv().await {
            if sender.send(Message::Text(msg)).await.is_err() {
                break;
            }
        }
    });

    // 接收任务
    let tx = state.tx.clone();
    let mut recv_task = tokio::spawn(async move {
        while let Some(Ok(msg)) = receiver.next().await {
            match msg {
                Message::Text(text) => {
                    info!("Received: {}", text);

                    // 解析消息
                    if let Ok(chat_msg) = serde_json::from_str::<ChatMessage>(&text) {
                        match chat_msg.msg_type.as_str() {
                            "assistant_message" => {
                                // 处理助手消息
                                handle_assistant_message(chat_msg, &tx).await;
                            }
                            "start_agent" => {
                                // 处理 Agent 启动
                                handle_start_agent(chat_msg, &tx).await;
                            }
                            _ => {
                                error!("Unknown message type: {}", chat_msg.msg_type);
                            }
                        }
                    }
                }
                Message::Close(_) => {
                    info!("Client disconnected");
                    break;
                }
                _ => {}
            }
        }
    });

    // 等待任务完成
    tokio::select! {
        _ = (&mut send_task) => recv_task.abort(),
        _ = (&mut recv_task) => send_task.abort(),
    }

    info!("WebSocket connection closed");
}

async fn handle_assistant_message(msg: ChatMessage, tx: &broadcast::Sender<String>) {
    // 模拟流式响应
    let response_chunks = vec![
        "这是",
        "一个",
        "流式",
        "响应",
        "的",
        "示例",
    ];

    for chunk in response_chunks {
        let response = serde_json::json!({
            "type": "assistant_stream",
            "chunk": chunk,
            "session_id": msg.session_id
        });

        if let Ok(json) = serde_json::to_string(&response) {
            let _ = tx.send(json);
        }

        // 模拟延迟
        tokio::time::sleep(tokio::time::Duration::from_millis(100)).await;
    }

    // 发送完成信号
    let complete = serde_json::json!({
        "type": "assistant_complete",
        "message": "响应完成",
        "session_id": msg.session_id
    });

    if let Ok(json) = serde_json::to_string(&complete) {
        let _ = tx.send(json);
    }
}

async fn handle_start_agent(msg: ChatMessage, tx: &broadcast::Sender<String>) {
    // 发送会话创建事件
    let session_created = serde_json::json!({
        "type": "session_created",
        "session_id": msg.session_id,
        "status": "queued"
    });

    if let Ok(json) = serde_json::to_string(&session_created) {
        let _ = tx.send(json);
    }

    // 模拟 Agent 执行
    tokio::time::sleep(tokio::time::Duration::from_millis(500)).await;

    // 发送流式输出
    let chunks = vec!["正在", "处理", "您的", "请求", "..."];

    for chunk in chunks {
        let stream = serde_json::json!({
            "type": "stream_chunk",
            "chunk": chunk,
            "session_id": msg.session_id
        });

        if let Ok(json) = serde_json::to_string(&stream) {
            let _ = tx.send(json);
        }

        tokio::time::sleep(tokio::time::Duration::from_millis(100)).await;
    }

    // 发送完成事件
    let completed = serde_json::json!({
        "type": "agent_completed",
        "session_id": msg.session_id,
        "result": "任务完成"
    });

    if let Ok(json) = serde_json::to_string(&completed) {
        let _ = tx.send(json);
    }
}
