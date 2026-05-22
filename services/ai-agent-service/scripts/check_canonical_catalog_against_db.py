import sys
from pathlib import Path

from sqlalchemy import text


SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))


from app.catalog.canonical_indicator_catalog import (  # noqa: E402
    get_analytics_columns,
    list_indicators,
)
from app.core.config import settings  # noqa: E402


def main() -> int:
    indicators = list_indicators()
    errors: list[str] = []
    warnings: list[str] = []

    if not settings.database_url:
        print("DATABASE_URL is not configured; cannot check catalog against DB.")
        return 1

    from app.db.postgres import engine  # noqa: E402

    with engine.connect() as conn:
        table_names = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT table_name "
                    "FROM information_schema.tables "
                    "WHERE table_schema='public'"
                )
            )
        }
        columns_by_table = {
            table_name: _load_columns(conn, table_name)
            for table_name in table_names
        }

    ok_count = 0
    for indicator in indicators:
        indicator_errors: list[str] = []

        if indicator.gold_table not in table_names:
            indicator_errors.append(f"missing gold table public.{indicator.gold_table}")
        else:
            gold_columns = columns_by_table.get(indicator.gold_table, set())
            if indicator.gold_column not in gold_columns:
                indicator_errors.append(
                    f"missing gold column public.{indicator.gold_table}.{indicator.gold_column}"
                )

        if indicator.analytics_table:
            if indicator.analytics_table not in table_names:
                indicator_errors.append(f"missing analytics table public.{indicator.analytics_table}")
            else:
                analytics_columns = columns_by_table.get(indicator.analytics_table, set())
                for column_name in get_analytics_columns(indicator.code):
                    if column_name not in analytics_columns:
                        indicator_errors.append(
                            f"missing analytics column public.{indicator.analytics_table}.{column_name}"
                        )
        elif indicator.supports_trend or indicator.supports_anomaly:
            indicator_errors.append("supports trend/anomaly but analytics_table is not configured")

        if indicator_errors:
            for error in indicator_errors:
                errors.append(f"{indicator.code}: {error}")
        else:
            ok_count += 1

    print("Canonical catalog vs DB check")
    print(f"total indicators: {len(indicators)}")
    print(f"ok count: {ok_count}")
    print(f"errors: {len(errors)}")
    print(f"warnings: {len(warnings)}")

    if errors:
        print("\nErrors:")
        for error in errors:
            print(f"- {error}")

    if warnings:
        print("\nWarnings:")
        for warning in warnings:
            print(f"- {warning}")

    return 1 if errors else 0


def _load_columns(conn, table_name: str) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            text(
                "SELECT column_name "
                "FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=:table_name"
            ),
            {"table_name": table_name},
        )
    }


if __name__ == "__main__":
    raise SystemExit(main())
