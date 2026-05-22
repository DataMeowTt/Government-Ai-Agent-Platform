def build_compare_line_chart_data(rows: list[dict]) -> list[dict]:
    """
    Convert long format:
      country_code, year, value

    Thành chart format:
      year, VNM, THA
    """
    by_year: dict[int, dict] = {}

    for row in rows:
        year = row.get("year")
        country_code = row.get("country_code")
        value = row.get("value")

        if year is None or country_code is None:
            continue

        if year not in by_year:
            by_year[year] = {"year": year}

        by_year[year][country_code] = value

    return [by_year[year] for year in sorted(by_year.keys())]


def build_series_line_chart_data(rows: list[dict]) -> list[dict]:
    return [
        {
            "year": row.get("year"),
            "value": row.get("value"),
            "country_code": row.get("country_code"),
            "country": row.get("country"),
        }
        for row in rows
    ]


def build_ranking_bar_chart_data(rows: list[dict]) -> list[dict]:
    return [
        {
            "country_code": row.get("country_code"),
            "country": row.get("country"),
            "year": row.get("year"),
            "value": row.get("value"),
        }
        for row in rows
    ]


def build_anomaly_bar_chart_data(rows: list[dict]) -> list[dict]:
    return [
        {
            "country_code": row.get("country_code"),
            "country": row.get("country"),
            "year": row.get("year"),
            "actual_value": row.get("actual_value"),
            "trend_value": row.get("trend_value"),
            "residual_value": row.get("residual_value"),
            "anomaly_score": row.get("anomaly_score"),
        }
        for row in rows
    ]