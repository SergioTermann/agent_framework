#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -f "$REPO_ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source <(sed '1s/^\xEF\xBB\xBF//' "$REPO_ROOT/.env")
  set +a
fi

export HF_ENDPOINT="${VLLM_HF_ENDPOINT:-${HF_ENDPOINT:-https://hf-mirror.com}}"
export HF_HUB_DISABLE_XET="${HF_HUB_DISABLE_XET:-1}"

exec "${VLLM_WSL_PYTHON:-/home/kevin/vllm-env/bin/python}" \
  "$REPO_ROOT/start_embedding_api.py" \
  --model "${EMBEDDING_MODEL:-Alibaba-NLP/gte-multilingual-base}" \
  --host "${EMBEDDING_HOST:-127.0.0.1}" \
  --port "${EMBEDDING_PORT:-8001}" \
  --device "${EMBEDDING_DEVICE:-cpu}"
