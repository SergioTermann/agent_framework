# Language Ownership Matrix

This document is the optimized language plan for the repository. It answers a
single question: which language should own each kind of problem.

## Decision Rules

### Use Go for control-plane code

Use Go when the module is mostly about:

- auth and RBAC
- stable HTTP APIs
- persistence-facing service logic
- gateway middleware
- connection lifecycle
- scheduling and operational control

### Use Python for AI-plane code

Use Python when the module is mostly about:

- prompt assembly
- context building
- RAG composition
- multi-agent orchestration
- model routing
- model provider adapters
- fast iteration on AI behavior

### Use Rust for compute kernels

Use Rust when the module is mostly about:

- vector math
- retrieval scoring and tokenization
- causal graph kernels
- high-throughput WS primitives
- any hot loop where Python profiling proves a bottleneck

## Ownership By Module

| Module family | Target language | Why |
|---|---|---|
| `src/agent_framework/gateway/*` | Go | edge and realtime control plane |
| `src/agent_framework/core/auth.py` | Go | auth is stable service logic |
| `src/agent_framework/api/auth_api.py` | Go | stable public contract |
| `src/agent_framework/api/application_api.py` | Go | CRUD-heavy service logic |
| `src/agent_framework/api/conversation_api.py` | Go | persistence-facing service logic |
| `src/agent_framework/api/api_key_api.py` | Go | auth and policy surface |
| `src/agent_framework/api/webhook_api.py` | Go | operational API surface |
| `src/agent_framework/web/unified_orchestrator.py` | Python | AI orchestration core |
| `src/agent_framework/web/context_builder.py` | Python | retrieval and prompt assembly |
| `src/agent_framework/api/unified_chat_api.py` | Python | AI-plane entrypoint |
| `src/agent_framework/platform/multi_agent*.py` | Python | model-coupled orchestration |
| `src/agent_framework/reasoning/model_serving.py` | Python | model runtime ecosystem |
| `src/agent_framework/reasoning/llm_rlhf_engine.py` | Python | training and RLHF |
| `src/agent_framework/vector_db/vector_ops.py` | Rust | compute hotspot |
| `src/agent_framework/vector_db/retrieval_core_ops.py` | Rust | retrieval hotspot |
| `src/agent_framework/causal/causal_graph_ops.py` | Rust | causal compute hotspot |

## Anti-Patterns

Do not do these:

- move unified chat orchestration into Go just for language uniformity
- re-implement Rust kernels in Go
- keep adding domain logic into `web_ui.py`
- let both Go and Python own the same public API long-term

## Recommended End State

- Go is the control plane
- Python is the AI plane
- Rust is the compute plane
- Frontend stays separate from backend ownership decisions
