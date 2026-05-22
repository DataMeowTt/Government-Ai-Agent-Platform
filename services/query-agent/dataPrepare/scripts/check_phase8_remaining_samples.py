import json
import re
from collections import Counter
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT_DIR / "configs"
DATASET_DIR = ROOT_DIR / "datasets" / "parser"

SCHEMA_PATH = CONFIG_DIR / "parsed_query_schema.v1.json"
INTENTS_PATH = CONFIG_DIR / "parser_intents.v1.json"
ENUMS_PATH = CONFIG_DIR / "parser_enums.v1.json"
QUESTION_FAMILIES_PATH = CONFIG_DIR / "question_families.v1.json"
COUNTRY_CATALOG_PATH = CONFIG_DIR / "country_catalog.v1.json"
INDICATOR_CATALOG_PATH = CONFIG_DIR / "indicator_catalog.v1.json"
HARD_CONFIG_PATH = CONFIG_DIR / "hard_case_generation.v1.json"
OFFUNS_CONFIG_PATH = CONFIG_DIR / "offtopic_unsupported_generation.v1.json"
BASE_PLANS_PATH = DATASET_DIR / "base_plans.v1.jsonl"
DETERMINISTIC_PATH = DATASET_DIR / "parser_deterministic.v1.jsonl"
PARAPHRASE_PATH = DATASET_DIR / "parser_paraphrase.v1.jsonl"
HARD_PATH = DATASET_DIR / "parser_hard_cases.v1.jsonl"
HARD_REPORT_PATH = DATASET_DIR / "parser_hard_cases_report.v1.json"
OFFUNS_PATH = DATASET_DIR / "parser_offtopic_unsupported.v1.jsonl"
OFFUNS_REPORT_PATH = DATASET_DIR / "parser_offtopic_unsupported_report.v1.json"

SAMPLE_FIELDS = {
    "sample_id",
    "plan_group_id",
    "version",
    "generation_source",
    "intent",
    "question_family",
    "language_style",
    "user_message",
    "assistant_json",
    "messages",
    "render_metadata",
}

PLACEHOLDER_RE = re.compile(r"{[^{}]+}")
MOJIBAKE_MARKERS = ["Ãƒ", "Ã‚", "Ã„", "Ã¡Â", "Ã†", "ï¿½"]
MOJIBAKE_REGEXES = [
    re.compile(r"[A-Za-z]\?[A-Za-z]"),
    re.compile(r"\?\?"),
    re.compile(r"(?:^|\s)\?[A-Za-z]"),
    re.compile(r"\b(?:d|ch|k|n|l|t|h|qu)\?", re.IGNORECASE),
]
ARTIFACT_PATTERNS = [
    re.compile(r"#\d+"),
    re.compile(r"\b(request|case|sample|id)\s*#?\d+\b", re.IGNORECASE),
    re.compile(r"\b(yeu cau|yêu cầu|mau|mẫu)\s*#?\d+\b", re.IGNORECASE),
]


def fail(message):
    raise SystemExit(f"Phase 8 remaining sample check failed: {message}")


def load_json(path):
    if not path.exists():
        fail(f"missing file: {path}")
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def read_jsonl(path, label):
    if not path.exists():
        fail(f"missing {label}: {path}")
    rows = []
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                fail(f"empty line in {label} at line {line_number}")
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                fail(f"invalid JSONL in {label} line {line_number}: {exc}")
    if not rows:
        fail(f"{label} is empty")
    return rows


def has_mojibake(text):
    if any(marker in text for marker in MOJIBAKE_MARKERS):
        return True
    return any(pattern.search(text) for pattern in MOJIBAKE_REGEXES)


def validate_messages(sample):
    sample_id = sample["sample_id"]
    messages = sample["messages"]
    if not isinstance(messages, list) or len(messages) != 3:
        fail(f"{sample_id} messages must have length 3")
    roles = [message.get("role") for message in messages if isinstance(message, dict)]
    if roles != ["system", "user", "assistant"]:
        fail(f"{sample_id} message roles must be system/user/assistant")
    if messages[1].get("content") != sample["user_message"]:
        fail(f"{sample_id} user message content mismatch")
    try:
        assistant_content = json.loads(messages[2].get("content"))
    except (TypeError, json.JSONDecodeError) as exc:
        fail(f"{sample_id} assistant message is not JSON: {exc}")
    if assistant_content != sample["assistant_json"]:
        fail(f"{sample_id} assistant content != assistant_json")


def validate_user_message(sample):
    sample_id = sample["sample_id"]
    text = sample["user_message"]
    if not isinstance(text, str) or not text.strip():
        fail(f"{sample_id} user_message empty")
    if len(text) > 500:
        fail(f"{sample_id} user_message too long")
    if PLACEHOLDER_RE.search(text):
        fail(f"{sample_id} user_message has placeholder")
    if has_mojibake(text):
        fail(f"{sample_id} user_message has mojibake")
    if any(pattern.search(text) for pattern in ARTIFACT_PATTERNS):
        fail(f"{sample_id} user_message has synthetic numbering artifact: {text}")


def validate_parsed_query(sample, plan, schema_fields, intents, enums, families, country_codes, indicator_codes):
    sample_id = sample["sample_id"]
    parsed = sample["assistant_json"]
    if parsed != plan["parsed_query"]:
        fail(f"{sample_id} assistant_json does not exactly equal base_plan.parsed_query")
    if set(parsed) != schema_fields:
        fail(f"{sample_id} assistant_json fields mismatch")
    if parsed["intent"] not in intents:
        fail(f"{sample_id} invalid intent")
    if parsed["question_family"] not in families:
        fail(f"{sample_id} invalid question_family")
    if parsed["intent"] != plan["intent"] or parsed["question_family"] != plan["question_family"]:
        fail(f"{sample_id} intent/question_family mismatch plan")
    for field, enum_name in (
        ("chart_preference", "chart_preference"),
        ("ranking_order", "ranking_order"),
        ("aggregation", "aggregation"),
        ("relative_time", "relative_time"),
        ("event_time", "event_time"),
    ):
        if parsed[field] not in enums[enum_name]:
            fail(f"{sample_id} invalid enum {field}: {parsed[field]}")
    invalid_countries = sorted(set(parsed["countries"]) - country_codes)
    if invalid_countries:
        fail(f"{sample_id} unknown countries: {invalid_countries}")
    invalid_indicators = sorted(set(parsed["indicators"]) - indicator_codes)
    if invalid_indicators:
        fail(f"{sample_id} unknown indicators: {invalid_indicators}")
    invalid_groups = sorted(set(parsed["country_groups"]) - set(enums["country_groups"]))
    if invalid_groups:
        fail(f"{sample_id} unknown country_groups: {invalid_groups}")

    if parsed["intent"] == "NEED_CLARIFICATION":
        if parsed["needs_clarification"] is not True or not parsed["clarification_questions"]:
            fail(f"{sample_id} NEED_CLARIFICATION label invalid")
    elif parsed["needs_clarification"] is not False:
        fail(f"{sample_id} non clarification must have needs_clarification=false")
    if parsed["intent"] == "OFF_TOPIC":
        if parsed["indicators"] or parsed["countries"] or parsed["country_groups"]:
            fail(f"{sample_id} OFF_TOPIC must have empty indicators/countries/groups")
        if parsed["start_year"] is not None or parsed["end_year"] is not None:
            fail(f"{sample_id} OFF_TOPIC must not include years")
        if parsed["chart_preference"] != "none":
            fail(f"{sample_id} OFF_TOPIC chart_preference must be none")
    if parsed["intent"] == "UNSUPPORTED" and parsed["needs_clarification"] is not False:
        fail(f"{sample_id} UNSUPPORTED must not need clarification")


def computed_counts(samples):
    return {
        "samples_by_intent": dict(sorted(Counter(sample["intent"] for sample in samples).items())),
        "samples_by_family": dict(sorted(Counter(sample["question_family"] for sample in samples).items())),
        "samples_by_language_style": dict(sorted(Counter(sample["language_style"] for sample in samples).items())),
    }


def validate_report(report, samples, target, source):
    if report["generation_source"] != source:
        fail(f"{source} report generation_source mismatch")
    if report["target_samples"] != target:
        fail(f"{source} report target_samples mismatch")
    if report["generated_samples"] != len(samples):
        fail(f"{source} report generated_samples mismatch")
    counts = computed_counts(samples)
    if report["samples_by_intent"] != counts["samples_by_intent"]:
        fail(f"{source} report samples_by_intent mismatch")
    if report["samples_by_language_style"] != counts["samples_by_language_style"]:
        fail(f"{source} report samples_by_language_style mismatch")


def domain_keyword_count(text):
    lowered = text.lower()
    keywords = ["gdp", "nợ công", "no cong", "inflation", "unemployment", "country ranking", "anomaly", "trend"]
    return sum(1 for keyword in keywords if keyword in lowered)


def unsupported_surface_ok(sample):
    text = sample["user_message"].lower()
    family = sample["question_family"]
    if family == "unsupported_raw_sql_request":
        return "sql" in text or "query" in text or "table" in text or "bảng" in text
    if family == "unsupported_arima_modeling":
        return "arima" in text
    if family == "unsupported_causal_claim":
        return any(term in text for term in ["chứng minh", "chung minh", "gây ra", "gay ra", "causal", "prove"])
    if family == "unsupported_no_data_year":
        parsed = sample["assistant_json"]
        year = parsed.get("start_year") or parsed.get("end_year")
        return year is None or str(year) in text
    if family == "unsupported_forecast_advanced":
        return any(term in text for term in ["dự báo", "du bao", "forecast", "mô hình", "mo hinh", "model"])
    return True


def validate_bucket(samples, plans_by_id, expected_bucket, schema_fields, intents, enums, families, country_codes, indicator_codes, warnings):
    artifact_findings = [
        sample
        for sample in samples
        if any(pattern.search(sample.get("user_message", "")) for pattern in ARTIFACT_PATTERNS)
    ]
    if artifact_findings:
        print("synthetic artifact examples:")
        for sample in artifact_findings[:30]:
            print(f"  {sample.get('sample_id')}: {sample.get('user_message')}")
        fail(f"{expected_bucket} has synthetic numbering artifacts: {len(artifact_findings)}")

    sample_ids = set()
    by_plan = Counter()
    for sample in samples:
        missing = sorted(SAMPLE_FIELDS - set(sample))
        if missing:
            fail(f"sample missing fields: {missing}")
        sample_id = sample["sample_id"]
        if sample_id in sample_ids:
            fail(f"duplicate sample_id in {expected_bucket}: {sample_id}")
        sample_ids.add(sample_id)
        if sample["generation_source"] != expected_bucket:
            fail(f"{sample_id} generation_source mismatch")
        plan_id = sample["plan_group_id"]
        if plan_id not in plans_by_id:
            fail(f"{sample_id} unknown plan_group_id {plan_id}")
        plan = plans_by_id[plan_id]
        if plan["generation_bucket"] != expected_bucket:
            fail(f"{sample_id} wrong base_plan generation_bucket")
        validate_messages(sample)
        validate_user_message(sample)
        validate_parsed_query(sample, plan, schema_fields, intents, enums, families, country_codes, indicator_codes)
        by_plan[plan_id] += 1

        if expected_bucket == "hard_cases":
            hard_type = sample.get("hard_case_type")
            if not hard_type:
                fail(f"{sample_id} missing hard_case_type")
            if hard_type == "ambiguous_alias" and not (
                sample["intent"] == "NEED_CLARIFICATION" and sample["question_family"] in {"ambiguous_country", "ambiguous_indicator"}
            ):
                fail(f"{sample_id} ambiguous_alias used outside ambiguous clarification")
            if hard_type == "missing_slot_clarification" and sample["intent"] != "NEED_CLARIFICATION":
                fail(f"{sample_id} missing_slot_clarification used outside NEED_CLARIFICATION")
        else:
            if sample["intent"] == "OFF_TOPIC" and domain_keyword_count(sample["user_message"]):
                warnings.append(f"{sample_id} OFF_TOPIC contains domain keyword")
            if sample["intent"] == "UNSUPPORTED" and not unsupported_surface_ok(sample):
                fail(f"{sample_id} UNSUPPORTED surface does not match unsupported family")
    return by_plan


def main():
    schema = load_json(SCHEMA_PATH)
    intents = set(load_json(INTENTS_PATH))
    enums = load_json(ENUMS_PATH)
    question_families = load_json(QUESTION_FAMILIES_PATH)
    country_catalog = load_json(COUNTRY_CATALOG_PATH)
    indicator_catalog = load_json(INDICATOR_CATALOG_PATH)
    hard_config = load_json(HARD_CONFIG_PATH)
    offuns_config = load_json(OFFUNS_CONFIG_PATH)
    base_plans = read_jsonl(BASE_PLANS_PATH, "base plans")
    deterministic = read_jsonl(DETERMINISTIC_PATH, "deterministic")
    paraphrase = read_jsonl(PARAPHRASE_PATH, "paraphrase")
    hard_samples = read_jsonl(HARD_PATH, "hard cases")
    hard_report = load_json(HARD_REPORT_PATH)
    offuns_samples = read_jsonl(OFFUNS_PATH, "offtopic unsupported")
    offuns_report = load_json(OFFUNS_REPORT_PATH)

    schema_fields = set(schema["required"])
    family_ids = {family["id"] for family in question_families["families"]}
    country_codes = {country["code"] for country in country_catalog["countries"]}
    indicator_codes = {indicator["code"] for indicator in indicator_catalog["indicators"]}
    plans_by_id = {plan["plan_group_id"]: plan for plan in base_plans}
    hard_target = sum(plan["target_sample_count"] for plan in base_plans if plan["generation_bucket"] == "hard_cases")
    offuns_target = sum(
        plan["target_sample_count"] for plan in base_plans if plan["generation_bucket"] == "off_topic_unsupported"
    )
    warnings = []

    hard_by_plan = validate_bucket(
        hard_samples, plans_by_id, "hard_cases", schema_fields, intents, enums, family_ids, country_codes, indicator_codes, warnings
    )
    offuns_by_plan = validate_bucket(
        offuns_samples,
        plans_by_id,
        "off_topic_unsupported",
        schema_fields,
        intents,
        enums,
        family_ids,
        country_codes,
        indicator_codes,
        warnings,
    )
    for plan in base_plans:
        if plan["generation_bucket"] == "hard_cases" and hard_by_plan[plan["plan_group_id"]] != plan["target_sample_count"]:
            fail(f"{plan['plan_group_id']} hard count mismatch")
        if (
            plan["generation_bucket"] == "off_topic_unsupported"
            and offuns_by_plan[plan["plan_group_id"]] != plan["target_sample_count"]
        ):
            fail(f"{plan['plan_group_id']} off_topic_unsupported count mismatch")

    validate_report(hard_report, hard_samples, hard_target, "hard_cases")
    validate_report(offuns_report, offuns_samples, offuns_target, "off_topic_unsupported")
    if hard_target != hard_config["target_samples"]:
        warnings.append(f"hard config target {hard_config['target_samples']} != computed {hard_target}")
    if offuns_target != offuns_config["target_samples"]:
        warnings.append(f"offuns config target {offuns_config['target_samples']} != computed {offuns_target}")

    all_sample_ids = {sample["sample_id"] for sample in hard_samples}
    if all_sample_ids & {sample["sample_id"] for sample in offuns_samples}:
        fail("sample_id collision between hard and offuns")

    base_messages = Counter(sample["user_message"] for sample in deterministic + paraphrase)
    remaining_messages = Counter(sample["user_message"] for sample in hard_samples + offuns_samples)
    duplicate_count = 0
    for message, count in remaining_messages.items():
        if count > 1:
            duplicate_count += count - 1
        if message in base_messages:
            duplicate_count += count
    if duplicate_count:
        fail(f"duplicate user_message count: {duplicate_count}")

    projected_total = len(deterministic) + len(paraphrase) + len(hard_samples) + len(offuns_samples)
    print(f"hard target/generated: {hard_target}/{len(hard_samples)}")
    print(f"off_topic_unsupported target/generated: {offuns_target}/{len(offuns_samples)}")
    print(f"combined remaining generated: {len(hard_samples) + len(offuns_samples)}")
    print(f"projected full dataset total: {projected_total}")
    print(f"duplicate count: {duplicate_count}")
    print(f"warning count: {len(warnings)}")
    for warning in warnings[:20]:
        print(f"WARNING {warning}")
    print("PASS")


if __name__ == "__main__":
    main()
