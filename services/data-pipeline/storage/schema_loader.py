from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

_SCHEMA_DIR = Path(__file__).parent / "schema"

_GOLD_TABLES = [
    "gold_growth_dynamics",
    "gold_structural_composition",
    "gold_fiscal_monetary",
    "gold_crisis_risk",
    "gold_social_welfare",
]


def create_all_tables(engine: Engine) -> None:
    with engine.begin() as conn:
        for table in _GOLD_TABLES:
            conn.execute(text(f'DROP TABLE IF EXISTS "{table}" CASCADE'))
            ddl = (_SCHEMA_DIR / f"{table}.sql").read_text(encoding="utf-8")
            conn.execute(text(ddl))
            print(f"  schema OK: {table}")
