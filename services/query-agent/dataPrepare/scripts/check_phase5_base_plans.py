import json
from collections import Counter
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT_DIR / "configs"
DATASET_DIR = ROOT_DIR / "datasets" / "parser"
BASE_PLANS_PATH = DATASET_DIR / "base_plans.v1.jsonl"
REPORT_PATH = DATASET_DIR / "base_plans_report.v1.json"

BASE_PLAN_FIELDS = {
    "plan_group_id",
    "version",
    "intent",
    "question_family",
    "priority",
    "generation_bucket",
    "target_sample_count",
    "parsed_query",
    "render_context",
    "constraints",
}
CONSTRAINT_FIELDS = {
    "requires_analytics",
    "requires_anomaly",
    "requires_cluster",
    "requires_multi_country",
    "requires_multi_indicator",
}


def load_json(path):
    full_path = CONFIG_DIR / path
    with full_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def fail(message):
    raise SystemExit(f"Phase 5 base plan check failed: {message}")


def read_jsonl(path):
    if not path.exists():
        fail(f"missing base plans file: {path}")
    plans = []
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                fail(f"empty line in JSONL at line {line_number}")
            try:
                plans.append(json.loads(line))
            except json.JSONDecodeError as exc:
                fail(f"invalid JSONL at line {line_number}: {exc}")
    if not plans:
        fail("base_plans.v1.jsonl is empty")
    return plans


def validate_basic_plan_structure(plan, line_number, generation_buckets):
    missing = sorted(BASE_PLAN_FIELDS - set(plan))
    if missing:
        fail(f"plan line {line_number} missing fields: {missing}")
    extra = sorted(set(plan) - BASE_PLAN_FIELDS)
    if extra:
        fail(f"plan line {line_number} has extra fields: {extra}")

    if not isinstance(plan["plan_group_id"], str) or not plan["plan_group_id"]:
        fail(f"plan line {line_number} has invalid plan_group_id")
    if not isinstance(plan["target_sample_count"], int) or plan["target_sample_count"] <= 0:
        fail(f"{plan['plan_group_id']} target_sample_count must be positive integer")
    if plan["generation_bucket"] not in generation_buckets:
        fail(f"{plan['plan_group_id']} has invalid generation_bucket: {plan['generation_bucket']}")
    if not isinstance(plan["parsed_query"], dict):
        fail(f"{plan['plan_group_id']} parsed_query must be object")
    if not isinstance(plan["render_context"], dict):
        fail(f"{plan['plan_group_id']} render_context must be object")
    if not isinstance(plan["constraints"], dict):
        fail(f"{plan['plan_group_id']} constraints must be object")
    missing_constraints = sorted(CONSTRAINT_FIELDS - set(plan["constraints"]))
    if missing_constraints:
        fail(f"{plan['plan_group_id']} constraints missing: {missing_constraints}")
    for key in CONSTRAINT_FIELDS:
        if not isinstance(plan["constraints"][key], bool):
            fail(f"{plan['plan_group_id']} constraints.{key} must be boolean")


def validate_parsed_query(
    plan,
    parsed_query_fields,
    parser_enums,
    country_codes,
    indicator_codes,
    family_meta,
    indicator_by_code,
    cluster_years,
):
    plan_id = plan["plan_group_id"]
    parsed_query = plan["parsed_query"]
    missing = sorted(set(parsed_query_fields) - set(parsed_query))
    extra = sorted(set(parsed_query) - set(parsed_query_fields))
    if missing:
        fail(f"{plan_id} parsed_query missing fields: {missing}")
    if extra:
        fail(f"{plan_id} parsed_query has extra fields: {extra}")

    if parsed_query["intent"] != plan["intent"]:
        fail(f"{plan_id} parsed_query.intent does not match plan intent")
    if parsed_query["question_family"] != plan["question_family"]:
        fail(f"{plan_id} parsed_query.question_family does not match plan question_family")

    for field in ("indicators", "countries", "country_groups", "clarification_questions"):
        if not isinstance(parsed_query[field], list):
            fail(f"{plan_id} parsed_query.{field} must be list")
    if not isinstance(parsed_query["needs_clarification"], bool):
        fail(f"{plan_id} parsed_query.needs_clarification must be bool")
    if not isinstance(parsed_query["confidence"], (int, float)) or not 0 <= parsed_query["confidence"] <= 1:
        fail(f"{plan_id} parsed_query.confidence must be number in [0,1]")
    for field in ("start_year", "end_year"):
        value = parsed_query[field]
        if value is not None and not isinstance(value, int):
            fail(f"{plan_id} parsed_query.{field} must be int or null")
        if value is not None and not 1900 <= value <= 2100:
            fail(f"{plan_id} parsed_query.{field} outside schema range: {value}")
    if (
        parsed_query["start_year"] is not None
        and parsed_query["end_year"] is not None
        and parsed_query["start_year"] > parsed_query["end_year"]
    ):
        fail(f"{plan_id} start_year > end_year")

    invalid_countries = sorted(set(parsed_query["countries"]) - country_codes)
    if invalid_countries:
        fail(f"{plan_id} has unknown countries: {invalid_countries}")
    invalid_indicators = sorted(set(parsed_query["indicators"]) - indicator_codes)
    if invalid_indicators:
        fail(f"{plan_id} has unknown indicators: {invalid_indicators}")
    invalid_groups = sorted(set(parsed_query["country_groups"]) - set(parser_enums["country_groups"]))
    if invalid_groups:
        fail(f"{plan_id} has unknown country_groups: {invalid_groups}")

    for field, enum_name in (
        ("chart_preference", "chart_preference"),
        ("ranking_order", "ranking_order"),
        ("aggregation", "aggregation"),
        ("relative_time", "relative_time"),
        ("event_time", "event_time"),
    ):
        if parsed_query[field] not in parser_enums[enum_name]:
            fail(f"{plan_id} parsed_query.{field} not in enum {enum_name}: {parsed_query[field]}")

    intent = plan["intent"]
    family_id = plan["question_family"]
    if intent == "NEED_CLARIFICATION":
        if parsed_query["needs_clarification"] is not True:
            fail(f"{plan_id} NEED_CLARIFICATION must have needs_clarification=true")
        if not parsed_query["clarification_questions"]:
            fail(f"{plan_id} NEED_CLARIFICATION needs clarification_questions")
    elif parsed_query["needs_clarification"] is not False:
        fail(f"{plan_id} non NEED_CLARIFICATION must have needs_clarification=false")

    if family_id == "missing_indicator" and parsed_query["indicators"]:
        fail(f"{plan_id} missing_indicator must have indicators=[]")
    if family_id in {"missing_country", "ambiguous_country"} and parsed_query["countries"]:
        fail(f"{plan_id} {family_id} must have countries=[]")
    if family_id == "missing_year_for_ranking" and (
        parsed_query["start_year"] is not None or parsed_query["end_year"] is not None
    ):
        fail(f"{plan_id} missing_year_for_ranking must not set years")
    if family_id == "ambiguous_indicator" and parsed_query["indicators"]:
        fail(f"{plan_id} ambiguous_indicator must have indicators=[]")
    if family_id == "ambiguous_time_range" and (
        parsed_query["start_year"] is not None and parsed_query["end_year"] is not None
    ):
        fail(f"{plan_id} ambiguous_time_range must leave a year bound unresolved")

    if intent == "OFF_TOPIC":
        if parsed_query["indicators"] or parsed_query["countries"] or parsed_query["country_groups"]:
            fail(f"{plan_id} OFF_TOPIC must not include indicators/countries/groups")
        if parsed_query["start_year"] is not None or parsed_query["end_year"] is not None:
            fail(f"{plan_id} OFF_TOPIC must not include years")
        if parsed_query["chart_preference"] != "none":
            fail(f"{plan_id} OFF_TOPIC chart_preference must be none")

    if intent == "RANKING":
        if parsed_query["limit"] is None:
            fail(f"{plan_id} RANKING must set limit")
        if parsed_query["ranking_order"] not in {"asc", "desc"}:
            fail(f"{plan_id} RANKING must set ranking_order asc/desc")
    if family_id == "ranking_top_n" and parsed_query["ranking_order"] != "desc":
        fail(f"{plan_id} ranking_top_n must use desc")
    if family_id == "ranking_bottom_n" and parsed_query["ranking_order"] != "asc":
        fail(f"{plan_id} ranking_bottom_n must use asc")

    if intent == "LATEST_VALUE":
        if parsed_query["relative_time"] != "latest" or parsed_query["aggregation"] != "latest":
            fail(f"{plan_id} LATEST_VALUE must use relative_time=latest and aggregation=latest")

    if intent in {"ANOMALY_DETECTION", "ANOMALY_EXPLANATION"}:
        for indicator in parsed_query["indicators"]:
            if not indicator_by_code[indicator]["supports_anomaly"]:
                fail(f"{plan_id} anomaly family uses non-anomaly indicator {indicator}")
    if intent == "TREND_ANALYSIS":
        for indicator in parsed_query["indicators"]:
            if not indicator_by_code[indicator]["supports_trend"]:
                fail(f"{plan_id} trend family uses non-trend indicator {indicator}")
    if plan["question_family"].startswith("cluster_") or intent.startswith("CLUSTER"):
        if plan["constraints"]["requires_cluster"] is not True:
            fail(f"{plan_id} cluster family must set requires_cluster=true")
        if parsed_query["start_year"] is not None and parsed_query["start_year"] not in cluster_years:
            fail(f"{plan_id} cluster start_year must be a cluster target year")
        if parsed_query["end_year"] is not None and parsed_query["end_year"] not in cluster_years:
            fail(f"{plan_id} cluster end_year must be a cluster target year")

    if family_id not in family_meta:
        fail(f"{plan_id} question_family not in question family config")
    if family_meta[family_id]["intent"] != intent:
        fail(f"{plan_id} question_family intent mismatch")


def validate_distribution(plans, dataset_distribution, base_config):
    total = sum(plan["target_sample_count"] for plan in plans)
    if total != dataset_distribution["target_total_samples"]:
        fail(f"total target_sample_count {total} != {dataset_distribution['target_total_samples']}")

    samples_by_intent = Counter()
    samples_by_bucket = Counter()
    groups_by_intent = Counter()
    groups_by_family = Counter()
    for plan in plans:
        samples_by_intent[plan["intent"]] += plan["target_sample_count"]
        samples_by_bucket[plan["generation_bucket"]] += plan["target_sample_count"]
        groups_by_intent[plan["intent"]] += 1
        groups_by_family[plan["question_family"]] += 1

    expected_by_intent = dataset_distribution["intent_targets"]
    if dict(samples_by_intent) != expected_by_intent:
        fail(f"samples by intent mismatch: {dict(samples_by_intent)}")

    warnings = []
    total_float = float(total)
    for bucket, expected_ratio in base_config["generation_buckets"].items():
        actual_ratio = samples_by_bucket[bucket] / total_float
        if abs(actual_ratio - expected_ratio) > 0.08:
            warnings.append(
                f"WARNING generation bucket {bucket} ratio {actual_ratio:.3f} differs from target {expected_ratio:.3f}"
            )

    return samples_by_intent, samples_by_bucket, groups_by_intent, groups_by_family, warnings


def validate_report(report, plans, samples_by_intent, groups_by_intent):
    if report["total_target_samples"] != sum(plan["target_sample_count"] for plan in plans):
        fail("report total_target_samples does not match computed total")
    if report["total_base_plan_groups"] != len(plans):
        fail("report total_base_plan_groups does not match plan count")
    if report["target_samples_by_intent"] != dict(sorted(samples_by_intent.items())):
        fail("report target_samples_by_intent does not match computed values")
    if report["plan_groups_by_intent"] != dict(sorted(groups_by_intent.items())):
        fail("report plan_groups_by_intent does not match computed values")


def main():
    parsed_schema = load_json("parsed_query_schema.v1.json")
    parser_intents = set(load_json("parser_intents.v1.json"))
    parser_enums = load_json("parser_enums.v1.json")
    question_families = load_json("question_families.v1.json")
    dataset_distribution = load_json("dataset_distribution.v1.json")
    country_catalog = load_json("country_catalog.v1.json")
    indicator_catalog = load_json("indicator_catalog.v1.json")
    analytics_metadata = load_json("analytics_metadata.v1.json")
    question_templates = load_json("question_templates.v1.json")
    base_config = load_json("base_plan_generation.v1.json")

    if not REPORT_PATH.exists():
        fail(f"missing base plans report: {REPORT_PATH}")
    with REPORT_PATH.open("r", encoding="utf-8") as file:
        report = json.load(file)

    plans = read_jsonl(BASE_PLANS_PATH)
    generation_buckets = set(base_config["generation_buckets"])
    plan_ids = set()
    family_meta = {family["id"]: family for family in question_families["families"]}
    template_families = set(question_templates["families"])
    country_codes = {country["code"] for country in country_catalog["countries"]}
    indicator_codes = {indicator["code"] for indicator in indicator_catalog["indicators"]}
    indicator_by_code = {indicator["code"]: indicator for indicator in indicator_catalog["indicators"]}
    cluster_years = set(analytics_metadata["cluster"]["target_years"])

    used_countries = set()
    used_indicators = set()
    warnings = []

    for index, plan in enumerate(plans, start=1):
        validate_basic_plan_structure(plan, index, generation_buckets)
        if plan["plan_group_id"] in plan_ids:
            fail(f"duplicate plan_group_id: {plan['plan_group_id']}")
        plan_ids.add(plan["plan_group_id"])
        if plan["intent"] not in parser_intents:
            fail(f"{plan['plan_group_id']} has invalid intent: {plan['intent']}")
        if plan["question_family"] not in family_meta:
            fail(f"{plan['plan_group_id']} has invalid question_family: {plan['question_family']}")
        if plan["question_family"] not in template_families:
            fail(f"{plan['plan_group_id']} question_family has no template")
        if plan["priority"] != family_meta[plan["question_family"]]["priority"]:
            fail(f"{plan['plan_group_id']} priority mismatch")

        validate_parsed_query(
            plan,
            parsed_schema["required"],
            parser_enums,
            country_codes,
            indicator_codes,
            family_meta,
            indicator_by_code,
            cluster_years,
        )
        used_countries.update(plan["parsed_query"]["countries"])
        used_indicators.update(plan["parsed_query"]["indicators"])

    samples_by_intent, samples_by_bucket, groups_by_intent, groups_by_family, bucket_warnings = validate_distribution(
        plans,
        dataset_distribution,
        base_config,
    )
    warnings.extend(bucket_warnings)

    missing_family_plans = sorted(set(family_meta) - set(groups_by_family))
    if missing_family_plans:
        fail(f"families missing base plans: {missing_family_plans}")
    missing_intent_plans = sorted(parser_intents - set(groups_by_intent))
    if missing_intent_plans:
        fail(f"intents missing base plans: {missing_intent_plans}")

    if len(used_countries) < 80:
        warnings.append(f"WARNING unique countries used below 80: {len(used_countries)}")
    if len(used_indicators) < 45:
        warnings.append(f"WARNING unique indicators used below 45: {len(used_indicators)}")

    validate_report(report, plans, samples_by_intent, groups_by_intent)

    for warning in warnings:
        print(warning)
    print(f"total base plan groups: {len(plans)}")
    print(f"total target samples: {sum(plan['target_sample_count'] for plan in plans)}")
    print("samples by intent:")
    for intent in sorted(samples_by_intent):
        print(f"  {intent}: {samples_by_intent[intent]}")
    print("generation bucket totals:")
    for bucket in sorted(samples_by_bucket):
        print(f"  {bucket}: {samples_by_bucket[bucket]}")
    print(f"unique indicators used: {len(used_indicators)}")
    print(f"unique countries used: {len(used_countries)}")
    print(f"warning count: {len(warnings)}")
    print("PASS")


if __name__ == "__main__":
    main()
