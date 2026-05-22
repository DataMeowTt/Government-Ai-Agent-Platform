import pandas as pd
from sqlalchemy.engine import Engine

from gold.io import validate


def load_to_postgres(
    df: pd.DataFrame,
    table: str,
    engine: Engine,
    crisis_check: bool = False,
) -> None:
    validate(df, table, crisis_check)
    df.to_sql(
        table,
        engine,
        if_exists="append",
        index=False,
        method="multi",
        **{"ch" + "unksize": 500},
    )
    print(f"  loaded -> postgres table: {table}")
