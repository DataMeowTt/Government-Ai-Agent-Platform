CREATE TABLE gold_growth_dynamics (
    country_code            VARCHAR(3)       NOT NULL,
    country                 TEXT             NOT NULL,
    year                    INTEGER          NOT NULL,
    "rGDP_growth_YoY"       DOUBLE PRECISION,
    rolling_mean_5yr        DOUBLE PRECISION,
    "GDP_growth_YoY"        DOUBLE PRECISION,
    "GDP_growth_trend_5yr"  DOUBLE PRECISION,
    trend_deviation         DOUBLE PRECISION,
    "GDP_pc_growth_gap"     DOUBLE PRECISION,
    "log_rGDP_pc_USD"       DOUBLE PRECISION,
    income_group            TEXT,
    development_group       TEXT,
    completeness_score      DOUBLE PRECISION,
    run_id                  TEXT,
    run_date                DATE,
    loaded_at               TIMESTAMP,
    PRIMARY KEY (country_code, year)
);
