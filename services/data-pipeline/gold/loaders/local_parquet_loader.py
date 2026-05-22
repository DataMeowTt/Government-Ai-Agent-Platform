from pathlib import Path

import pandas as pd

from gold.io import validate
from utils.io_paths import to_local_path


DEFAULT_GOLD_OUTPUT_DIR = "data/gold"


def resolve_table_output_path(output_dir: str | None, table: str) -> Path:
    base_dir = to_local_path(output_dir or DEFAULT_GOLD_OUTPUT_DIR)
    return base_dir / table


def write_gold_parquet(
    df: pd.DataFrame,
    table: str,
    output_dir: str | None = None,
    crisis_check: bool = False,
) -> Path:
    validate(df, table, crisis_check=crisis_check)

    output_path = resolve_table_output_path(output_dir, table)
    output_path.mkdir(parents=True, exist_ok=True)

    file_path = output_path / "part-00000.parquet"
    df.to_parquet(file_path, index=False)

    print(f"  loaded -> local parquet: {file_path}")
    return file_path