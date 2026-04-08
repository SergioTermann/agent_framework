# ReMe Memory Sidecar

This project supports multiple memory backends behind the existing `MemoryManager` API:

- `local`: current SQLite/vector-store path
- `reme`: Alibaba ReMe, recommended in an isolated sidecar process
- `viking`: ByteDance OpenViking / VikingDB

## Why Sidecar

`ReMe` can pull in dependency versions that are awkward to mix into the main app environment. The sidecar mode keeps `ReMe` in a dedicated virtual environment and lets the main app talk to it over HTTP.

## ReMe Setup

1. Create or reuse the dedicated venv:

```powershell
python -m venv .venv_reme_memory
python -m pip --python .\.venv_reme_memory\Scripts\python.exe install --disable-pip-version-check --no-input reme-ai agentscope
```

2. Configure `.env`:

```env
MEMORY_BACKEND=reme
MEMORY_BACKEND_FALLBACK=true
REME_SIDECAR_ENABLED=true
REME_SIDECAR_AUTO_START=true
REME_SIDECAR_BASE_URL=http://127.0.0.1:8765
REME_SIDECAR_HOST=127.0.0.1
REME_SIDECAR_PORT=8765
REME_SIDECAR_VENV=.venv_reme_memory
REME_SIDECAR_WORKDIR=.reme-sidecar
REME_SIDECAR_TIMEOUT=45
REME_SIDECAR_REQUEST_TIMEOUT=10
```

3. If ReMe needs separate model credentials, set them too:

```env
REME_LLM_API_KEY=...
REME_LLM_BASE_URL=...
REME_EMBEDDING_API_KEY=...
REME_EMBEDDING_BASE_URL=...
```

If `REME_*` is omitted, the sidecar falls back to the project's existing OpenAI-compatible settings:

- `LLM_API_KEY`
- `LLM_BASE_URL`
- `OPENAI_API_KEY`
- `SILICONFLOW_API_KEY`
- `BASE_URL`

For `LLM_PROVIDER=vllm`, do not assume the chat endpoint can also serve embeddings. In that case, set one of these explicitly:

- `REME_EMBEDDING_BASE_URL`
- `EMBEDDING_BASE_URL`

If your embedding model requires an explicit vector size, set `REME_EMBEDDING_DIMENSIONS` to the actual output dimension. Otherwise leave it unset and let ReMe use the embedding model's native size.

4. Start the sidecar manually if you do not want lazy auto-start:

```powershell
python start_reme_memory.py
```

## Runtime Behavior

- Backend selection is resolved by `resolve_memory_backend(...)`.
- If `MEMORY_BACKEND=reme` and the sidecar venv exists, the app activates the ReMe proxy path.
- If initialization fails and `MEMORY_BACKEND_FALLBACK=true`, the app falls back to `local`.
- Current backend state is exposed at `GET /api/memory/backend`.

## Health Check

```powershell
Invoke-RestMethod http://127.0.0.1:8765/health
```

Expected response:

```json
{"success":true,"status":"ok"}
```

## Viking Setup

If you want to switch to ByteDance OpenViking / VikingDB instead:

```env
MEMORY_BACKEND=viking
MEMORY_BACKEND_FALLBACK=true
VIKING_ENABLED=true
VIKING_HOST=api-knowledgebase.mlp.cn-beijing.volces.com
VIKING_REGION=cn-beijing
VIKING_ACCESS_KEY=...
VIKING_SECRET_KEY=...
VIKING_SCHEME=http
VIKING_TIMEOUT=30
```

The project will probe Viking availability and use the existing local backend as fallback when credentials or SDK support are missing.
