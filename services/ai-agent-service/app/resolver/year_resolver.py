import re
from dataclasses import dataclass


@dataclass(frozen=True)
class YearRange:
    start_year: int | None = None
    end_year: int | None = None
    years: list[int] | None = None


def resolve_year_range(message: str) -> YearRange:
    years = [int(item) for item in re.findall(r"(?<!\d)(?:19|20)\d{2}(?!\d)", message)]

    if not years:
        return YearRange(start_year=None, end_year=None, years=[])

    if re.search(r"thập kỷ|thap ky|decade", message, re.IGNORECASE) and len(years) == 1:
        decade_start = years[0]
        return YearRange(
            start_year=decade_start,
            end_year=decade_start + 9,
            years=[decade_start, decade_start + 9],
        )

    if len(years) == 1:
        return YearRange(
            start_year=years[0],
            end_year=years[0],
            years=[years[0]],
        )

    start_year = min(years)
    end_year = max(years)

    return YearRange(
        start_year=start_year,
        end_year=end_year,
        years=[start_year, end_year],
    )