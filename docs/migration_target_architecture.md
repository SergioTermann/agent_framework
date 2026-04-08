# Migration Target Architecture

This document defines the target repository layout for the staged migration
from the current mixed Python-first codebase to a clearer service-oriented
layout:

- Go owns the control plane: gateway, auth, stable CRUD APIs, persistence-
  facing service logic, scheduling, and operational endpoints.
- Python owns the AI plane: agent orchestration, context building, RAG
  composition, multi-agent coordination, and model-facing adapters.
- Rust owns performance-critical compute kernels.
- Frontend assets are isolated from backend services.

## Target Layout

```text
agent_framework/
|- services/
|  |- gateway-go/
|  |- app-go/
|  |- task-executor-go/
|  |- ai-python/
|  |- model-python/
|  `- retrieval-python/
|- crates/
|  |- vector-core/
|  |- retrieval-core/
|  |- causal-core/
|  `- ws-core/
|- frontend/
|  |- templates/
|  |- static/
|  `- optional-spa/
|- shared/
|  |- api-schemas/
|  |- event-schemas/
|  |- config/
|  `- openapi/
|- deploy/
|- docs/
`- scripts/
```

## Current To Target Mapping

### Move to `services/gateway-go`

Current sources:

- `go_services/gateway/*`
- `src/agent_framework/gateway/*`

Target responsibilities:

- edge routing
- JWT auth verification
- WS connection lifecycle
- event delivery and ack
- reverse proxy and static delivery

### Move to `services/app-go`

Current sources:

- `src/agent_framework/api/*`
- `src/agent_framework/core/auth.py`
- selected persistence-facing modules from `src/agent_framework/platform/*`
- selected non-AI workflow metadata modules from `src/agent_framework/workflow/*`

Target responsibilities:

- business APIs
- auth and RBAC
- applications and publishing
- workflow metadata and scheduling contracts
- conversation persistence contracts
- memory service contracts
- monitoring, webhook, and tool endpoints

### Move to `services/ai-python`

Current sources:

- `src/agent_framework/web/unified_orchestrator.py`
- `src/agent_framework/web/context_builder.py`
- `src/agent_framework/web/conversation_manager*.py`
- `src/agent_framework/api/unified_chat_api.py`
- `src/agent_framework/platform/multi_agent*.py`
- AI-coupled modules from `src/agent_framework/workflow/*`
- AI-coupled modules from `src/agent_framework/memory/*`

Target responsibilities:

- agent orchestration
- context assembly and retrieval composition
- multi-agent coordination
- model routing and feedback loops
- AI-heavy workflow execution steps

### Move to `services/task-executor-go`

Current sources:

- `go_services/task_executor/*`
- `src/agent_framework/infra/go_task_client.py`

Target responsibilities:

- async task queue
- worker lifecycle
- task status and metrics

### Keep in Python under `services/model-python`

Current sources:

- `src/agent_framework/reasoning/model_serving.py`
- `src/agent_framework/reasoning/rerank_server.py`
- `src/agent_framework/reasoning/llm_rlhf_engine.py`
- `src/agent_framework/reasoning/rl_engine.py`
- `src/agent_framework/web/multimodal_processor.py`

Target responsibilities:

- model serving
- training and RLHF
- multimodal inference
- model-specific adapters

### Keep in Python under `services/retrieval-python`

Current sources:

- `src/agent_framework/vector_db/knowledge_base.py`
- `src/agent_framework/vector_db/rag.py`
- `src/agent_framework/vector_db/rag_agent.py`

Target responsibilities:

- RAG orchestration
- knowledge base adapters
- retrieval pipelines that still depend on Python model tooling

### Move compute kernels to `crates/*`

Current sources:

- `rust_extensions/vector_core/*`
- `rust_extensions/retrieval_core/*`
- `rust_extensions/causal_core/*`
- `rust_extensions/ws_server/*`

Python modules to thin out over time:

- `src/agent_framework/vector_db/vector_ops.py`
- `src/agent_framework/vector_db/retrieval_core_ops.py`
- `src/agent_framework/causal/causal_graph_ops.py`

Target responsibilities:

- vector math
- tokenization and retrieval kernels
- causal graph kernels
- optional high-throughput WS primitives

### Move UI assets to `frontend/*`

Current sources:

- `src/agent_framework/templates/*`
- `src/agent_framework/static/*`

Target responsibilities:

- templates and static assets
- optional future SPA without coupling it to backend source trees

## Service Boundaries

### `gateway-go`

Should not own domain business logic. It should call `app-go` or proxy to
Python services when required.

### `app-go`

Owns stable business contracts and persistence-facing service logic.

### `ai-python`

Owns AI orchestration, prompt assembly, retrieval composition, and all flows
that are tightly coupled to model behavior.

### `model-python`

Owns model runtime concerns only. It should expose narrow RPC or HTTP contracts.

### `retrieval-python`

Owns retrieval composition until those flows can be safely split further.

### `crates/*`

Own pure compute and performance-sensitive logic. No business rules.

## Migration Rules

1. Do not add new Flask endpoints in `src/agent_framework/web/web_ui.py`.
2. Do not add new business logic to `src/agent_framework/gateway/*`.
3. Do not move AI orchestration to Go unless the model coupling has first been
   removed from the module.
4. New service code should prefer the target directories above.
5. Python should call Rust for kernels, not re-implement them again.
6. Go should own public API contracts once a module is migrated.
