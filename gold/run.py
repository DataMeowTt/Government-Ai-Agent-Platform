import argparse

from gold.io import load_silver
from gold.tables import (
    growth_dynamics,
    structural_composition,
    fiscal_monetary,
    crisis_risk,
    social_welfare,
)
from storage.connect import get_engine
from storage.schema_loader import create_all_tables

_ALL_TABLES = {
    "growth_dynamics":       growth_dynamics,
    "structural_composition": structural_composition,
    "fiscal_monetary":       fiscal_monetary,
    "crisis_risk":           crisis_risk,
    "social_welfare":        social_welfare,
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

    for name, module in runners.items():
        print(f"\nBuilding {name}...")
        module.run(silver, engine)

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
