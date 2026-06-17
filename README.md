# Government AI Agent Platform

Cloud-native economic data analytics with a governed natural-language interface.

[Live demo](https://gov-ai-frontend-lnv3c6gztq-as.a.run.app) | [Repository](https://github.com/DataMeowTt/Government-Ai-Agent-Platform)

## Overview

Government AI Agent Platform integrates public economic data, prepares it for analytics, and exposes it through both a dashboard and an AI assistant. The system follows a **BigQuery-direct** architecture: BigQuery is the analytical source of truth for the Backend API and the AI Agent, while Google Cloud Storage preserves raw snapshots and operational evidence.

The platform currently integrates:

- World Bank World Development Indicators (WDI)
- Global Macro Database (GMD)
- FAOSTAT Macro

The demo dataset contains more than **1.16 million raw rows** before normalization. It supports country profiles, indicator comparison, structural clustering, anomaly exploration, data freshness tracking, and natural-language economic questions.

## Key Features

- Multi-source ingestion with source fingerprints, snapshots, manifests, and lineage artifacts
- Layered warehouse design: GCS Bronze and BigQuery Silver, Gold, Analytics, and Ops
- Contract-driven indicators, tables, and data-quality rules
- Dashboard pages for countries, indicators, comparison, clusters, anomalies, and AI chat
- Guarded BigQuery access with table and column allowlists, parameterized inputs, result limits, and query cost limits
- Natural-language parsing into a typed `ParsedQuery` JSON object instead of free-form SQL generation
- Schema, catalog, and safe-to-execute validation before any AI data query
- Read-only AI tools for lookup, comparison, ranking, trends, anomalies, and coverage
- Monthly Google Cloud automation with Scheduler, Workflows, and a Cloud Run Job
- Operational freshness metadata exposed to the frontend

## Architecture

```mermaid
flowchart LR
    subgraph Sources[Official data sources]
        WDI[World Bank WDI]
        GMD[Global Macro Database]
        FAO[FAOSTAT Macro]
    end

    SCH[Cloud Scheduler] --> WF[Google Workflows]
    WF --> ETL[Cloud Run ETL Job]
    Sources --> ETL
    ETL --> BRONZE[GCS Bronze snapshots]
    ETL --> SILVER[BigQuery Silver]
    SILVER --> GOLD[BigQuery Gold]
    GOLD --> ANALYTICS[BigQuery Analytics]
    ETL --> OPS[BigQuery Ops metadata]

    UI[Next.js Dashboard] --> API[NestJS Backend API]
    API --> GOLD
    API --> ANALYTICS
    API --> OPS
    API --> AGENT[FastAPI AI Agent]
    AGENT --> PARSER[Fine-tuned semantic parser]
    AGENT --> GUARD[Schema, catalog, and execution guardrails]
    GUARD --> TOOLS[Read-only BigQuery tools]
    TOOLS --> GOLD
    TOOLS --> ANALYTICS
```

### Main request flows

**Dashboard flow**

```text
User -> Next.js frontend -> NestJS endpoint -> guarded BigQuery query -> table/chart response
```

**AI flow**

```text
Question -> Backend proxy -> AI Agent -> ParsedQuery JSON
         -> schema/catalog/safety checks -> read-only BigQuery tool
         -> grounded answer + table data + chart configuration
```

The AI Agent does not receive permission to write warehouse data or trigger the ETL pipeline.

## Data Platform

### Source scale used by the demo

| Source | Rows | Columns | Source shape |
| --- | ---: | ---: | --- |
| WDI | 403,256 | 70 | World Bank bulk CSV, wide by year |
| FAOSTAT Macro | 708,632 | 13 | Normalized CSV with codebook |
| GMD | 56,864 | 84 | Wide country-year CSV |
| **Total** | **1,168,752** | - | Raw rows before normalization |

### Storage layers

| Layer | Storage | Purpose |
| --- | --- | --- |
| Bronze | Google Cloud Storage | Raw snapshots, manifests, fingerprints, lineage, and recovery evidence |
| Silver | BigQuery `gov_ai_silver` | Normalized long-format records by country, year, indicator, and source |
| Gold | BigQuery `gov_ai_gold` | Curated subject tables for growth, fiscal and monetary data, crisis risk, social welfare, and structural composition |
| Analytics | BigQuery `gov_ai_analytics` | Derived trend, anomaly, residual, and clustering outputs |
| Ops | BigQuery `gov_ai_ops` | Pipeline run metadata, publish status, source state, and freshness |

The shared contracts in [`contracts/`](contracts/) define public indicators, table structure, capabilities, units, mappings, and quality rules. Generated artifacts keep the Python pipeline, TypeScript backend, and AI catalog aligned.

## AI Agent

The semantic parser converts a user question into fields such as:

```json
{
  "intent": "COMPARE_COUNTRIES",
  "indicators": ["govdebt_GDP"],
  "countries": ["VNM", "THA"],
  "start_year": 2010,
  "end_year": 2023,
  "chart_preference": "line",
  "needs_clarification": false
}
```

The parser was fine-tuned from `Qwen/Qwen3-4B-Instruct-2507` with QLoRA/LoRA on a 30,000-example domain dataset covering 27 intents, 151 question families, 88 countries, and 56 indicators.

### Parser evaluation

Results below are from the report's stratified 1,000-example test evaluation.

| Version | Valid JSON | Schema pass | Catalog pass | Exact JSON | Intent accuracy | Indicator F1 | Country F1 | Safe execute |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| v1/v2 | 100.0% | 95.3% | 77.3% | 3.0% | 23.71% | 85.38% | 88.95% | 36.2% |
| v3 | 100.0% | 99.3% | 83.6% | 63.2% | 95.47% | 97.08% | 94.49% | 70.7% |
| v3.1 | 100.0% | 99.3% | 85.8% | 63.2% | 95.47% | 97.08% | 94.49% | 71.7% |

`Safe execute` is intentionally lower than JSON validity because the evaluation set includes incomplete, unsupported, and off-topic questions that should be clarified or rejected instead of executed.

## Application Pages

| Route | Purpose |
| --- | --- |
| `/` | Platform overview and data freshness |
| `/countries` | Search and browse countries |
| `/countries/[code]` | Country profile, indicators, anomalies, and cluster benchmarks |
| `/indicators` | Public indicator catalog and metadata |
| `/compare` | Compare indicators across countries and years |
| `/clusters` | Explore structural country groups |
| `/anomalies` | Filter and inspect statistically unusual observations |
| `/chat` | Ask economic data questions in natural language |

## Technology Stack

| Area | Technologies |
| --- | --- |
| Frontend | Next.js 16, React 19, TypeScript, Tailwind CSS, TanStack Query/Table, Recharts, Zustand, Zod |
| Backend API | NestJS 11, TypeScript, Google Cloud BigQuery client, Axios, TypeORM/PostgreSQL fallback |
| AI Agent | FastAPI, Pydantic, Google Gen AI SDK, BigQuery client, deterministic and Gemini-assisted composers |
| Semantic parser | Qwen3 4B Instruct, QLoRA/LoRA adapter, JSON schema and catalog guardrails |
| Data pipeline | Python 3.11, PySpark 4.1.1, Pandas, PyArrow, Google Cloud Storage and BigQuery clients |
| Analytics | Pandas, NumPy, scikit-learn |
| Cloud | Cloud Run services, Cloud Run Jobs, Google Workflows, Cloud Scheduler, GCS, BigQuery, Artifact Registry |
| Quality | Jest, pytest, Ruff, mypy, data contracts, warehouse validation, smoke tests |

## Repository Structure

```text
.
|-- contracts/                    # Indicator, table, and data-quality contracts
|-- fe/                           # Next.js dashboard and AI chat frontend
|-- infra/gcp/cloud-run/          # Cloud Run deployment configuration examples
|-- scripts/                      # Contract, deployment, ETL, and validation utilities
|-- server/                       # NestJS Backend API
|-- services/
|   |-- ai-agent-service/         # FastAPI AI Agent and BigQuery tools
|   |-- analytics-worker/         # Trend, anomaly, clustering, and batch analytics
|   |-- data-pipeline/            # Source ingestion and Bronze/Silver/Gold publishing
|   `-- query-agent/              # Parser datasets, training, evaluation, inference, and model artifact
`-- sql/bigquery/                 # Generated BigQuery DDL
```

## Getting Started

### Prerequisites

- Node.js 20+
- Python 3.11+; Python 3.12 is used by the AI Agent container
- Java 17 for local PySpark pipeline execution
- Google Cloud CLI and credentials with access to the configured BigQuery datasets
- Optional: Docker for container builds and Cloud Run parity

Authenticate the local BigQuery clients with Application Default Credentials:

```powershell
gcloud auth application-default login
gcloud config set project western-pivot-452008-a6
```

Access to the deployed project's datasets is required. For another Google Cloud project, create equivalent datasets and override the environment variables below.

### 1. Clone the repository

```powershell
git clone https://github.com/DataMeowTt/Government-Ai-Agent-Platform.git
cd Government-Ai-Agent-Platform
```

### 2. Start the AI Agent

```powershell
cd services/ai-agent-service
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create `services/ai-agent-service/.env`:

```dotenv
PORT=8002
INTERNAL_API_KEY=dev-internal-key
AI_AGENT_DATA_SOURCE=bigquery
BIGQUERY_PROJECT_ID=western-pivot-452008-a6
BIGQUERY_LOCATION=asia-southeast1
BIGQUERY_GOLD_DATASET=gov_ai_gold
BIGQUERY_ANALYTICS_DATASET=gov_ai_analytics
BIGQUERY_MAX_BYTES_BILLED=100000000

# Required for the fine-tuned external parser path used by the full demo flow.
PARSER_SERVICE_BASE_URL=https://your-parser-service.example.com

# Optional Gemini routing/composition.
ENABLE_GEMINI=false
GEMINI_API_KEY=
```

Run the service:

```powershell
uvicorn app.main:app --reload --port 8002
```

Health endpoint: `http://localhost:8002/health`

### 3. Start the Backend API

Open another terminal:

```powershell
cd server
npm ci
```

Create `server/.env`:

```dotenv
PORT=3001
NODE_ENV=development
BACKEND_DATA_SOURCE=bigquery
BIGQUERY_PROJECT_ID=western-pivot-452008-a6
BIGQUERY_LOCATION=asia-southeast1
BIGQUERY_GOLD_DATASET=gov_ai_gold
BIGQUERY_ANALYTICS_DATASET=gov_ai_analytics
BIGQUERY_OPS_DATASET=gov_ai_ops
BIGQUERY_MAX_BYTES_BILLED=100000000
BIGQUERY_CACHE_TTL_SECONDS=300
AI_AGENT_BASE_URL=http://localhost:8002
AI_AGENT_TIMEOUT_MS=90000
AI_AGENT_INTERNAL_API_KEY=dev-internal-key
CORS_ORIGINS=http://localhost:3000
```

Run the API:

```powershell
npm run start:dev
```

Backend base URL: `http://localhost:3001`

### 4. Start the Frontend

Open a third terminal:

```powershell
cd fe
npm ci
Copy-Item .env.example .env.local
```

Set the frontend API URL in `fe/.env.local`:

```dotenv
NEXT_PUBLIC_API_URL=http://localhost:3001
```

Start Next.js:

```powershell
npm run dev
```

Open `http://localhost:3000`.

The dashboard and BigQuery-backed API can run without Gemini. The complete natural-language parsing path additionally needs a reachable parser service; Gemini features need a valid API key when enabled.

## Backend API

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/api/v1/indicators` | Public indicator catalog and capabilities |
| `GET` | `/api/v1/countries` | Countries available in the warehouse |
| `GET` | `/api/v1/countries/:code/full-analytics` | Full country analytics profile |
| `GET` | `/api/v1/countries/:code/indicators` | Country indicator series |
| `GET` | `/api/v1/countries/:code/anomalies` | Country anomaly records |
| `GET` | `/api/v1/countries/:code/cluster-benchmark` | Country cluster comparison |
| `GET` | `/api/v1/compare` | Country/indicator comparison by year range |
| `GET` | `/api/v1/analytics/clusters` | Structural clustering results |
| `GET` | `/api/v1/analytics/anomalies` | Paginated anomaly results |
| `POST` | `/api/v1/ai/chat` | Backend proxy to the AI Agent |
| `GET` | `/api/v1/ai/health` | AI Agent connectivity check |
| `GET` | `/api/v1/system/data-freshness` | Latest successful pipeline metadata |

## Data Pipeline

Install the pipeline and development dependencies:

```powershell
cd services/data-pipeline
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

Inspect the guarded scheduled pipeline options:

```powershell
python -m jobs.scheduled_pipeline --help
python -m jobs.plan_snapshot --help
```

The production demo uses:

- Cloud Run Job: `gov-ai-snapshot-plan`
- Workflow: `economic-data-pipeline`
- Scheduler: `economic-data-pipeline-monthly`
- Schedule: day 5 of every month at `02:00 UTC`
- ETL runtime: 2 CPU, 8 GiB memory, 1-hour timeout

The base ETL job is kept non-writing. Write approval is passed only through a controlled workflow execution, followed by validation, scoped publish, recovery support, and `SUCCESS` metadata.

## Testing and Validation

### Frontend

```powershell
cd fe
npm run lint
npm run build
```

### Backend

```powershell
cd server
npm test -- --runInBand
npm run test:e2e
npm run build
```

### AI Agent

```powershell
cd services/ai-agent-service
pip install pytest
pytest tests -q
```

### Data pipeline

```powershell
cd services/data-pipeline
pip install -e ".[dev]"
pytest
ruff check .
```

### Shared contracts

```powershell
python scripts/validate_indicator_contract.py
python scripts/parser_catalog_audit.py
```

## Cloud Deployment

This section is the explicit end-to-end deployment path for Google Cloud. The helper scripts in this repository are scoped to the demo project `western-pivot-452008-a6`; if you deploy to a different project, update the values in `infra/gcp/cloud-run/*.env.local` and remove or adapt the project guard in the deployment scripts.

### 1. Prepare Google Cloud

Install the Google Cloud CLI, authenticate, and select the target project:

```powershell
gcloud auth login
gcloud auth application-default login
gcloud config set project western-pivot-452008-a6
```

Enable the required APIs:

```powershell
$PROJECT_ID = "western-pivot-452008-a6"

gcloud services enable run.googleapis.com --project $PROJECT_ID
gcloud services enable artifactregistry.googleapis.com --project $PROJECT_ID
gcloud services enable secretmanager.googleapis.com --project $PROJECT_ID
gcloud services enable bigquery.googleapis.com --project $PROJECT_ID
gcloud services enable storage.googleapis.com --project $PROJECT_ID
gcloud services enable workflows.googleapis.com --project $PROJECT_ID
gcloud services enable cloudscheduler.googleapis.com --project $PROJECT_ID
gcloud services enable workflowexecutions.googleapis.com --project $PROJECT_ID
```

Create the Artifact Registry repository if it does not already exist:

```powershell
$REGION = "asia-southeast1"
$ARTIFACT_REPOSITORY = "gov-ai-jobs"

gcloud artifacts repositories create $ARTIFACT_REPOSITORY `
  --repository-format=docker `
  --location $REGION `
  --project $PROJECT_ID

gcloud auth configure-docker "$REGION-docker.pkg.dev"
```

Create or verify the runtime service account:

```powershell
$RUNTIME_SERVICE_ACCOUNT = "gov-ai-runner@$PROJECT_ID.iam.gserviceaccount.com"

gcloud iam service-accounts create gov-ai-runner `
  --project $PROJECT_ID `
  --display-name "Government AI Cloud Run runtime"
```

Grant the runtime account the permissions needed by the demo services and ETL job:

```powershell
gcloud projects add-iam-policy-binding $PROJECT_ID `
  --member "serviceAccount:$RUNTIME_SERVICE_ACCOUNT" `
  --role "roles/bigquery.jobUser"

gcloud projects add-iam-policy-binding $PROJECT_ID `
  --member "serviceAccount:$RUNTIME_SERVICE_ACCOUNT" `
  --role "roles/bigquery.dataViewer"

gcloud projects add-iam-policy-binding $PROJECT_ID `
  --member "serviceAccount:$RUNTIME_SERVICE_ACCOUNT" `
  --role "roles/bigquery.dataEditor"

gcloud projects add-iam-policy-binding $PROJECT_ID `
  --member "serviceAccount:$RUNTIME_SERVICE_ACCOUNT" `
  --role "roles/storage.objectAdmin"

gcloud projects add-iam-policy-binding $PROJECT_ID `
  --member "serviceAccount:$RUNTIME_SERVICE_ACCOUNT" `
  --role "roles/secretmanager.secretAccessor"

gcloud projects add-iam-policy-binding $PROJECT_ID `
  --member "serviceAccount:$RUNTIME_SERVICE_ACCOUNT" `
  --role "roles/logging.logWriter"
```

The deploying identity also needs Cloud Run Admin, Artifact Registry Writer, Workflows Admin, Cloud Scheduler Admin, Secret Manager Admin, and `iam.serviceAccounts.actAs` on the runtime service account.

### 2. Prepare environment files and secrets

Deployment examples live in [`infra/gcp/cloud-run/`](infra/gcp/cloud-run/). Create local copies for environment-specific values:

```powershell
Copy-Item infra/gcp/cloud-run/deploy.env.example infra/gcp/cloud-run/deploy.env.local
Copy-Item infra/gcp/cloud-run/backend.env.example infra/gcp/cloud-run/backend.env.local
Copy-Item infra/gcp/cloud-run/ai-agent.env.example infra/gcp/cloud-run/ai-agent.env.local
Copy-Item infra/gcp/cloud-run/secrets.env.example infra/gcp/cloud-run/secrets.env.local
```

Edit the `.env.local` files:

- `deploy.env.local`: project id, region, Artifact Registry repository, image tag, service names, runtime service account.
- `backend.env.local`: BigQuery datasets, AI Agent URL, timeout, cache TTL, and CORS origins.
- `ai-agent.env.local`: BigQuery datasets, Gemini toggle, parser runtime flags.
- `secrets.env.local`: secret values. Do not commit this file.

Required Secret Manager names used by the scripts:

| Secret | Runtime env var | Required when |
| --- | --- | --- |
| `gov-ai-agent-internal-api-key` | `INTERNAL_API_KEY`, `AI_AGENT_INTERNAL_API_KEY` | Always, for Backend to AI Agent calls |
| `gov-ai-gemini-api-key` | `GEMINI_API_KEY` | `ENABLE_GEMINI=true` |
| `gov-ai-parser-service-base-url` | `PARSER_SERVICE_BASE_URL` | Full semantic parser flow |
| `gov-ai-parser-service-api-key` | `PARSER_SERVICE_API_KEY` | Parser service requires an API key |

Import the secret values without printing them:

```powershell
.\scripts\import_cloud_run_secrets_from_env.ps1
```

### 3. Build and push container images

The service deployment script expects images to already exist in Artifact Registry. Build and push the Backend, AI Agent, and data-pipeline images first:

```powershell
$PROJECT_ID = "western-pivot-452008-a6"
$REGION = "asia-southeast1"
$ARTIFACT_REPOSITORY = "gov-ai-jobs"
$IMAGE_TAG = "bigquery-direct"
$IMAGE_PREFIX = "$REGION-docker.pkg.dev/$PROJECT_ID/$ARTIFACT_REPOSITORY"

docker build -f services/ai-agent-service/Dockerfile `
  -t "$IMAGE_PREFIX/gov-ai-agent:$IMAGE_TAG" `
  services/ai-agent-service
docker push "$IMAGE_PREFIX/gov-ai-agent:$IMAGE_TAG"

docker build -f server/Dockerfile `
  -t "$IMAGE_PREFIX/gov-ai-backend:$IMAGE_TAG" `
  server
docker push "$IMAGE_PREFIX/gov-ai-backend:$IMAGE_TAG"

docker build -f services/data-pipeline/Dockerfile `
  -t "$IMAGE_PREFIX/gov-ai-data-pipeline:$IMAGE_TAG" `
  services/data-pipeline
docker push "$IMAGE_PREFIX/gov-ai-data-pipeline:$IMAGE_TAG"
```

The Frontend image needs the deployed Backend URL at build time, so build it after the Backend service is deployed.

### 4. Deploy AI Agent and Backend

The service deployment script deploys `gov-ai-agent` and `gov-ai-backend`, then runs smoke checks. It refuses to deploy unless the monthly scheduler is paused, which prevents a data refresh from running while service images are being changed.

If this is a fresh project and the scheduler does not exist yet, create a paused placeholder first:

```powershell
$WORKFLOW_EXECUTION_URI = "https://workflowexecutions.googleapis.com/v1/projects/$PROJECT_ID/locations/$REGION/workflows/economic-data-pipeline/executions"

gcloud scheduler jobs describe economic-data-pipeline-monthly `
  --location $REGION `
  --project $PROJECT_ID *> $null

if ($LASTEXITCODE -ne 0) {
  gcloud scheduler jobs create http economic-data-pipeline-monthly `
    --project $PROJECT_ID `
    --location $REGION `
    --schedule "0 2 5 * *" `
    --time-zone "Etc/UTC" `
    --uri $WORKFLOW_EXECUTION_URI `
    --http-method POST `
    --oauth-service-account-email $RUNTIME_SERVICE_ACCOUNT `
    --oauth-token-scope "https://www.googleapis.com/auth/cloud-platform" `
    --message-body "{}"
}
```

Pause the scheduler before deploying or redeploying services:

```powershell
gcloud scheduler jobs pause economic-data-pipeline-monthly `
  --location $REGION `
  --project $PROJECT_ID
```

Review the sanitized plan first:

```powershell
.\scripts\deploy_cloud_run_services.ps1 -PlanOnly
```

Deploy and smoke test:

```powershell
.\scripts\deploy_cloud_run_services.ps1
```

Useful variants:

```powershell
.\scripts\deploy_cloud_run_services.ps1 -SkipSmoke
.\scripts\deploy_cloud_run_services.ps1 -SkipDeploy
```

The script prints the deployed `ai_agent_url` and `backend_url`. Save the Backend URL for the next step:

```powershell
$BACKEND_URL = gcloud run services describe gov-ai-backend `
  --region asia-southeast1 `
  --project western-pivot-452008-a6 `
  --format "value(status.url)"
```

### 5. Deploy the Frontend

Build the Frontend with `NEXT_PUBLIC_API_URL` pointing to the deployed Backend:

```powershell
$FRONTEND_SERVICE_NAME = "gov-ai-frontend"

docker build -f fe/Dockerfile `
  --build-arg NEXT_PUBLIC_API_URL=$BACKEND_URL `
  -t "$IMAGE_PREFIX/gov-ai-frontend:$IMAGE_TAG" `
  fe
docker push "$IMAGE_PREFIX/gov-ai-frontend:$IMAGE_TAG"

gcloud run deploy $FRONTEND_SERVICE_NAME `
  --project $PROJECT_ID `
  --region $REGION `
  --platform managed `
  --service-account $RUNTIME_SERVICE_ACCOUNT `
  --image "$IMAGE_PREFIX/gov-ai-frontend:$IMAGE_TAG" `
  --ingress all `
  --allow-unauthenticated `
  --min-instances 0 `
  --cpu 1 `
  --memory 512Mi `
  --set-env-vars "NEXT_PUBLIC_API_URL=$BACKEND_URL"
```

Get the Frontend URL and update Backend CORS:

```powershell
$FRONTEND_URL = gcloud run services describe $FRONTEND_SERVICE_NAME `
  --region $REGION `
  --project $PROJECT_ID `
  --format "value(status.url)"

gcloud run services update gov-ai-backend `
  --project $PROJECT_ID `
  --region $REGION `
  --update-env-vars "CORS_ORIGINS=http://localhost:3000,http://localhost:3001,$FRONTEND_URL"
```

Open `$FRONTEND_URL` and confirm that dashboard pages can call the Backend.

### 6. Deploy the ETL Cloud Run Job

Deploy the data pipeline as a safe default job. The default command is `plan` mode, so it does not write GCS or BigQuery unless the workflow later passes explicit approval environment variables:

```powershell
$BUCKET = "western-pivot-452008-a6-gov-ai-economic-data"

gcloud run jobs deploy gov-ai-snapshot-plan `
  --project $PROJECT_ID `
  --region $REGION `
  --image "$IMAGE_PREFIX/gov-ai-data-pipeline:$IMAGE_TAG" `
  --service-account $RUNTIME_SERVICE_ACCOUNT `
  --cpu 2 `
  --memory 8Gi `
  --task-timeout 3600 `
  --max-retries 0 `
  --command python `
  --args "-m,jobs.scheduled_pipeline,--mode,plan,--run-id,manual-plan,--run-date,2026-01-01,--source,all,--runtime-dir,/tmp/gov-ai/runtime,--output-dir,/tmp/gov-ai/output,--project-id,$PROJECT_ID,--location,$REGION,--gcs-bucket,$BUCKET,--silver-output-format,parquet,--silver-source,all" `
  --set-env-vars "PYTHONUNBUFFERED=1"
```

Run a plan-only job once:

```powershell
gcloud run jobs execute gov-ai-snapshot-plan `
  --project $PROJECT_ID `
  --region $REGION `
  --wait
```

The planned production path is:

```text
source acquisition -> change detection -> Bronze snapshot -> Silver candidate
-> Gold/Analytics candidates -> quality gate -> scoped BigQuery publish
-> Ops freshness metadata
```

### 7. Deploy Workflow and Scheduler

Generate and validate the offline workflow/scheduler plan:

```powershell
python scripts/workflow_scheduler_plan.py --check
python scripts/workflow_scheduler_plan.py --format text
```

Create a deployable workflow file, then deploy it. The workflow executes the ETL job with explicit write approvals scoped to that workflow execution:

```powershell
$WORKFLOW_FILE = "$env:TEMP\economic-data-pipeline.yaml"

@"
main:
  params: [args]
  steps:
    - init:
        assign:
          - project_id: `${sys.get_env("GOOGLE_CLOUD_PROJECT_ID")}
          - location: "$REGION"
          - job_name: "gov-ai-snapshot-plan"
          - run_id: `${"scheduled-refresh-" + string(int(sys.now()))}
          - run_date: `${text.substring(time.format(sys.now()), 0, 10)}
    - run_etl_job:
        call: googleapis.run.v2.projects.locations.jobs.run
        args:
          name: `${"projects/" + project_id + "/locations/" + location + "/jobs/" + job_name}
          body:
            overrides:
              containerOverrides:
                - args:
                    - "-m"
                    - "jobs.scheduled_pipeline"
                    - "--mode"
                    - "execute"
                    - "--run-id"
                    - `${run_id}
                    - "--run-date"
                    - `${run_date}
                    - "--source"
                    - "all"
                    - "--allow-network"
                    - "--runtime-dir"
                    - "/tmp/gov-ai/runtime"
                    - "--output-dir"
                    - "/tmp/gov-ai/output"
                    - "--project-id"
                    - `${project_id}
                    - "--location"
                    - `${location}
                    - "--gcs-bucket"
                    - "$BUCKET"
                  env:
                    - name: CLOUD_WRITE_APPROVED
                      value: "true"
                    - name: BIGQUERY_WRITE_APPROVED
                      value: "true"
                    - name: BIGQUERY_WAREHOUSE_WRITE_APPROVED
                      value: "true"
                    - name: BIGQUERY_OPS_WRITE_APPROVED
                      value: "true"
                    - name: RECOVERY_TABLE_RETENTION_DAYS
                      value: "45"
        result: run_result
    - finish:
        return:
          status: "submitted_execute_cloud_run_job"
          run_id: `${run_id}
          run_date: `${run_date}
          run_result: `${run_result}
"@ | Set-Content -Encoding UTF8 $WORKFLOW_FILE

gcloud workflows deploy economic-data-pipeline `
  --project $PROJECT_ID `
  --location $REGION `
  --service-account $RUNTIME_SERVICE_ACCOUNT `
  --source $WORKFLOW_FILE
```

Update the monthly scheduler target and keep it paused until smoke checks pass:

```powershell
$WORKFLOW_EXECUTION_URI = "https://workflowexecutions.googleapis.com/v1/projects/$PROJECT_ID/locations/$REGION/workflows/economic-data-pipeline/executions"

gcloud scheduler jobs update http economic-data-pipeline-monthly `
  --project $PROJECT_ID `
  --location $REGION `
  --schedule "0 2 5 * *" `
  --time-zone "Etc/UTC" `
  --uri $WORKFLOW_EXECUTION_URI `
  --http-method POST `
  --oauth-service-account-email $RUNTIME_SERVICE_ACCOUNT `
  --oauth-token-scope "https://www.googleapis.com/auth/cloud-platform" `
  --message-body "{}"

gcloud scheduler jobs pause economic-data-pipeline-monthly `
  --project $PROJECT_ID `
  --location $REGION
```

If you skipped the placeholder creation earlier, create the scheduler instead:

```powershell
gcloud scheduler jobs create http economic-data-pipeline-monthly `
  --project $PROJECT_ID `
  --location $REGION `
  --schedule "0 2 5 * *" `
  --time-zone "Etc/UTC" `
  --uri $WORKFLOW_EXECUTION_URI `
  --http-method POST `
  --oauth-service-account-email $RUNTIME_SERVICE_ACCOUNT `
  --oauth-token-scope "https://www.googleapis.com/auth/cloud-platform" `
  --message-body "{}"
```

Run a controlled workflow execution manually:

```powershell
gcloud workflows run economic-data-pipeline `
  --project $PROJECT_ID `
  --location $REGION
```

Resume the monthly schedule only after the manual execution and smoke checks pass:

```powershell
gcloud scheduler jobs resume economic-data-pipeline-monthly `
  --project $PROJECT_ID `
  --location $REGION
```

### 8. Post-deployment smoke checks

```powershell
curl.exe "$BACKEND_URL/api/v1/system/data-freshness"
curl.exe "$BACKEND_URL/api/v1/indicators"
curl.exe "$BACKEND_URL/api/v1/countries"
curl.exe "$BACKEND_URL/api/v1/compare?countries=VNM,THA&indicator=govdebt_GDP&from=2010&to=2023"
curl.exe "$BACKEND_URL/api/v1/ai/health"

curl.exe -X POST "$BACKEND_URL/api/v1/ai/chat" `
  -H "Content-Type: application/json" `
  -d "{\"message\":\"Compare public debt of Vietnam and Thailand from 2010 to 2023\",\"conversationId\":\"cloud-smoke-readme\"}"
```

If the Frontend renders but API calls fail, check `CORS_ORIGINS` on `gov-ai-backend` and confirm `NEXT_PUBLIC_API_URL` was set during the Frontend Docker build.

### 9. Rollback and operational commands

List revisions:

```powershell
gcloud run revisions list --service gov-ai-backend --region $REGION --project $PROJECT_ID
gcloud run revisions list --service gov-ai-agent --region $REGION --project $PROJECT_ID
gcloud run revisions list --service gov-ai-frontend --region $REGION --project $PROJECT_ID
```

Route all traffic back to a previous revision:

```powershell
gcloud run services update-traffic gov-ai-backend `
  --region $REGION `
  --project $PROJECT_ID `
  --to-revisions REVISION_NAME=100
```

Pause scheduled ETL while investigating an issue:

```powershell
gcloud scheduler jobs pause economic-data-pipeline-monthly `
  --project $PROJECT_ID `
  --location $REGION
```

## Current Limitations

- The fine-tuned parser currently uses a separate demo deployment path and is not yet a production-grade managed service.
- Parser exact-JSON accuracy is 63.2%, although intent, indicator, and country metrics are substantially higher and downstream guardrails reject unsafe plans.
- Current analytics are primarily descriptive; forecasting, causal inference, policy simulation, and uncertainty modeling are outside the present scope.
- Dashboard evaluation is currently based on functional and smoke testing rather than a formal end-user usability study.
- A production rollout still needs stronger authentication, authorization, rate limiting, audit logging, alerting, rollback automation, and cost monitoring.

## Project Status

The end-to-end demo has verified:

- A controlled ETL run with `SUCCESS` metadata
- Monthly workflow and scheduler configuration
- BigQuery-backed data freshness through the Backend API
- AI health check returning HTTP 200
- AI chat smoke test returning a successful response
- Dashboard flows for country lookup, comparison, anomalies, clusters, indicators, and AI chat

This repository is an academic/demo implementation. Treat cloud identifiers, external parser endpoints, and model artifacts as environment-specific when adapting it for another deployment.
