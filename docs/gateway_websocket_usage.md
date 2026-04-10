# Gateway WebSocket 使用说明

## 页面联调入口

- Namespace：`/gateway`
- 已接入页面：
  - `GET /maintenance-assistant`
  - `GET /dev/assistant`

以上两个页面现在会优先通过 Gateway 的 `chat.send` 发起诊断；如果 Gateway 不可用，则自动回退到 `POST /api/unified/chat`。

## 连接方式

优先使用 JWT：

```js
const socket = io('/gateway', {
  auth: {
    token: 'Bearer 对应登录返回 token',
    device_id: 'web-001'
  }
})
```

开发联调阶段也支持：

```js
const socket = io('/gateway', {
  auth: {
    user_id: 'u1001',
    device_id: 'web-001'
  }
})
```

## 客户端发送事件

### 心跳

```js
socket.emit('gateway.heartbeat', { source: 'web-client' })
```

### 发送聊天请求

```js
socket.emit('chat.send', {
  message: '帮我分析机组偏航超差告警',
  metadata: {
    assistant_profile: 'wind_maintenance'
  },
  delivery: {
    target: 'CONNECTION',
    event: 'chat.message'
  }
})
```

### ACK

```js
socket.emit('message.ack', {
  ackId: payload.ackId
})
```

## 服务端返回事件

- `gateway.connected`
- `gateway.heartbeat.ok`
- `chat.message`
- `chat.completed`
- `chat.error`
- `notify.system`
- `message.ack.ok`
- `gateway.error`

## 主动推送接口

```http
POST /api/gateway/push
Content-Type: application/json
```

```json
{
  "user_id": "u1001",
  "event": "notify.system",
  "target": "ALL",
  "payload": {
    "title": "任务完成",
    "content": "AI 诊断已完成"
  }
}
```

## 查询接口

- `GET /api/gateway/nodes`
- `GET /api/gateway/online-users`
- `GET /api/gateway/users/<user_id>/connections`
- `GET /api/gateway/users/<user_id>/offline-events`
- `GET /api/gateway/events/<event_id>`

## 当前实现说明

- 在线用户、连接、事件、投递状态持久化到 `gateway.db`
- 用户离线时事件转为 `PENDING_OFFLINE`
- 用户重新连接后自动补发离线事件
- 客户端 ACK 后事件状态更新为 `ACKED`
