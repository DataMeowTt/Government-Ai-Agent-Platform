from copy import deepcopy
from typing import Any


def merge_followup_query(previous_query: dict[str, Any], delta: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(previous_query or {})
    changes = delta or {}

    for key in ("indicator", "indicators", "intent"):
        if key in changes:
            merged[key] = changes[key]

    if "countries" in changes:
        merged["countries"] = list(changes["countries"] or [])
    if "add_countries" in changes:
        countries = list(merged.get("countries") or [])
        for country_code in changes.get("add_countries") or []:
            if country_code not in countries:
                countries.append(country_code)
        merged["countries"] = countries
    if "remove_countries" in changes:
        remove = set(changes.get("remove_countries") or [])
        merged["countries"] = [code for code in merged.get("countries") or [] if code not in remove]

    if "year" in changes and changes["year"] is not None:
        merged["start_year"] = int(changes["year"])
        merged["end_year"] = int(changes["year"])
    else:
        for key in ("start_year", "end_year"):
            if key in changes and changes[key] is not None:
                merged[key] = int(changes[key])

    if "limit" in changes and changes["limit"] is not None:
        merged["limit"] = max(1, min(int(changes["limit"]), 50))
    if "ranking_order" in changes and changes["ranking_order"] in {"asc", "desc"}:
        merged["ranking_order"] = changes["ranking_order"]

    if merged.get("indicator") and not merged.get("indicators"):
        merged["indicators"] = [merged["indicator"]]
    if merged.get("indicators") and not merged.get("indicator"):
        merged["indicator"] = merged["indicators"][0]

    return merged
