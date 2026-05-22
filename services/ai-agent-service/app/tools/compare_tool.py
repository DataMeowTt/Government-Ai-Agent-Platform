from app.tools.coverage_tool import get_data_coverage
from app.tools.indicator_series_tool import get_indicator_series
from app.tools.common import require_family_support


def compare_countries(
    indicator_code: str,
    country_codes: list[str],
    start_year: int | None = None,
    end_year: int | None = None,
) -> dict:
    require_family_support(indicator_code, "compare")

    rows = get_indicator_series(
        indicator_code=indicator_code,
        country_codes=country_codes,
        start_year=start_year,
        end_year=end_year,
    )

    coverage = get_data_coverage(
        indicator_code=indicator_code,
        country_codes=country_codes,
    )

    return {
        "indicator": indicator_code,
        "countries": country_codes,
        "start_year": start_year,
        "end_year": end_year,
        "coverage": coverage,
        "rows": rows,
    }
