(function () {
  const state = {
    socket: null,
    connected: false,
    connectionId: '',
    namespace: '/gateway',
  };

  const el = (id) => document.getElementById(id);
  const statusEl = el('gatewayStatus');
  const logEl = el('gatewayLog');
  const tokenInput = el('gatewayToken');
  const userIdInput = el('gatewayUserId');
  const deviceIdInput = el('gatewayDeviceId');
  const namespaceInput = el('gatewayNamespace');
  const messageInput = el('gatewayMessage');
  const pushUserInput = el('pushUserId');
  const pushEventInput = el('pushEvent');
  const pushPayloadInput = el('pushPayload');

  function appendLog(type, message, data) {
    const row = document.createElement('div');
    row.className = `log-item ${type || 'info'}`;
    const now = new Date().toLocaleTimeString('zh-CN');
    const payload = data ? `\n${JSON.stringify(data, null, 2)}` : '';
    row.textContent = `[${now}] ${message}${payload}`;
    logEl.prepend(row);
  }

  function setStatus(text, tone) {
    statusEl.textContent = text;
    statusEl.dataset.tone = tone || 'idle';
  }

  function getAuthPayload() {
    const payload = {
      device_id: (deviceIdInput.value || '').trim(),
    };
    const token = (tokenInput.value || '').trim();
    const userId = (userIdInput.value || '').trim();
    if (token) payload.token = token;
    if (userId) payload.user_id = userId;
    return payload;
  }

  function connectGateway() {
    if (typeof window.io !== 'function') {
      appendLog('error', 'Socket.IO 客户端未加载，无法建立 Gateway 连接');
      return;
    }
    disconnectGateway();
    state.namespace = (namespaceInput.value || '/gateway').trim() || '/gateway';
    const auth = getAuthPayload();
    state.socket = window.io(state.namespace, {
      auth,
      transports: ['websocket', 'polling'],
    });

    state.socket.on('connect', () => {
      state.connected = true;
      setStatus(`已连接 ${state.namespace}`, 'ok');
      appendLog('success', 'Gateway 已连接', { sid: state.socket.id, namespace: state.namespace });
    });

    state.socket.on('disconnect', (reason) => {
      state.connected = false;
      state.connectionId = '';
      setStatus(`连接已断开：${reason}`, 'warn');
      appendLog('warn', 'Gateway 连接断开', { reason });
    });

    state.socket.on('gateway.connected', (payload) => {
      state.connectionId = payload.connectionId || '';
      setStatus(`在线：${payload.userId} @ ${payload.nodeId}`, 'ok');
      appendLog('success', 'Gateway 鉴权完成', payload);
    });

    state.socket.on('gateway.error', (payload) => {
      appendLog('error', 'Gateway 返回错误', payload);
      setStatus(payload?.error || '网关错误', 'error');
    });

    state.socket.on('gateway.heartbeat.ok', (payload) => {
      appendLog('info', '心跳已确认', payload);
    });

    state.socket.on('chat.message', (payload) => {
      appendLog('success', '收到 chat.message', payload);
      if (payload?.ackId) {
        state.socket.emit('message.ack', { ackId: payload.ackId, source: 'gateway-demo' });
      }
    });

    state.socket.on('notify.system', (payload) => {
      appendLog('success', '收到 notify.system', payload);
      if (payload?.ackId) {
        state.socket.emit('message.ack', { ackId: payload.ackId, source: 'gateway-demo' });
      }
    });

    state.socket.on('request.accepted', (payload) => appendLog('info', 'chat.send 已受理', payload));
    state.socket.on('chat.completed', (payload) => appendLog('success', 'chat.send 已完成', payload));
    state.socket.on('chat.error', (payload) => appendLog('error', 'chat.send 失败', payload));
    state.socket.on('message.ack.ok', (payload) => appendLog('info', 'ACK 已落库', payload));
  }

  function disconnectGateway() {
    if (state.socket) {
      state.socket.disconnect();
      state.socket = null;
    }
    state.connected = false;
  }

  function sendHeartbeat() {
    if (!state.socket || !state.connected) {
      appendLog('warn', '尚未连接 Gateway');
      return;
    }
    state.socket.emit('gateway.heartbeat', { source: 'gateway-demo' });
  }

  function sendChat() {
    if (!state.socket || !state.connected) {
      appendLog('warn', '尚未连接 Gateway');
      return;
    }
    const message = (messageInput.value || '').trim();
    if (!message) {
      appendLog('warn', '请输入聊天消息');
      return;
    }
    state.socket.emit('chat.send', {
      message,
      metadata: {
        source: 'gateway-demo',
        assistant_profile: 'wind_maintenance',
      },
      delivery: {
        target: 'CONNECTION',
        event: 'chat.message',
      },
    });
    appendLog('info', '已发送 chat.send', { message });
  }

  async function pushEvent() {
    const userId = (pushUserInput.value || userIdInput.value || '').trim();
    if (!userId) {
      appendLog('warn', '请输入推送目标 user_id');
      return;
    }
    let payload = {};
    try {
      payload = JSON.parse((pushPayloadInput.value || '{}').trim() || '{}');
    } catch (error) {
      appendLog('error', '推送 payload 不是合法 JSON', { error: String(error) });
      return;
    }
    const event = (pushEventInput.value || 'notify.system').trim() || 'notify.system';
    const response = await fetch('/api/gateway/push', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: userId,
        event,
        target: 'ALL',
        payload,
      }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.success) {
      appendLog('error', '主动推送失败', data);
      return;
    }
    appendLog('success', '主动推送成功', data.data);
  }

  el('connectGatewayBtn').addEventListener('click', connectGateway);
  el('disconnectGatewayBtn').addEventListener('click', disconnectGateway);
  el('heartbeatBtn').addEventListener('click', sendHeartbeat);
  el('sendChatBtn').addEventListener('click', sendChat);
  el('pushEventBtn').addEventListener('click', pushEvent);
  el('clearLogBtn').addEventListener('click', () => {
    logEl.innerHTML = '';
  });

  setStatus('尚未连接', 'idle');
})();
