import argparse
from dataclasses import dataclass
from typing import Callable

import pandas as pd
from gold.io import load_silver
from gold.loaders.postgres_loader import load_to_postgres
from gold.transforms import add_run_metadata, current_loaded_at
from gold.tables import (
    growth_dynamics,
    structural_composition,
    fiscal_monetary,
    crisis_risk,
    social_welfare,
)
from storage.connect import get_engine
from storage.schema_loader import create_all_tables


@dataclass(frozen=True)
class GoldTableSpec:
    table_name: str
    build: Callable[[pd.DataFrame], pd.DataFrame]
    crisis_check: bool = False


_ALL_TABLES = {
    "growth_dynamics": GoldTableSpec(
        table_name="gold_growth_dynamics",
        build=growth_dynamics.build,
    ),
    "structural_composition": GoldTableSpec(
        table_name="gold_structural_composition",
        build=structural_composition.build,
    ),
    "fiscal_monetary": GoldTableSpec(
        table_name="gold_fiscal_monetary",
        build=fiscal_monetary.build,
    ),
    "crisis_risk": GoldTableSpec(
        table_name="gold_crisis_risk",
        build=crisis_risk.build,
        crisis_check=True,
    ),
    "social_welfare": GoldTableSpec(
        table_name="gold_social_welfare",
        build=social_welfare.build,
    ),
}


def main(table: str = "all", silver_path: str = None) -> None:
    print("Connecting to Postgres...")
    engine = get_engine()

    print("Creating / resetting schemas...")
    create_all_tables(engine)

    print("\nLoading silver layer...")
    silver = load_silver(silver_path)
    print(f"Silver rows: {len(silver):,}")

    runners = _ALL_TABLES if table == "all" else {table: _ALL_TABLES[table]}
    loaded_at = current_loaded_at()

    for name, spec in runners.items():
        print(f"\nBuilding {name}...")
        gold_df = add_run_metadata(spec.build(silver), loaded_at=loaded_at)
        load_to_postgres(
            gold_df,
            spec.table_name,
            engine,
            crisis_check=spec.crisis_check,
        )

    print("\nAll gold tables loaded into Postgres.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Gold layer pipeline.")
    parser.add_argument(
        "--table",
        default="all",
        choices=list(_ALL_TABLES.keys()) + ["all"],
        help="Which gold table to build (default: all).",
    )
    parser.add_argument(
        "--silver",
        default=None,
        metavar="PATH",
        help="Path to the Silver layer Spark output directory (default: auto-detect).",
    )
    args = parser.parse_args()
    main(table=args.table, silver_path=args.silver)