import argparse
from dataclasses import dataclass
from typing import Callable, Literal

import pandas as pd

from gold.io import load_silver
from gold.loaders.local_parquet_loader import write_gold_parquet
from gold.loaders.postgres_loader import load_to_postgres
from gold.transforms import add_run_metadata, current_loaded_at
from gold.tables import (
    crisis_risk,
    fiscal_monetary,
    growth_dynamics,
    social_welfare,
    structural_composition,
)
from storage.connect import get_engine
from storage.schema_loader import create_all_tables


GoldTarget = Literal["local_parquet", "postgres"]


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


def _load_to_target(
    gold_df: pd.DataFrame,
    spec: GoldTableSpec,
    target: GoldTarget,
    gold_output_dir: str | None,
    engine,
) -> None:
    if target == "local_parquet":
        write_gold_parquet(
            gold_df,
            spec.table_name,
            output_dir=gold_output_dir,
            crisis_check=spec.crisis_check,
        )
        return

    if target == "postgres":
        if engine is None:
            raise RuntimeError("Postgres engine is required for target='postgres'.")

        load_to_postgres(
            gold_df,
            spec.table_name,
            engine,
            crisis_check=spec.crisis_check,
        )
        return

    raise ValueError(f"Unsupported target: {target!r}")


def main(
    table: str = "all",
    silver_path: str | None = None,
    target: GoldTarget = "postgres",
    gold_output_dir: str | None = None,
    reset_schema: bool = True,
) -> None:
    print("\nLoading silver layer...")
    silver = load_silver(silver_path)
    print(f"Silver rows: {len(silver):,}")

    engine = None

    if target == "postgres":
        print("\nConnecting to Postgres...")
        engine = get_engine()

        if reset_schema:
            print("Creating / resetting schemas...")
            create_all_tables(engine)

    runners = _ALL_TABLES if table == "all" else {table: _ALL_TABLES[table]}
    loaded_at = current_loaded_at()

    for name, spec in runners.items():
        print(f"\nBuilding {name}...")
        gold_df = add_run_metadata(spec.build(silver), loaded_at=loaded_at)
        _load_to_target(
            gold_df=gold_df,
            spec=spec,
            target=target,
            gold_output_dir=gold_output_dir,
            engine=engine,
        )

    print(f"\nGold build finished. target={target}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build Gold tables.")
    parser.add_argument(
        "--table",
        default="all",
        choices=list(_ALL_TABLES.keys()) + ["all"],
        help="Which gold table to build.",
    )
    parser.add_argument(
        "--silver",
        default=None,
        metavar="PATH",
        help="Path to the Silver Spark CSV output directory.",
    )
    parser.add_argument(
        "--target",
        default="postgres",
        choices=["local_parquet", "postgres"],
        help="Where to write Gold output.",
    )
    parser.add_argument(
        "--gold-output-dir",
        default=None,
        metavar="PATH",
        help="Local directory for target=local_parquet.",
    )
    parser.add_argument(
        "--no-reset-schema",
        action="store_true",
        help="For target=postgres, do not drop/recreate Gold schemas.",
    )

    args = parser.parse_args()

    main(
        table=args.table,
        silver_path=args.silver,
        target=args.target,
        gold_output_dir=args.gold_output_dir,
        reset_schema=not args.no_reset_schema,
    )