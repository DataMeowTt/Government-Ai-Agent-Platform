# Government AI Agent Platform — Data Pipeline

A production-grade macroeconomic data pipeline that ingests, transforms, and serves structured analytical tables for AI insight generation and dashboard consumption.

---

## Overview

This project builds a two-layer data pipeline (Silver → Gold) over three global macroeconomic datasets covering **88 countries** from **1980 to 2025**. The Gold layer is loaded directly into PostgreSQL and serves as the foundation for AI-driven economic analysis and visualization.

---

## Architecture

```
Raw Data (CSV)
    │
    ▼
┌─────────────────────────────────────────┐
│           Silver Layer (Spark)          │
│  WDI · GMD · MACRO → unified long fmt  │
└─────────────────┬───────────────────────┘
                  │  processed.csv (long format)
                  ▼
┌─────────────────────────────────────────┐
│           Gold Layer (Pandas)           │
│  5 analytical wide-format tables        │
└─────────────────┬───────────────────────┘
                  │
                  ▼
          PostgreSQL Database
                  │
        ┌─────────┴──────────┐
        ▼                    ▼
   AI Insights          Dashboard
```

---

## Data Sources

| Source | Description | Indicators |
|--------|-------------|------------|
| **WDI** | World Bank — World Development Indicators | GDP, unemployment, poverty, trade, population |
| **GMD** | Global Macro Database | Real GDP, fiscal balance, debt, crisis flags, REER |
| **MACRO** | FAO Macro Statistics | GDP value, GFCF, GNI, agricultural/manufacturing VA |

---

## Silver Layer

Processed by **Apache Spark 3.5.0** via Docker Compose (1 master + 2 workers).

Each source goes through its own pipeline:
- **Filter** — country whitelist (88 ISO-3 codes), year range, indicator selection
- **Transform** — rename, cast, reshape (pivot/unpivot)
- **Feature engineering** — rolling windows, growth rates, log transforms, encoded flags
- **Validate** — range checks, null handling, deduplication

Output: a single long-format CSV with schema:

```
country_code | country | year | indicator | value | source
```

Entry point: `docker compose up spark-submit`

---

## Gold Layer

Processed by **Pandas** from the Silver CSV. Produces 5 purpose-built wide-format tables loaded into PostgreSQL.

| Table | Purpose | Sources |
|-------|---------|---------|
| `gold_growth_dynamics` | GDP growth time-series, trend & cycle analysis | GMD, MACRO |
| `gold_structural_composition` | Sectoral composition, investment intensity | MACRO |
| `gold_fiscal_monetary` | Government finance, debt, inflation | GMD, WDI |
| `gold_crisis_risk` | Crisis flags, early-warning signals | GMD |
| `gold_social_welfare` | Unemployment, poverty, demographics | WDI, GMD |

Each table includes:
- `income_group` and `development_group` joined from GMD
- `completeness_score` — share of non-null indicators per row
- Linear interpolation (max 2 consecutive missing years) on numeric columns
- Source precedence: **GMD > WDI > MACRO** when indicators overlap

Entry point:
```bash
python -m src.processing_analysis.run_gold
```

---

## Project Structure

```
.
├── main.py                          # Spark entry point
├── docker-compose.yaml              # Spark cluster (master + 2 workers + submit)
├── requirements.txt
├── .env                             # Postgres credentials (gitignored)
│
├── data/
│   ├── raw_data/                    # Source CSVs (WDI, GMD, MACRO)
│   └── processed_data/             # Silver output
│
├── logs/
│   ├── processing.log
│   └── errors.log
│
└── src/
    ├── config/
    │   └── countries.py             # ALLOWED_ISO3 — 88 countries
    ├── processing/                  # Silver layer (PySpark)
    │   ├── WDI/
    │   ├── GMD/
    │   ├── MACRO/
    │   ├── schema/
    │   │   └── processed_schema.py
    │   └── processing_job.py
    ├── processing_analysis/         # Gold layer (Pandas)
    │   ├── gold_growth_dynamics.py
    │   ├── gold_structural_composition.py
    │   ├── gold_fiscal_monetary.py
    │   ├── gold_crisis_risk.py
    │   ├── gold_social_welfare.py
    │   └── run_gold.py
    ├── storage/
    │   ├── connect.py               # SQLAlchemy engine from .env
    │   ├── schema_loader.py         # DDL runner
    │   └── schema/                  # .sql table definitions
    └── utils/
        ├── logger.py
        └── gold_utils.py            # Shared Gold helpers
```

---

## Setup

**1. Environment**
```bash
conda activate btl_env
pip install -r requirements.txt
```

**2. Configure `.env`**
```env
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=mydb
POSTGRES_USER=your_user
POSTGRES_PASSWORD=your_password
```

**3. Run Silver layer** (requires Docker)
```bash
docker compose up spark-submit
```

**4. Run Gold layer → PostgreSQL**
```bash
python -m src.processing_analysis.run_gold
```

---

## Gold Layer Output Stats

| Table | Rows | Countries | Year Range |
|-------|------|-----------|------------|
| gold_growth_dynamics | 4,048 | 88 | 1980–2025 |
| gold_structural_composition | 3,823 | 87 | 1980–2024 |
| gold_fiscal_monetary | 4,048 | 88 | 1980–2025 |
| gold_crisis_risk | 4,048 | 88 | 1980–2025 |
| gold_social_welfare | 4,048 | 88 | 1980–2025 |

---

## Next Steps

- **AI Insights** — LLM-based analysis over Gold tables (growth anomaly detection, crisis early-warning, cross-country benchmarking)
- **Dashboard** — Visualization layer consuming PostgreSQL Gold tables (handed off to dev team)
