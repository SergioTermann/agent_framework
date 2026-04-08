#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -f "$REPO_ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source <(sed '1s/^\xEF\xBB\xBF//' "$REPO_ROOT/.env")
  set +a
fi

MODEL_NAME="${LLM_MODEL:-Qwen/Qwen2.5-1.5B-Instruct}"
HOST="${LLM_HOST:-127.0.0.1}"
PORT="${LLM_PORT:-8000}"

export HF_ENDPOINT="${VLLM_HF_ENDPOINT:-${HF_ENDPOINT:-https://hf-mirror.com}}"
export HF_HUB_DISABLE_XET="${HF_HUB_DISABLE_XET:-1}"

exec "${VLLM_WSL_PYTHON:-/home/kevin/vllm-env/bin/python}" \
  -m vllm.entrypoints.openai.api_server \
  --model "$MODEL_NAME" \
  --host "$HOST" \
  --port "$PORT" \
  --served-model-name "$MODEL_NAME" \
  --tensor-parallel-size "${VLLM_TENSOR_PARALLEL_SIZE:-1}" \
  --gpu-memory-utilization "${VLLM_GPU_MEMORY_UTILIZATION:-0.8}" \
  --max-model-len "${VLLM_MAX_MODEL_LEN:-4096}"
