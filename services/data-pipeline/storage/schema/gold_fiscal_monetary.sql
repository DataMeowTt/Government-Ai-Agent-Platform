-- Column names match what SQLAlchemy writes from the gold_fiscal_monetary DataFrame.
-- Mixed-case names are quoted to preserve case in PostgreSQL.
CREATE TABLE gold_fiscal_monetary (
    country_code            VARCHAR(3)       NOT NULL,
    country                 TEXT             NOT NULL,
    year                    INTEGER          NOT NULL,
    "govdebt_GDP"           DOUBLE PRECISION,
    "debt_change_YoY"       DOUBLE PRECISION,
    "govrev_GDP"            DOUBLE PRECISION,
    "govexp_GDP"            DOUBLE PRECISION,
    "fiscal_balance_GDP"    DOUBLE PRECISION,
    cumulative_deficit_5yr  DOUBLE PRECISION,
    ltrate                  DOUBLE PRECISION,
    infl                    DOUBLE PRECISION,
    real_interest_rate      DOUBLE PRECISION,
    "tax_revenue_pct_GDP"   DOUBLE PRECISION,
    inflation_cpi           DOUBLE PRECISION,
    inflation_deflator      DOUBLE PRECISION,
    inflation_gap           DOUBLE PRECISION,
    rolling_3yr_avg_cpi     DOUBLE PRECISION,
    income_group            TEXT,
    development_group       TEXT,
    completeness_score      DOUBLE PRECISION,
    run_id                  TEXT,
    run_date                DATE,
    loaded_at               TIMESTAMP,
    PRIMARY KEY (country_code, year)
);
