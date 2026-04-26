# Government AI Agent Platform — Data Pipeline

A production-grade macroeconomic data pipeline that ingests, transforms, and serves structured analytical tables for AI insight generation and dashboard consumption.

---

## Overview

This project builds a two-layer data pipeline (Silver → Gold) over three global macroeconomic datasets covering **88 countries** from **1980 to 2025**. The Gold layer is loaded directly into PostgreSQL and serves as the foundation for AI-driven economic analysis and visualization.

---

## Data Sources

| Source | Description | Indicators |
|--------|-------------|------------|
| **WDI** | World Bank — World Development Indicators | GDP, unemployment, poverty, trade, population |
| **GMD** | Global Macro Database | Real GDP, fiscal balance, debt, crisis flags, REER |
| **MACRO** | FAO Macro Statistics | GDP value, GFCF, GNI, agricultural/manufacturing VA |

---

## Silver Layer

Each source goes through its own pipeline:
- **Filter** — country whitelist (88 ISO-3 codes), year range, indicator selection
- **Transform** — rename, cast, reshape (pivot/unpivot)
- **Feature engineering** — rolling windows, growth rates, log transforms, encoded flags
- **Validate** — range checks, null handling, deduplication

Output: a single long-format CSV with schema:

```
country_code | country | year | indicator | value | source
```

---

## Gold Layer

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

---

- **AI Insights** — LLM-based analysis over Gold tables (growth anomaly detection, crisis early-warning, cross-country benchmarking)
- **Dashboard** — Visualization layer consuming PostgreSQL Gold tables (handed off to dev team)

---

## How to Run

**1. Setup**

```bash
git clone <repo>
cd Government-Ai-Agent-Platform

python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

pip install -e ".[dev]"

cp .env.example .env           # fill in POSTGRES_* values
```

**2. Bronze → Silver** (runs on Docker Spark cluster)

```bash
make silver
```

Reads raw CSVs from `/opt/dataset/`, outputs `processed.csv` to `/opt/workspace/data/processed_data/`.

**3. Silver → Gold** (runs locally, requires Postgres)

```bash
make gold
```

Reads `processed.csv`, builds 5 analytical tables, loads them into PostgreSQL.

To rebuild a single table: `make gold-table TABLE=crisis_risk`
