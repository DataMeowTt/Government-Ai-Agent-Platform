import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
EXPECTED_COUNTRY_COUNT = 88
EXPECTED_ANALYTICS_SUFFIXES = {
    "actual",
    "trend",
    "residual",
    "slope",
    "intercept",
    "r2",
    "anomaly_score",
}
EXPECTED_CLUSTER_YEARS = [2000, 2010, 2020, 2022]
REQUIRED_LANGUAGE_STYLES = {
    "vi",
    "vi_no_diacritics",
    "en",
    "mixed_vi_en",
    "technical_code",
    "short_chat",
}
ALLOWED_INDICATOR_CATEGORIES = {
    "growth_dynamics",
    "structural_composition",
    "fiscal_monetary",
    "crisis_risk",
    "social_welfare",
    "quality",
}


def load_json(relative_path):
    path = ROOT_DIR / relative_path
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError as exc:
        raise SystemExit(f"Missing required config: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {path}: {exc}") from exc


def fail(message):
    raise SystemExit(f"Phase 3 catalog check failed: {message}")


def normalize_alias(alias):
    value = alias.lower().strip().replace("_", " ")
    value = value.replace("đ", "d").replace("Đ", "d")
    value = unicodedata.normalize("NFD", value)
    value = "".join(char for char in value if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", value).strip()


def require_non_empty_string(value, field_name, item_id):
    if not isinstance(value, str) or not value:
        fail(f"{item_id}.{field_name} must be a non-empty string")


def require_aliases(item, item_id):
    aliases = item.get("aliases")
    if not isinstance(aliases, list) or not aliases:
        fail(f"{item_id}.aliases must be a non-empty list")
    invalid_aliases = [alias for alias in aliases if not isinstance(alias, str) or not alias]
    if invalid_aliases:
        fail(f"{item_id}.aliases must contain only non-empty strings: {invalid_aliases}")
    if len(set(aliases)) != len(aliases):
        fail(f"{item_id}.aliases contains duplicate values")
    return aliases


def require_hint_keys(item, item_id, required_keys):
    hint = item.get("question_templates_hint")
    if not isinstance(hint, dict) or not hint:
        fail(f"{item_id}.question_templates_hint must be a non-empty object")
    missing = [key for key in required_keys if not isinstance(hint.get(key), str) or not hint.get(key)]
    if missing:
        fail(f"{item_id}.question_templates_hint missing required keys: {missing}")


def analytics_indicator_map(analytics_metadata):
    tables = analytics_metadata.get("analytics_tables_indicators")
    if not isinstance(tables, dict) or not tables:
        fail("analytics_metadata.analytics_tables_indicators must be a non-empty object")

    code_to_gold_table = {}
    for gold_table, indicators in tables.items():
        require_non_empty_string(gold_table, "gold_table", "analytics_metadata")
        if not isinstance(indicators, list) or not indicators:
            fail(f"analytics_metadata.analytics_tables_indicators.{gold_table} must be a non-empty list")
        for code in indicators:
            require_non_empty_string(code, "indicator_code", f"analytics_metadata[{gold_table}]")
            if code in code_to_gold_table:
                fail(f"analytics indicator appears in multiple tables: {code}")
            code_to_gold_table[code] = gold_table
    return code_to_gold_table


def validate_analytics_metadata(analytics_metadata, indicator_codes):
    anomaly_method = analytics_metadata.get("anomaly_method")
    if not isinstance(anomaly_method, dict):
        fail("analytics_metadata.anomaly_method must be an object")
    if anomaly_method.get("default_threshold") != 0.75:
        fail("analytics_metadata.anomaly_method.default_threshold must be 0.75")

    suffixes = analytics_metadata.get("analytics_suffixes")
    if not isinstance(suffixes, list):
        fail("analytics_metadata.analytics_suffixes must be a list")
    missing_suffixes = sorted(EXPECTED_ANALYTICS_SUFFIXES - set(suffixes))
    if missing_suffixes:
        fail(f"analytics_metadata.analytics_suffixes missing: {missing_suffixes}")

    trend_method = analytics_metadata.get("trend_method")
    if not isinstance(trend_method, dict):
        fail("analytics_metadata.trend_method must be an object")
    trend_suffixes = trend_method.get("output_suffixes")
    if not isinstance(trend_suffixes, list):
        fail("analytics_metadata.trend_method.output_suffixes must be a list")
    missing_trend_suffixes = sorted((EXPECTED_ANALYTICS_SUFFIXES - {"anomaly_score"}) - set(trend_suffixes))
    if missing_trend_suffixes:
        fail(f"analytics_metadata.trend_method.output_suffixes missing: {missing_trend_suffixes}")

    anomaly_suffixes = anomaly_method.get("output_suffixes")
    if not isinstance(anomaly_suffixes, list) or "anomaly_score" not in anomaly_suffixes:
        fail("analytics_metadata.anomaly_method.output_suffixes must include anomaly_score")

    cluster = analytics_metadata.get("cluster")
    if not isinstance(cluster, dict):
        fail("analytics_metadata.cluster must be an object")
    if cluster.get("target_years") != EXPECTED_CLUSTER_YEARS:
        fail(f"analytics_metadata.cluster.target_years must be {EXPECTED_CLUSTER_YEARS}")
    if cluster.get("n_clusters") != 5:
        fail("analytics_metadata.cluster.n_clusters must be 5")

    cluster_indicators = cluster.get("indicators")
    if not isinstance(cluster_indicators, list) or not cluster_indicators:
        fail("analytics_metadata.cluster.indicators must be non-empty")

    code_to_gold_table = analytics_indicator_map(analytics_metadata)
    missing_analytics_codes = sorted(set(code_to_gold_table) - indicator_codes)
    if missing_analytics_codes:
        fail(f"analytics indicators missing from indicator_catalog: {missing_analytics_codes}")

    missing_cluster_codes = sorted(set(cluster_indicators) - indicator_codes)
    if missing_cluster_codes:
        fail(f"cluster indicators missing from indicator_catalog: {missing_cluster_codes}")

    return code_to_gold_table, set(cluster_indicators)


def validate_indicator_catalog(indicator_catalog, analytics_codes, cluster_codes):
    indicators = indicator_catalog.get("indicators")
    if not isinstance(indicators, list):
        fail("indicator_catalog.indicators must be a list")

    declared_total = indicator_catalog.get("total_indicators")
    if declared_total != len(indicators):
        fail(
            "indicator_catalog.total_indicators "
            f"({declared_total}) != len(indicators) ({len(indicators)})"
        )

    codes = []
    categories = Counter()
    analytics_supported = 0

    for index, indicator in enumerate(indicators):
        if not isinstance(indicator, dict):
            fail(f"indicator at index {index} must be an object")

        code = indicator.get("code")
        require_non_empty_string(code, "code", f"indicator[{index}]")
        item_id = f"indicator[{code}]"
        codes.append(code)

        for field_name in ("name", "category", "unit", "gold_table", "description"):
            require_non_empty_string(indicator.get(field_name), field_name, item_id)

        if indicator["category"] not in ALLOWED_INDICATOR_CATEGORIES:
            fail(f"{item_id}.category is not allowed: {indicator['category']}")

        require_aliases(indicator, item_id)
        require_hint_keys(indicator, item_id, required_keys=("en", "technical"))

        for field_name in ("supports_trend", "supports_anomaly", "used_for_cluster"):
            if not isinstance(indicator.get(field_name), bool):
                fail(f"{item_id}.{field_name} must be boolean")

        expected_analytics_gold_table = analytics_codes.get(code)
        if expected_analytics_gold_table:
            expected_analytics_table = f"analytics_{expected_analytics_gold_table}"
            if indicator["supports_trend"] is not True or indicator["supports_anomaly"] is not True:
                fail(f"{item_id} is in analytics metadata but trend/anomaly support is not true")
            if indicator.get("analytics_table") != expected_analytics_table:
                fail(
                    f"{item_id}.analytics_table must be {expected_analytics_table}, "
                    f"got {indicator.get('analytics_table')}"
                )
        else:
            if indicator["supports_trend"] or indicator["supports_anomaly"]:
                fail(f"{item_id} is not in analytics metadata but support flag is true")
            if indicator.get("analytics_table") is not None:
                fail(f"{item_id} is not in analytics metadata but analytics_table is not null")

        if code in cluster_codes and indicator["used_for_cluster"] is not True:
            fail(f"{item_id} is in cluster indicators but used_for_cluster is not true")
        if code not in cluster_codes and indicator["used_for_cluster"] is True:
            fail(f"{item_id}.used_for_cluster is true but code is not in cluster metadata")

        categories[indicator["category"]] += 1
        if indicator["supports_trend"] or indicator["supports_anomaly"]:
            analytics_supported += 1

    duplicate_codes = sorted(code for code, count in Counter(codes).items() if count > 1)
    if duplicate_codes:
        fail(f"duplicate indicator codes: {duplicate_codes}")

    return indicators, categories, analytics_supported


def validate_country_catalog(country_catalog):
    countries = country_catalog.get("countries")
    if not isinstance(countries, list):
        fail("country_catalog.countries must be a list")

    declared_total = country_catalog.get("total_countries")
    if declared_total != len(countries):
        fail(
            "country_catalog.total_countries "
            f"({declared_total}) != len(countries) ({len(countries)})"
        )
    if declared_total != EXPECTED_COUNTRY_COUNT:
        fail(f"country_catalog.total_countries must be {EXPECTED_COUNTRY_COUNT}")

    codes = []
    iso3_pattern = re.compile(r"^[A-Z]{3}$")

    for index, country in enumerate(countries):
        if not isinstance(country, dict):
            fail(f"country at index {index} must be an object")

        code = country.get("code")
        require_non_empty_string(code, "code", f"country[{index}]")
        if iso3_pattern.match(code) is None:
            fail(f"country[{code}].code must match ^[A-Z]{{3}}$")

        item_id = f"country[{code}]"
        codes.append(code)
        require_non_empty_string(country.get("name"), "name", item_id)
        if "region" not in country:
            fail(f"{item_id}.region is required")
        require_aliases(country, item_id)
        require_hint_keys(country, item_id, required_keys=("en", "iso3"))
        if country["question_templates_hint"]["iso3"] != code:
            fail(f"{item_id}.question_templates_hint.iso3 must equal code")

    duplicate_codes = sorted(code for code, count in Counter(codes).items() if count > 1)
    if duplicate_codes:
        fail(f"duplicate country codes: {duplicate_codes}")

    return countries


def find_alias_collision_warnings(items, item_type):
    alias_to_codes = defaultdict(set)
    for item in items:
        for alias in item["aliases"]:
            normalized = normalize_alias(alias)
            if normalized:
                alias_to_codes[normalized].add(item["code"])

    warnings = []
    for alias, codes in sorted(alias_to_codes.items()):
        if len(codes) > 1:
            warnings.append(
                f"WARNING {item_type} alias collision: '{alias}' -> {sorted(codes)}"
            )
    return warnings


def validate_alias_generation_rules(alias_rules):
    language_styles = alias_rules.get("language_styles")
    if not isinstance(language_styles, list):
        fail("alias_generation_rules.language_styles must be a list")

    missing_styles = sorted(REQUIRED_LANGUAGE_STYLES - set(language_styles))
    if missing_styles:
        fail(f"alias_generation_rules.language_styles missing: {missing_styles}")

    noise_policy = alias_rules.get("noise_policy")
    if not isinstance(noise_policy, dict):
        fail("alias_generation_rules.noise_policy must be an object")

    typo_rate_max = noise_policy.get("typo_rate_max")
    if not isinstance(typo_rate_max, (int, float)) or not 0 <= typo_rate_max <= 0.1:
        fail("alias_generation_rules.noise_policy.typo_rate_max must be in [0, 0.1]")

    forbidden_rules = alias_rules.get("forbidden_generation_rules")
    if not isinstance(forbidden_rules, list) or not forbidden_rules:
        fail("alias_generation_rules.forbidden_generation_rules must be non-empty")
    if not all(isinstance(rule, str) and rule for rule in forbidden_rules):
        fail("alias_generation_rules.forbidden_generation_rules must contain strings")


def slot_base(slot):
    return slot.split(">=", 1)[0]


def validate_question_family_compatibility(
    question_families, parser_enums, indicator_count, country_count
):
    families = question_families.get("families")
    if not isinstance(families, list):
        fail("question_families.families must be a list")

    required_slot_bases = set()
    for family in families:
        if not isinstance(family, dict):
            fail("question_families.families must contain objects")
        required_slots = family.get("required_slots")
        if not isinstance(required_slots, list):
            fail(f"{family.get('id', '<unknown>')}.required_slots must be a list")
        required_slot_bases.update(
            slot_base(slot) for slot in required_slots if isinstance(slot, str)
        )

    if "indicators" in required_slot_bases and indicator_count < 2:
        fail("question families require indicators but indicator_catalog has fewer than 2")
    if "countries" in required_slot_bases and country_count < 2:
        fail("question families require countries but country_catalog has fewer than 2")
    if "country_groups" in required_slot_bases:
        country_groups = parser_enums.get("country_groups")
        if not isinstance(country_groups, list) or not country_groups:
            fail("question families require country_groups but parser_enums.country_groups is empty")


def main():
    indicator_catalog = load_json("configs/indicator_catalog.v1.json")
    country_catalog = load_json("configs/country_catalog.v1.json")
    alias_rules = load_json("configs/alias_generation_rules.v1.json")
    analytics_metadata = load_json("configs/analytics_metadata.v1.json")
    parser_enums = load_json("configs/parser_enums.v1.json")
    question_families = load_json("configs/question_families.v1.json")

    raw_indicators = indicator_catalog.get("indicators")
    if not isinstance(raw_indicators, list):
        fail("indicator_catalog.indicators must be a list")
    raw_indicator_codes = {
        indicator.get("code")
        for indicator in raw_indicators
        if isinstance(indicator, dict) and isinstance(indicator.get("code"), str)
    }

    analytics_codes, cluster_codes = validate_analytics_metadata(
        analytics_metadata,
        raw_indicator_codes,
    )
    indicators, categories, analytics_supported = validate_indicator_catalog(
        indicator_catalog,
        analytics_codes,
        cluster_codes,
    )
    countries = validate_country_catalog(country_catalog)
    country_warnings = find_alias_collision_warnings(countries, "country")
    indicator_warnings = find_alias_collision_warnings(indicators, "indicator")

    validate_alias_generation_rules(alias_rules)
    validate_question_family_compatibility(
        question_families,
        parser_enums,
        indicator_count=len(indicators),
        country_count=len(countries),
    )

    for warning in country_warnings:
        print(warning)
    for warning in indicator_warnings:
        print(warning)

    print(f"total countries: {len(countries)}")
    print(f"total indicators: {len(indicators)}")
    print("indicator categories count:")
    for category, count in sorted(categories.items()):
        print(f"  {category}: {count}")
    print(f"analytics-supported indicators count: {analytics_supported}")
    print(f"cluster indicators count: {len(cluster_codes)}")
    print(f"countries alias collision warnings count: {len(country_warnings)}")
    print(f"indicators alias collision warnings count: {len(indicator_warnings)}")
    print("PASS")


if __name__ == "__main__":
    main()
