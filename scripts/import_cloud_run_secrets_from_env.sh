#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CLOUD_RUN_DIR="$REPO_ROOT/infra/gcp/cloud-run"

SECRETS_ENV_FILE="${1:-$CLOUD_RUN_DIR/secrets.env.local}"
DEPLOY_ENV_FILE="$CLOUD_RUN_DIR/deploy.env.local"
if [ ! -f "$DEPLOY_ENV_FILE" ]; then
  DEPLOY_ENV_FILE="$CLOUD_RUN_DIR/deploy.env.example"
fi

if [ ! -f "$SECRETS_ENV_FILE" ]; then
  echo "Missing secrets env file: $SECRETS_ENV_FILE" >&2
  exit 1
fi

if [ ! -f "$DEPLOY_ENV_FILE" ]; then
  echo "Missing deploy env file: $DEPLOY_ENV_FILE" >&2
  exit 1
fi

load_env_file() {
  local env_file="$1"
  while IFS= read -r raw_line || [ -n "$raw_line" ]; do
    local line="${raw_line%$'\r'}"
    [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
    [[ "$line" != *"="* ]] && continue
    local key="${line%%=*}"
    local value="${line#*=}"
    key="${key//[[:space:]]/}"
    value="${value#\"}"
    value="${value%\"}"
    value="${value#\'}"
    value="${value%\'}"
    export "$key=$value"
  done < "$env_file"
}

load_env_file "$DEPLOY_ENV_FILE"
load_env_file "$SECRETS_ENV_FILE"

PROJECT_ID="${PROJECT_ID:-}"
if [ -z "$PROJECT_ID" ]; then
  echo "PROJECT_ID is missing from deploy env file" >&2
  exit 1
fi

ACTIVE_PROJECT="$(gcloud config get-value project 2>/dev/null | tr -d '\r')"
if [ "$ACTIVE_PROJECT" != "$PROJECT_ID" ]; then
  echo "Active gcloud project mismatch: expected $PROJECT_ID, got $ACTIVE_PROJECT" >&2
  exit 1
fi

create_or_add_secret() {
  local env_key="$1"
  local secret_name="$2"
  local value="${!env_key:-}"

  if [ -z "$value" ]; then
    echo "skip $secret_name ($env_key is empty)"
    return
  fi

  if ! gcloud secrets describe "$secret_name" --project "$PROJECT_ID" >/dev/null 2>&1; then
    echo "create $secret_name"
    gcloud secrets create "$secret_name" --project "$PROJECT_ID" --replication-policy="automatic" >/dev/null
  fi

  printf '%s' "$value" | gcloud secrets versions add "$secret_name" --project "$PROJECT_ID" --data-file=- >/dev/null
  echo "updated $secret_name (new version added)"
}

create_or_add_secret "GEMINI_API_KEY" "gov-ai-gemini-api-key"
create_or_add_secret "AI_AGENT_INTERNAL_API_KEY" "gov-ai-agent-internal-api-key"
create_or_add_secret "PARSER_SERVICE_BASE_URL" "gov-ai-parser-service-base-url"
create_or_add_secret "PARSER_SERVICE_API_KEY" "gov-ai-parser-service-api-key"

echo "Secret import completed without printing secret values."
