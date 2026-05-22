import json
import re
from collections import Counter, defaultdict
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
QUESTION_TEMPLATES_PATH = CONFIG_DIR / "question_templates.v1.json"
BASE_PLANS_PATH = DATASET_DIR / "base_plans.v1.jsonl"
SAMPLES_PATH = DATASET_DIR / "parser_deterministic.v1.jsonl"
REPORT_PATH = DATASET_DIR / "parser_deterministic_report.v1.json"

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
MOJIBAKE_LITERALS = [
    "d? li?u",
    "ch? s?",
    "qu?c",
    "k?t",
    "d??i",
    "d?ng",
    "hi?n",
    "n? cÃ´ng",
    "l?m phÃ¡t",
    "th?t nghi?p",
    "t?ng tr",
    "kh?ng ho?ng",
    "c?nh bÃ¡o",
    "r?i ro",
    "phÃ¢n t?ch",
    "xu h??ng",
]
MOJIBAKE_MARKERS = [
    "Ãƒ",
    "Ã‚Â²",
    "Ã„",
    "Ã¡Â»",
    "Ã¡Âº",
    "Ã†",
    "ï¿½",
]
MOJIBAKE_REGEXES = [
    re.compile(r"[A-Za-z]\?[A-Za-z]"),
    re.compile(r"\?\?"),
    re.compile(r"(?:^|\s)\?[A-Za-z]"),
    re.compile(r"\b(?:d|ch|k|n|l|t|h|qu)\?", re.IGNORECASE),
    re.compile(r"tr\?\?", re.IGNORECASE),
]


def fail(message):
    raise SystemExit(f"Phase 6 deterministic sample check failed: {message}")


def load_json(path):
    if not path.exists():
        fail(f"missing file: {path}")
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def read_jsonl(path, label):
    if not path.exists():
        fail(f"missing {label} file: {path}")
    rows = []
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                fail(f"empty line in {label} JSONL at line {line_number}")
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                fail(f"invalid {label} JSONL at line {line_number}: {exc}")
    if not rows:
        fail(f"{label} JSONL is empty")
    return rows


def has_mojibake(text):
    lowered = text.lower()
    if any(literal.lower() in lowered for literal in MOJIBAKE_LITERALS):
        return True
    if any(marker in text for marker in MOJIBAKE_MARKERS):
        return True
    return any(pattern.search(text) for pattern in MOJIBAKE_REGEXES)


def validate_assistant_json(
    sample,
    plan,
    schema_fields,
    intents,
    enums,
    family_meta,
    country_codes,
    indicator_codes,
):
    sample_id = sample["sample_id"]
    assistant_json = sample["assistant_json"]
    if not isinstance(assistant_json, dict):
        fail(f"{sample_id} assistant_json must be object")
    missing = sorted(schema_fields - set(assistant_json))
    extra = sorted(set(assistant_json) - schema_fields)
    if missing:
        fail(f"{sample_id} assistant_json missing fields: {missing}")
    if extra:
        fail(f"{sample_id} assistant_json has extra fields: {extra}")
    if assistant_json != plan["parsed_query"]:
        fail(f"{sample_id} assistant_json does not exactly match base_plan.parsed_query")
    if assistant_json["intent"] not in intents:
        fail(f"{sample_id} invalid intent: {assistant_json['intent']}")
    if assistant_json["question_family"] not in family_meta:
        fail(f"{sample_id} unknown question_family: {assistant_json['question_family']}")
    if family_meta[assistant_json["question_family"]]["intent"] != assistant_json["intent"]:
        fail(f"{sample_id} question_family intent mismatch")

    for field in ("indicators", "countries", "country_groups", "clarification_questions"):
        if not isinstance(assistant_json[field], list):
            fail(f"{sample_id} assistant_json.{field} must be list")
    if not isinstance(assistant_json["needs_clarification"], bool):
        fail(f"{sample_id} assistant_json.needs_clarification must be bool")
    if not isinstance(assistant_json["confidence"], (int, float)) or not 0 <= assistant_json["confidence"] <= 1:
        fail(f"{sample_id} assistant_json.confidence must be number in [0,1]")

    for field in ("start_year", "end_year"):
        value = assistant_json[field]
        if value is not None and not isinstance(value, int):
            fail(f"{sample_id} assistant_json.{field} must be int or null")
        if value is not None and not 1900 <= value <= 2100:
            fail(f"{sample_id} assistant_json.{field} outside [1900,2100]: {value}")
    if (
        assistant_json["start_year"] is not None
        and assistant_json["end_year"] is not None
        and assistant_json["start_year"] > assistant_json["end_year"]
    ):
        fail(f"{sample_id} start_year > end_year")

    invalid_countries = sorted(set(assistant_json["countries"]) - country_codes)
    if invalid_countries:
        fail(f"{sample_id} unknown countries: {invalid_countries}")
    invalid_indicators = sorted(set(assistant_json["indicators"]) - indicator_codes)
    if invalid_indicators:
        fail(f"{sample_id} unknown indicators: {invalid_indicators}")
    invalid_groups = sorted(set(assistant_json["country_groups"]) - set(enums["country_groups"]))
    if invalid_groups:
        fail(f"{sample_id} unknown country_groups: {invalid_groups}")

    for field, enum_name in (
        ("chart_preference", "chart_preference"),
        ("ranking_order", "ranking_order"),
        ("aggregation", "aggregation"),
        ("relative_time", "relative_time"),
        ("event_time", "event_time"),
    ):
        if assistant_json[field] not in enums[enum_name]:
            fail(f"{sample_id} assistant_json.{field} not in enum {enum_name}: {assistant_json[field]}")


def validate_messages(sample):
    sample_id = sample["sample_id"]
    messages = sample["messages"]
    if not isinstance(messages, list) or len(messages) != 3:
        fail(f"{sample_id} messages must be length 3")
    roles = [message.get("role") for message in messages if isinstance(message, dict)]
    if roles != ["system", "user", "assistant"]:
        fail(f"{sample_id} message roles must be system/user/assistant")
    if messages[1].get("content") != sample["user_message"]:
        fail(f"{sample_id} messages[1].content does not equal user_message")
    try:
        parsed_content = json.loads(messages[2].get("content"))
    except (TypeError, json.JSONDecodeError) as exc:
        fail(f"{sample_id} messages[2].content is not valid JSON: {exc}")
    if parsed_content != sample["assistant_json"]:
        fail(f"{sample_id} parsed assistant content does not equal assistant_json")


def validate_user_message(sample):
    sample_id = sample["sample_id"]
    user_message = sample["user_message"]
    if not isinstance(user_message, str) or not user_message.strip():
        fail(f"{sample_id} user_message is empty")
    if len(user_message) > 500:
        fail(f"{sample_id} user_message too long: {len(user_message)}")
    if PLACEHOLDER_RE.search(user_message):
        fail(f"{sample_id} user_message contains unrendered placeholder: {user_message}")
    if has_mojibake(user_message):
        fail(f"{sample_id} user_message contains mojibake: {user_message.encode('ascii', errors='backslashreplace')}")


def validate_special_semantics(sample, country_aliases_lower, indicator_codes_lower, warnings):
    user_message = sample["user_message"]
    lowered = user_message.lower()
    intent = sample["intent"]
    family = sample["question_family"]
    sample_id = sample["sample_id"]

    if intent == "OFF_TOPIC":
        domain_keywords = [
            "gdp",
            "nợ công",
            "no cong",
            "inflation",
            "lạm phát",
            "lam phat",
            "unemployment",
            "thất nghiệp",
            "that nghiep",
            "indicator",
            "chỉ số",
            "chi so",
        ]
        if any(keyword in lowered for keyword in domain_keywords):
            warnings.append(f"{sample_id} OFF_TOPIC may contain domain keyword")
        if any(alias and alias in lowered for alias in country_aliases_lower):
            warnings.append(f"{sample_id} OFF_TOPIC may contain country alias")

    if intent == "NEED_CLARIFICATION":
        if family in {"missing_indicator", "ambiguous_indicator"}:
            if any(code and code in lowered for code in indicator_codes_lower):
                warnings.append(f"{sample_id} NEED_CLARIFICATION missing indicator may contain indicator code")
        if family in {"missing_country", "ambiguous_country"}:
            if any(alias and alias in lowered for alias in country_aliases_lower):
                warnings.append(f"{sample_id} NEED_CLARIFICATION missing country may contain country alias")


def validate_report(report, samples, samples_by_intent, samples_by_language_style, samples_by_family):
    computed_total = len(samples)
    if report.get("total_samples") != computed_total:
        fail(f"report total_samples {report.get('total_samples')} != computed {computed_total}")
    if report.get("samples_by_intent") != dict(sorted(samples_by_intent.items())):
        fail("report samples_by_intent does not match computed values")
    if report.get("samples_by_language_style") != dict(sorted(samples_by_language_style.items())):
        fail("report samples_by_language_style does not match computed values")
    if report.get("samples_by_family") != dict(sorted(samples_by_family.items())):
        fail("report samples_by_family does not match computed values")


def build_alias_sets(country_catalog, indicator_catalog):
    country_aliases = set()
    for country in country_catalog["countries"]:
        country_aliases.add(country["code"].lower())
        country_aliases.add(country["name"].lower())
        for alias in country.get("aliases") or []:
            if len(alias) >= 3:
                country_aliases.add(alias.lower())
        for alias in (country.get("question_templates_hint") or {}).values():
            if isinstance(alias, str) and len(alias) >= 3:
                country_aliases.add(alias.lower())

    indicator_codes = {indicator["code"].lower() for indicator in indicator_catalog["indicators"]}
    return country_aliases, indicator_codes


def main():
    schema = load_json(SCHEMA_PATH)
    intents = set(load_json(INTENTS_PATH))
    enums = load_json(ENUMS_PATH)
    question_families = load_json(QUESTION_FAMILIES_PATH)
    country_catalog = load_json(COUNTRY_CATALOG_PATH)
    indicator_catalog = load_json(INDICATOR_CATALOG_PATH)
    templates = load_json(QUESTION_TEMPLATES_PATH)
    base_plans = read_jsonl(BASE_PLANS_PATH, "base plans")
    samples = read_jsonl(SAMPLES_PATH, "deterministic samples")
    report = load_json(REPORT_PATH)

    schema_fields = set(schema["required"])
    language_styles = set(templates["template_language_styles"])
    family_meta = {family["id"]: family for family in question_families["families"]}
    country_codes = {country["code"] for country in country_catalog["countries"]}
    indicator_codes = {indicator["code"] for indicator in indicator_catalog["indicators"]}
    country_aliases_lower, indicator_codes_lower = build_alias_sets(country_catalog, indicator_catalog)

    base_by_id = {plan["plan_group_id"]: plan for plan in base_plans}
    deterministic_plan_ids = {
        plan["plan_group_id"] for plan in base_plans if plan["generation_bucket"] == "deterministic_template"
    }
    expected_total = sum(
        plan["target_sample_count"] for plan in base_plans if plan["generation_bucket"] == "deterministic_template"
    )
    expected_counts_by_plan = {
        plan["plan_group_id"]: plan["target_sample_count"]
        for plan in base_plans
        if plan["generation_bucket"] == "deterministic_template"
    }

    sample_ids = set()
    samples_by_plan = Counter()
    samples_by_intent = Counter()
    samples_by_family = Counter()
    samples_by_language_style = Counter()
    user_messages = Counter()
    messages_by_plan = defaultdict(set)
    warnings = []

    for line_number, sample in enumerate(samples, start=1):
        missing = sorted(SAMPLE_FIELDS - set(sample))
        if missing:
            fail(f"sample line {line_number} missing fields: {missing}")
        sample_id = sample["sample_id"]
        if sample_id in sample_ids:
            fail(f"duplicate sample_id: {sample_id}")
        sample_ids.add(sample_id)

        plan_id = sample["plan_group_id"]
        if plan_id not in base_by_id:
            fail(f"{sample_id} plan_group_id does not exist in base_plans: {plan_id}")
        plan = base_by_id[plan_id]
        if plan_id not in deterministic_plan_ids:
            fail(f"{sample_id} renders non-deterministic base plan: {plan_id}")
        if sample["generation_source"] != "deterministic_template":
            fail(f"{sample_id} invalid generation_source: {sample['generation_source']}")
        if sample["intent"] != plan["intent"] or sample["question_family"] != plan["question_family"]:
            fail(f"{sample_id} intent/question_family do not match base plan")
        if sample["intent"] != sample["assistant_json"].get("intent"):
            fail(f"{sample_id} intent does not match assistant_json.intent")
        if sample["question_family"] != sample["assistant_json"].get("question_family"):
            fail(f"{sample_id} question_family does not match assistant_json.question_family")
        if sample["language_style"] not in language_styles:
            fail(f"{sample_id} invalid language_style: {sample['language_style']}")

        validate_messages(sample)
        validate_user_message(sample)
        validate_assistant_json(
            sample,
            plan,
            schema_fields,
            intents,
            enums,
            family_meta,
            country_codes,
            indicator_codes,
        )
        validate_special_semantics(sample, country_aliases_lower, indicator_codes_lower, warnings)

        if sample["user_message"] in messages_by_plan[plan_id]:
            fail(f"{sample_id} duplicate user_message within plan_group_id {plan_id}")
        messages_by_plan[plan_id].add(sample["user_message"])

        samples_by_plan[plan_id] += 1
        samples_by_intent[sample["intent"]] += 1
        samples_by_family[sample["question_family"]] += 1
        samples_by_language_style[sample["language_style"]] += 1
        user_messages[sample["user_message"]] += 1

    if len(samples) != expected_total:
        fail(f"sample count {len(samples)} != deterministic target {expected_total}")
    for plan_id, expected_count in expected_counts_by_plan.items():
        actual_count = samples_by_plan.get(plan_id, 0)
        if actual_count != expected_count:
            fail(f"{plan_id} sample count {actual_count} != target_sample_count {expected_count}")
    unexpected_plan_ids = sorted(set(samples_by_plan) - deterministic_plan_ids)
    if unexpected_plan_ids:
        fail(f"rendered unexpected plan ids: {unexpected_plan_ids[:10]}")

    duplicate_user_messages = sum(count - 1 for count in user_messages.values() if count > 1)
    if duplicate_user_messages:
        warnings.append(f"global duplicate user messages: {duplicate_user_messages}")
    if duplicate_user_messages > max(1, int(0.01 * len(samples))):
        fail(f"global duplicate user messages exceed 1%: {duplicate_user_messages}")

    validate_report(report, samples, samples_by_intent, samples_by_language_style, samples_by_family)

    print(f"total samples: {len(samples)}")
    print(f"total plan groups used: {len(samples_by_plan)}")
    print(f"samples by language style: {dict(sorted(samples_by_language_style.items()))}")
    print(f"unique user messages: {len(user_messages)}")
    print(f"duplicate user messages: {duplicate_user_messages}")
    print(f"warning count: {len(warnings)}")
    for warning in warnings[:20]:
        print(f"WARNING {warning}")
    print("PASS")


if __name__ == "__main__":
    main()
