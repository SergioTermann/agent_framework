# gateway-go

Target owner:

- edge HTTP entrypoint
- WebSocket lifecycle
- event push and ack
- auth middleware
- reverse proxy concerns

Current sources to absorb:

- `go_services/gateway/*`
- `src/agent_framework/gateway/*`

Implemented now:

- gateway control-plane HTTP routes in Go
- connection registry and online-user queries
- file-backed gateway state persistence
- delivery tracking and event ack state transitions
- optional JWT auth compatible with `services/app-go`

Current routes:

- `GET /api/gateway/nodes`
- `GET /api/gateway/online-users`
- `GET /api/gateway/users/{user_id}/connections`
- `GET /api/gateway/users/{user_id}/offline-events`
- `GET /api/gateway/events/{event_id}`
- `POST /api/gateway/events/{event_id}/ack`
- `POST /api/gateway/push`
- `POST /api/gateway/connections`
- `POST /api/gateway/connections/{connection_id}/replay-pending`
- `DELETE /api/gateway/connections/{connection_id}`
- `POST /api/gateway/connections/{connection_id}/heartbeat`
- `GET /api/v1/gateway/nodes`
- `GET /api/v1/gateway/online-users`
- `GET /api/v1/gateway/users/{user_id}/connections`
- `GET /api/v1/gateway/users/{user_id}/offline-events`
- `GET /api/v1/gateway/events/{event_id}`
- `POST /api/v1/gateway/events/{event_id}/ack`
- `POST /api/v1/gateway/push`
- `POST /api/v1/gateway/connections`
- `POST /api/v1/gateway/connections/{connection_id}/replay-pending`
- `DELETE /api/v1/gateway/connections/{connection_id}`
- `POST /api/v1/gateway/connections/{connection_id}/heartbeat`

Auth knobs:

- `GATEWAY_REQUIRE_AUTH=true` enables JWT validation on gateway routes
- `GATEWAY_AUTH_SECRET` overrides the shared signing secret
- `GATEWAY_GO_STORE_PATH` overrides the gateway state snapshot path
- `GATEWAY_GO_OFFLINE_RETENTION` controls how long offline connections are kept in snapshots
- `GATEWAY_GO_COMPLETED_RETENTION` controls how long delivered/acked events are kept in snapshots
- fallback secret resolution order:
  `GATEWAY_AUTH_SECRET` -> `APP_AUTH_SECRET` -> `JWT_SECRET_KEY` -> `SECRET_KEY`

Incremental cutover:

- keep WebSocket and AI orchestration in Python
- set `GATEWAY_CONTROL_PLANE=go` in Flask to proxy legacy `/api/gateway/*` HTTP routes to `gateway-go`
- set `GATEWAY_CONTROL_PLANE_URL=http://127.0.0.1:7000` or another sidecar address
- in `GATEWAY_CONTROL_PLANE=go` mode, Python gateway persistence is disabled and control-plane state stays in `gateway-go`
- use `python start_app.py --with-go-control-plane` for local sidecar startup
