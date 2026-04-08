# Services

This directory is the target home for runtime services after migration.

- `gateway-go`: edge gateway, WS delivery, auth middleware
- `app-go`: business APIs and orchestration service layer
- `ai-python`: agent orchestration, unified chat, context assembly
- `task-executor-go`: async task execution service
- `model-python`: model serving and training workloads
- `retrieval-python`: RAG orchestration and Python adapters

Current source of truth remains the legacy tree under `src/` and
`go_services/` until code is moved.
