(function () {
  const STORAGE_USER_KEY = 'maintenance_gateway_user_id';
  const STORAGE_DEVICE_KEY = 'maintenance_gateway_device_id';
  const STORAGE_TOKEN_KEYS = ['auth_token', 'token', 'jwt_token'];
  const HEARTBEAT_INTERVAL_MS = 30000;
  const REQUEST_TIMEOUT_MS = 120000;

  function randomId(prefix) {
    if (window.crypto && typeof window.crypto.randomUUID === 'function') {
      return `${prefix}${window.crypto.randomUUID()}`;
    }
    return `${prefix}${Date.now()}_${Math.random().toString(16).slice(2)}`;
  }

  function getOrCreateStorageValue(key, prefix) {
    try {
      const existing = window.localStorage.getItem(key);
      if (existing) return existing;
      const created = randomId(prefix);
      window.localStorage.setItem(key, created);
      return created;
    } catch (_error) {
      return randomId(prefix);
    }
  }

  function readToken() {
    try {
      for (const key of STORAGE_TOKEN_KEYS) {
        const value = window.localStorage.getItem(key);
        if (value) return value;
      }
    } catch (_error) {
      return '';
    }
    return '';
  }

  function createBridge() {
    let socket = null;
    let heartbeatTimer = null;
    let connected = false;
    let connectingPromise = null;
    let connectionId = '';
    const pending = new Map();
    const listenersAttached = { value: false };

    function emitStatus(detail) {
      window.dispatchEvent(new CustomEvent('maintenance-gateway-status', { detail }));
    }

    function emitIncoming(detail) {
      window.dispatchEvent(new CustomEvent('maintenance-gateway-event', { detail }));
    }

    function updateStatus(partial) {
      emitStatus({
        connected,
        connectionId,
        namespace: '/gateway',
        ...partial,
      });
    }

    function ensureSocket() {
      if (socket || typeof window.io !== 'function') {
        return socket;
      }
      socket = window.io('/gateway', {
        autoConnect: false,
        transports: ['websocket', 'polling'],
        auth: {
          token: readToken(),
          user_id: getOrCreateStorageValue(STORAGE_USER_KEY, 'maint_user_'),
          device_id: getOrCreateStorageValue(STORAGE_DEVICE_KEY, 'maint_device_'),
        },
      });
      attachListeners();
      return socket;
    }

    function attachListeners() {
      if (!socket || listenersAttached.value) return;
      listenersAttached.value = true;

      socket.on('connect', () => {
        updateStatus({ phase: 'connected_transport', message: 'Gateway 传输层已连接' });
      });

      socket.on('disconnect', (reason) => {
        connected = false;
        connectionId = '';
        stopHeartbeat();
        updateStatus({ phase: 'disconnected', message: `Gateway 已断开：${reason}` });
      });

      socket.on('gateway.connected', (payload) => {
        connected = true;
        connectionId = payload?.connectionId || '';
        startHeartbeat();
        updateStatus({
          phase: 'ready',
          message: `Gateway 已就绪：${payload?.userId || '-'} @ ${payload?.nodeId || '-'}`,
          payload,
        });
      });

      socket.on('gateway.error', (payload) => {
        updateStatus({
          phase: 'error',
          message: payload?.error || 'Gateway 返回错误',
          payload,
        });
      });

      socket.on('gateway.heartbeat.ok', (payload) => {
        emitIncoming({ event: 'gateway.heartbeat.ok', payload });
      });

      socket.on('notify.system', (envelope) => {
        autoAck(envelope);
        emitIncoming({ event: 'notify.system', payload: envelope });
      });

      socket.on('chat.message', (envelope) => {
        autoAck(envelope);
        const data = envelope?.data || {};
        const requestId = data.requestId;
        if (requestId && pending.has(requestId)) {
          const waiter = pending.get(requestId);
          pending.delete(requestId);
          clearTimeout(waiter.timerId);
          waiter.resolve({
            ...data,
            __transport: 'gateway',
            __gateway: {
              traceId: envelope?.traceId,
              ackId: envelope?.ackId,
            },
          });
          return;
        }
        emitIncoming({ event: 'chat.message', payload: envelope });
      });

      socket.on('chat.completed', (payload) => {
        emitIncoming({ event: 'chat.completed', payload });
      });

      socket.on('chat.error', (payload) => {
        const requestId = payload?.requestId;
        if (requestId && pending.has(requestId)) {
          const waiter = pending.get(requestId);
          pending.delete(requestId);
          clearTimeout(waiter.timerId);
          waiter.reject(new Error(payload?.error || 'Gateway chat.send 失败'));
          return;
        }
        emitIncoming({ event: 'chat.error', payload });
      });

      socket.on('message.ack.ok', (payload) => {
        emitIncoming({ event: 'message.ack.ok', payload });
      });
    }

    function startHeartbeat() {
      stopHeartbeat();
      heartbeatTimer = window.setInterval(() => {
        if (socket && connected) {
          socket.emit('gateway.heartbeat', { source: 'maintenance-assistant-ui' });
        }
      }, HEARTBEAT_INTERVAL_MS);
    }

    function stopHeartbeat() {
      if (heartbeatTimer) {
        window.clearInterval(heartbeatTimer);
        heartbeatTimer = null;
      }
    }

    function autoAck(envelope) {
      if (!socket || !connected) return;
      const ackId = envelope?.ackId;
      if (!ackId) return;
      socket.emit('message.ack', {
        ackId,
        source: 'maintenance-assistant-ui',
      });
    }

    async function ensureConnected() {
      if (connected && socket) return socket;
      if (typeof window.io !== 'function') {
        throw new Error('Socket.IO 客户端未加载');
      }
      if (connectingPromise) return connectingPromise;
      const client = ensureSocket();
      connectingPromise = new Promise((resolve, reject) => {
        const timeoutId = window.setTimeout(() => {
          connectingPromise = null;
          reject(new Error('Gateway 连接超时'));
        }, 15000);

        const handleReady = () => {
          window.clearTimeout(timeoutId);
          connectingPromise = null;
          resolve(client);
        };

        const handleFailure = (payload) => {
          window.clearTimeout(timeoutId);
          connectingPromise = null;
          reject(new Error(payload?.error || 'Gateway 连接失败'));
        };

        client.once('gateway.connected', handleReady);
        client.once('gateway.error', handleFailure);
        client.connect();
      });
      return connectingPromise;
    }

    async function sendChatPayload(payload) {
      const client = await ensureConnected();
      const requestId = randomId('req_');
      return new Promise((resolve, reject) => {
        const timerId = window.setTimeout(() => {
          pending.delete(requestId);
          reject(new Error('Gateway chat.send 超时'));
        }, REQUEST_TIMEOUT_MS);

        pending.set(requestId, { resolve, reject, timerId });
        client.emit('chat.send', {
          ...payload,
          requestId,
          delivery: {
            target: 'CONNECTION',
            event: 'chat.message',
          },
        });
      });
    }

    function isAvailable() {
      return typeof window.io === 'function';
    }

    function statusLabel() {
      if (!isAvailable()) return 'Gateway 未加载';
      if (connected) return 'Gateway 在线';
      if (socket && socket.connected) return 'Gateway 传输连接已建立';
      return 'Gateway 待连接';
    }

    updateStatus({
      phase: isAvailable() ? 'idle' : 'unavailable',
      message: statusLabel(),
    });

    return {
      isAvailable,
      ensureConnected,
      sendChatPayload,
      statusLabel,
      getConnectionId: () => connectionId,
      isGatewayPreferred: () => isAvailable(),
    };
  }

  window.MaintenanceAssistantGatewayBridge = createBridge();
})();
