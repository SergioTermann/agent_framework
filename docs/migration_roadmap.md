# Migration Roadmap

This roadmap converts the current mixed repository into the target architecture
defined in `docs/migration_target_architecture.md`.

## Scope

- move control-plane service layers to Go
- keep AI-plane orchestration in Python
- move hot compute paths to Rust
- keep model-heavy and training-heavy systems in Python
- avoid big-bang rewrites

## Phase Summary

### Phase 0: Freeze boundaries

Deliverables:

- target architecture document
- migration checklist
- no new core service logic added to `web_ui.py`

Exit criteria:

- team agrees on service ownership
- new work uses target boundaries by default

### Phase 1: Gateway and auth to Go

Modules:

- `src/agent_framework/gateway/*`
- `src/agent_framework/core/auth.py`
- `src/agent_framework/api/auth_api.py`
- entry concerns currently in `src/agent_framework/web/web_ui.py`

Deliverables:

- Go gateway owns WS lifecycle and event delivery
- Go auth and RBAC middleware
- Python gateway code becomes compatibility layer only

### Phase 2: Core business APIs to Go

Modules:

- `src/agent_framework/api/application_api.py`
- `src/agent_framework/api/conversation_api.py`
- `src/agent_framework/api/api_key_api.py`
- `src/agent_framework/api/tool_api.py`
- `src/agent_framework/api/webhook_api.py`
- `src/agent_framework/platform/*`

Deliverables:

- `app-go` exposes stable HTTP APIs
- route registration is no longer centered on Flask

### Phase 3: Workflow and task orchestration

Modules:

- control-plane workflow APIs and task scheduling contracts
- `src/agent_framework/api/workflow_advanced_api.py`
- `src/agent_framework/api/visual_workflow_api.py`
- `src/agent_framework/api/async_task_api.py`

Deliverables:

- Go scheduling and workflow metadata layer
- Go task executor becomes first-class backend, not sidecar-only
- AI-bound execution steps stay in Python

### Phase 4: Memory service layer

Modules:

- `src/agent_framework/api/memory_api.py`
- Go-facing memory contracts and persistence-facing pieces
- AI-coupled retrieval and scoring paths remain in Python

Deliverables:

- memory API moved to Go
- Python remains only where model coupling is required

### Phase 4.5: Formalize AI plane in Python

Modules:

- `src/agent_framework/web/unified_orchestrator.py`
- `src/agent_framework/web/context_builder.py`
- `src/agent_framework/api/unified_chat_api.py`
- `src/agent_framework/platform/multi_agent*.py`

Deliverables:

- explicit `ai-python` service boundary
- narrow contracts from Go control plane to Python AI plane
- no further spread of AI orchestration into Go codepaths

### Phase 5: Retrieval kernels to Rust

Modules:

- `src/agent_framework/vector_db/vector_ops.py`
- `src/agent_framework/vector_db/retrieval_core_ops.py`
- `src/agent_framework/vector_db/retrieval_utils.py`

Deliverables:

- Rust owns vector and retrieval kernels
- Python retrieval layer calls Rust through thin adapters

### Phase 6: Causal kernels to Rust

Modules:

- `src/agent_framework/causal/causal_graph_ops.py`
- `src/agent_framework/causal/causal_reasoning_engine.py`
- `src/agent_framework/reasoning/advanced_reasoning_engine.py`

Deliverables:

- causal compute core moved to Rust
- Python keeps orchestration and model-assisted reasoning only

## Suggested 8-Week Plan

### Week 1

- publish target architecture
- freeze `web_ui.py` expansion
- inventory public APIs and WS events

### Week 2

- scaffold `services/gateway-go`, `services/app-go`, and `services/ai-python`
- port auth middleware and JWT verification
- port gateway event models

### Week 3

- move gateway WS connect, heartbeat, ack, and push flows to Go
- keep Python behind compatibility endpoints where needed

### Week 4

- port application, conversation, and API key endpoints to Go
- add contract tests for migrated APIs

### Week 5

- port workflow API shell and task submission paths
- switch async task API to Go-first path
- keep AI execution nodes in Python

### Week 6

- port memory business API to Go
- keep backend-specific adapters in Python until contracts stabilize

### Week 6.5

- isolate `ai-python` contracts for unified chat and multi-agent flows
- define HTTP or RPC boundaries from Go to Python

### Week 7

- move retrieval kernels to Rust
- replace Python hotspots with Rust-backed adapters

### Week 8

- move causal kernels to Rust
- remove dead compatibility paths
- update deploy flow and docs

## File-Level First Batch

The first migration batch should start with these files:

- `src/agent_framework/web/web_ui.py`
- `src/agent_framework/gateway/api.py`
- `src/agent_framework/gateway/service.py`
- `src/agent_framework/gateway/socketio_gateway.py`
- `src/agent_framework/gateway/storage.py`
- `src/agent_framework/core/auth.py`
- `src/agent_framework/api/auth_api.py`
- `src/agent_framework/api/conversation_api.py`
- `src/agent_framework/api/application_api.py`
- `src/agent_framework/api/api_key_api.py`

The first batch should explicitly exclude these AI-plane modules from a Go
rewrite:

- `src/agent_framework/web/unified_orchestrator.py`
- `src/agent_framework/web/context_builder.py`
- `src/agent_framework/api/unified_chat_api.py`
- `src/agent_framework/platform/multi_agent.py`
- `src/agent_framework/platform/multi_agent_impl.py`

## Definition of Done Per Module

For a module to count as migrated:

1. public traffic no longer depends on the old Python entrypoint
2. tests cover the new service contract
3. old endpoint is removed or clearly marked compatibility-only
4. docs and deploy scripts reference the new owner

## Risks

- copying behavior without first freezing contracts
- migrating model-heavy code to Go without payoff
- migrating AI orchestration to Go and losing iteration speed
- re-implementing Rust kernels in Go
- leaving both old and new paths writable for too long

## Non-Goals

- immediate frontend rewrite
- immediate removal of all Python code
- rewriting unified chat and context assembly in Go
- rewriting model-serving and RLHF stacks in Go or Rust
