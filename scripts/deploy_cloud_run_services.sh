#!/usr/bin/env bash
set -euo pipefail

PLAN_ONLY="${PLAN_ONLY:-false}"
SKIP_DEPLOY="${SKIP_DEPLOY:-false}"
SKIP_SMOKE="${SKIP_SMOKE:-false}"

for arg in "$@"; do
  case "$arg" in
    --plan-only|--dry-run)
      PLAN_ONLY=true
      ;;
    --skip-deploy)
      SKIP_DEPLOY=true
      ;;
    --skip-smoke)
      SKIP_SMOKE=true
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      exit 1
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CLOUD_RUN_DIR="$REPO_ROOT/infra/gcp/cloud-run"
REQUIRED_PROJECT_ID="western-pivot-452008-a6"

resolve_env_file() {
  local base_name="$1"
  local local_file="$CLOUD_RUN_DIR/${base_name}.env.local"
  local example_file="$CLOUD_RUN_DIR/${base_name}.env.example"

  if [ -f "$local_file" ]; then
    echo "$local_file"
    return
  fi
  if [ -f "$example_file" ]; then
    echo "$example_file"
    return
  fi

  echo "Missing env file: $local_file or $example_file" >&2
  exit 1
}

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

to_bool() {
  local value="${1:-}"
  local default_value="${2:-false}"
  case "${value,,}" in
    1|true|yes|on) echo "true" ;;
    0|false|no|off) echo "false" ;;
    *) echo "$default_value" ;;
  esac
}

secret_exists() {
  local secret_name="$1"
  gcloud secrets describe "$secret_name" --project "$PROJECT_ID" >/dev/null 2>&1
}

join_env_csv() {
  local csv=""
  for key in "$@"; do
    if [ -n "${!key+x}" ]; then
      if [ -n "$csv" ]; then
        csv+=","
      fi
      csv+="$key=${!key}"
    fi
  done
  echo "$csv"
}

print_non_secret_env() {
  local title="$1"
  shift
  echo ""
  echo "$title"
  for key in "$@"; do
    if [ -n "${!key+x}" ]; then
      echo "  $key=${!key}"
    fi
  done
}

DEPLOY_ENV_FILE="$(resolve_env_file "deploy")"
BACKEND_ENV_FILE="$(resolve_env_file "backend")"
AI_AGENT_ENV_FILE="$(resolve_env_file "ai-agent")"

load_env_file "$DEPLOY_ENV_FILE"
load_env_file "$BACKEND_ENV_FILE"
load_env_file "$AI_AGENT_ENV_FILE"

: "${PROJECT_ID:?PROJECT_ID is required}"
: "${REGION:?REGION is required}"
: "${ARTIFACT_REPOSITORY:?ARTIFACT_REPOSITORY is required}"
: "${IMAGE_TAG:?IMAGE_TAG is required}"
: "${BACKEND_SERVICE_NAME:?BACKEND_SERVICE_NAME is required}"
: "${AI_AGENT_SERVICE_NAME:?AI_AGENT_SERVICE_NAME is required}"
: "${RUNTIME_SERVICE_ACCOUNT:?RUNTIME_SERVICE_ACCOUNT is required}"
: "${BACKEND_IMAGE_NAME:?BACKEND_IMAGE_NAME is required}"
: "${AI_AGENT_IMAGE_NAME:?AI_AGENT_IMAGE_NAME is required}"

if [ "$PROJECT_ID" != "$REQUIRED_PROJECT_ID" ]; then
  echo "PROJECT_ID must be exactly $REQUIRED_PROJECT_ID" >&2
  exit 1
fi

CLOUD_READS_AVAILABLE=true
ACTIVE_PROJECT="$(gcloud config get-value project 2>/dev/null | tr -d '\r' || true)"
if [ -z "$ACTIVE_PROJECT" ]; then
  CLOUD_READS_AVAILABLE=false
  ACTIVE_PROJECT="not verified"
fi
if [ "$CLOUD_READS_AVAILABLE" = true ] && [ "$ACTIVE_PROJECT" != "$PROJECT_ID" ]; then
  echo "Active gcloud project mismatch: expected $PROJECT_ID, got $ACTIVE_PROJECT" >&2
  exit 1
fi
if [ "$CLOUD_READS_AVAILABLE" = false ] && [ "$PLAN_ONLY" != true ]; then
  echo "Active gcloud project could not be verified in this shell environment." >&2
  exit 1
fi

SCHEDULER_VERIFY_COMMAND="gcloud scheduler jobs describe economic-data-pipeline-monthly --location $REGION --project $PROJECT_ID --format=value(state)"
SCHEDULER_STATE="not verified"
if [ "$CLOUD_READS_AVAILABLE" = true ] && scheduler_out=$(gcloud scheduler jobs describe economic-data-pipeline-monthly --location "$REGION" --project "$PROJECT_ID" --format="value(state)" 2>/dev/null); then
  SCHEDULER_STATE="$(echo "$scheduler_out" | tr -d '\r')"
fi

BACKEND_IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$ARTIFACT_REPOSITORY/$BACKEND_IMAGE_NAME:$IMAGE_TAG"
AI_AGENT_IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$ARTIFACT_REPOSITORY/$AI_AGENT_IMAGE_NAME:$IMAGE_TAG"

SECRET_INTERNAL="gov-ai-agent-internal-api-key"
SECRET_GEMINI="gov-ai-gemini-api-key"
SECRET_PARSER_BASE="gov-ai-parser-service-base-url"
SECRET_PARSER_API="gov-ai-parser-service-api-key"

INTERNAL_EXISTS=false
GEMINI_EXISTS=false
PARSER_BASE_EXISTS=false
PARSER_API_EXISTS=false
INTERNAL_STATUS="not verified"
GEMINI_STATUS="not verified"
PARSER_BASE_STATUS="not verified"
PARSER_API_STATUS="not verified"

if [ "$CLOUD_READS_AVAILABLE" = true ]; then
  if secret_exists "$SECRET_INTERNAL"; then INTERNAL_EXISTS=true; INTERNAL_STATUS="present"; else INTERNAL_STATUS="missing"; fi
  if secret_exists "$SECRET_GEMINI"; then GEMINI_EXISTS=true; GEMINI_STATUS="present"; else GEMINI_STATUS="missing"; fi
  if secret_exists "$SECRET_PARSER_BASE"; then PARSER_BASE_EXISTS=true; PARSER_BASE_STATUS="present"; else PARSER_BASE_STATUS="missing"; fi
  if secret_exists "$SECRET_PARSER_API"; then PARSER_API_EXISTS=true; PARSER_API_STATUS="present"; else PARSER_API_STATUS="missing"; fi
fi

ENABLE_GEMINI_BOOL="$(to_bool "${ENABLE_GEMINI:-true}" "true")"
PARSER_REQUIRED_BOOL="$(to_bool "${PARSER_SERVICE_REQUIRED:-false}" "false")"
PARSER_API_KEY_RUNTIME_USED_BOOL="$(to_bool "${PARSER_SERVICE_API_KEY_RUNTIME_USED:-false}" "false")"

BACKEND_NON_SECRET_KEYS=(
  NODE_ENV
  BACKEND_DATA_SOURCE
  BIGQUERY_PROJECT_ID
  BIGQUERY_LOCATION
  BIGQUERY_GOLD_DATASET
  BIGQUERY_ANALYTICS_DATASET
  BIGQUERY_MAX_BYTES_BILLED
  BIGQUERY_CACHE_TTL_SECONDS
  AI_AGENT_BASE_URL
  AI_AGENT_TIMEOUT_MS
)

AI_AGENT_NON_SECRET_KEYS=(
  ENVIRONMENT
  APP_ENV
  PYTHONUNBUFFERED
  AI_AGENT_DATA_SOURCE
  BIGQUERY_PROJECT_ID
  BIGQUERY_LOCATION
  BIGQUERY_GOLD_DATASET
  BIGQUERY_ANALYTICS_DATASET
  BIGQUERY_MAX_BYTES_BILLED
  ENABLE_GEMINI
)

BACKEND_SET_ENV_VARS="$(join_env_csv "${BACKEND_NON_SECRET_KEYS[@]}")"
AI_AGENT_SET_ENV_VARS="$(join_env_csv "${AI_AGENT_NON_SECRET_KEYS[@]}")"

BACKEND_SECRET_BINDINGS=(
  "AI_AGENT_INTERNAL_API_KEY=$SECRET_INTERNAL:latest"
)

AI_AGENT_SECRET_BINDINGS=(
  "INTERNAL_API_KEY=$SECRET_INTERNAL:latest"
  "GEMINI_API_KEY=$SECRET_GEMINI:latest"
)

if [ "$PARSER_BASE_EXISTS" = true ]; then
  AI_AGENT_SECRET_BINDINGS+=("PARSER_SERVICE_BASE_URL=$SECRET_PARSER_BASE:latest")
fi
if [ "$PARSER_API_KEY_RUNTIME_USED_BOOL" = true ] && [ "$PARSER_API_EXISTS" = true ]; then
  AI_AGENT_SECRET_BINDINGS+=("PARSER_SERVICE_API_KEY=$SECRET_PARSER_API:latest")
fi

BACKEND_SET_SECRETS="$(IFS=,; echo "${BACKEND_SECRET_BINDINGS[*]}")"
AI_AGENT_SET_SECRETS="$(IFS=,; echo "${AI_AGENT_SECRET_BINDINGS[*]}")"

echo "=== Cloud Run Deploy Plan (Sanitized) ==="
echo "deploy env file: $DEPLOY_ENV_FILE"
echo "backend env file: $BACKEND_ENV_FILE"
echo "ai-agent env file: $AI_AGENT_ENV_FILE"
echo "project: $PROJECT_ID"
echo "active_project: $ACTIVE_PROJECT"
echo "region: $REGION"
echo "backend_service: $BACKEND_SERVICE_NAME"
echo "ai_agent_service: $AI_AGENT_SERVICE_NAME"
echo "runtime_service_account: $RUNTIME_SERVICE_ACCOUNT"
echo "backend_image: $BACKEND_IMAGE"
echo "ai_agent_image: $AI_AGENT_IMAGE"
echo "scheduler_verify_command: $SCHEDULER_VERIFY_COMMAND"
echo "scheduler_state: $SCHEDULER_STATE"

print_non_secret_env "backend non-secret env (for --set-env-vars)" "${BACKEND_NON_SECRET_KEYS[@]}"
print_non_secret_env "ai-agent non-secret env (for --set-env-vars)" "${AI_AGENT_NON_SECRET_KEYS[@]}"

echo ""
echo "secret existence (name only):"
echo "  $SECRET_INTERNAL: $INTERNAL_STATUS"
echo "  $SECRET_GEMINI: $GEMINI_STATUS"
echo "  $SECRET_PARSER_BASE: $PARSER_BASE_STATUS"
echo "  $SECRET_PARSER_API: $PARSER_API_STATUS"

echo ""
echo "backend --set-secrets:"
for binding in "${BACKEND_SECRET_BINDINGS[@]}"; do
  echo "  $binding"
done
echo "ai-agent --set-secrets:"
for binding in "${AI_AGENT_SECRET_BINDINGS[@]}"; do
  echo "  $binding"
done

echo ""
echo "sanitized commands preview:"
echo "  gcloud run deploy $AI_AGENT_SERVICE_NAME --project $PROJECT_ID --region $REGION --image $AI_AGENT_IMAGE --set-env-vars <non-secret-csv> --set-secrets <secret-names-only>"
echo "  gcloud run deploy $BACKEND_SERVICE_NAME --project $PROJECT_ID --region $REGION --image $BACKEND_IMAGE --set-env-vars <non-secret-csv> --set-secrets <secret-names-only>"

if [ "$PLAN_ONLY" = true ]; then
  echo ""
  echo "Plan mode enabled. No deploy/update/smoke was executed."
  exit 0
fi

if [ "$CLOUD_READS_AVAILABLE" != true ]; then
  echo "Hard stop: cloud checks are unavailable in this shell environment." >&2
  exit 1
fi
if [ "$SCHEDULER_STATE" != "PAUSED" ]; then
  echo "Hard stop: Scheduler state must be PAUSED. Current state: $SCHEDULER_STATE" >&2
  exit 1
fi
if [ "$INTERNAL_EXISTS" != true ]; then
  echo "Hard stop: missing required secret $SECRET_INTERNAL" >&2
  exit 1
fi
if [ "$ENABLE_GEMINI_BOOL" = true ] && [ "$GEMINI_EXISTS" != true ]; then
  echo "Hard stop: ENABLE_GEMINI=true but missing required secret $SECRET_GEMINI" >&2
  exit 1
fi
if [ "$PARSER_REQUIRED_BOOL" = true ] && [ "$PARSER_BASE_EXISTS" != true ]; then
  echo "Hard stop: parser runtime requires $SECRET_PARSER_BASE but it is missing" >&2
  exit 1
fi
if [ "$PARSER_REQUIRED_BOOL" = true ] && [ "$PARSER_API_KEY_RUNTIME_USED_BOOL" = true ] && [ "$PARSER_API_EXISTS" != true ]; then
  echo "Hard stop: parser API key runtime is enabled but secret $SECRET_PARSER_API is missing" >&2
  exit 1
fi

if [ "$SKIP_DEPLOY" = true ]; then
  echo "SkipDeploy=true, deploy step skipped."
  exit 0
fi

gcloud run deploy "$AI_AGENT_SERVICE_NAME" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --platform managed \
  --service-account "$RUNTIME_SERVICE_ACCOUNT" \
  --image "$AI_AGENT_IMAGE" \
  --ingress all \
  --allow-unauthenticated \
  --min-instances 0 \
  --cpu 1 \
  --memory 1Gi \
  --set-env-vars "$AI_AGENT_SET_ENV_VARS" \
  --set-secrets "$AI_AGENT_SET_SECRETS"

AI_AGENT_URL="$(gcloud run services describe "$AI_AGENT_SERVICE_NAME" --region "$REGION" --project "$PROJECT_ID" --format='value(status.url)')"

if [ -z "${AI_AGENT_BASE_URL:-}" ]; then
  AI_AGENT_BASE_URL="$AI_AGENT_URL"
  BACKEND_SET_ENV_VARS="$(join_env_csv "${BACKEND_NON_SECRET_KEYS[@]}")"
fi

gcloud run deploy "$BACKEND_SERVICE_NAME" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --platform managed \
  --service-account "$RUNTIME_SERVICE_ACCOUNT" \
  --image "$BACKEND_IMAGE" \
  --ingress all \
  --allow-unauthenticated \
  --min-instances 0 \
  --cpu 1 \
  --memory 1Gi \
  --set-env-vars "$BACKEND_SET_ENV_VARS" \
  --set-secrets "$BACKEND_SET_SECRETS"

BACKEND_URL="$(gcloud run services describe "$BACKEND_SERVICE_NAME" --region "$REGION" --project "$PROJECT_ID" --format='value(status.url)')"

echo ""
echo "Deploy finished"
echo "ai_agent_url=$AI_AGENT_URL"
echo "backend_url=$BACKEND_URL"

if [ "$SKIP_SMOKE" = true ]; then
  echo "SkipSmoke=true, smoke step skipped."
  exit 0
fi

echo ""
echo "Smoke:"
curl -fsS "$AI_AGENT_URL/health"
echo ""
curl -fsS "$BACKEND_URL/api/v1/ai/health"
echo ""
curl -fsS -X POST "$BACKEND_URL/api/v1/ai/chat" \
  -H "Content-Type: application/json" \
  -d '{"message":"Compare public debt of Vietnam and Thailand from 2010 to 2023","conversationId":"cloud-smoke-phase14b"}'
echo ""
curl -fsS "$BACKEND_URL/api/v1/compare?countries=VNM,THA&indicator=govdebt_GDP&from=2010&to=2023"
echo ""
curl -fsS "$BACKEND_URL/api/v1/countries/AFG/indicators"
echo ""
