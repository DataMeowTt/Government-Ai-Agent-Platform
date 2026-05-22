import json
import re
from collections import Counter
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT_DIR / "configs"
DATASET_DIR = ROOT_DIR / "datasets" / "parser"

CONFIG_PATH = CONFIG_DIR / "paraphrase_generation.v1.json"
SCHEMA_PATH = CONFIG_DIR / "parsed_query_schema.v1.json"
INTENTS_PATH = CONFIG_DIR / "parser_intents.v1.json"
ENUMS_PATH = CONFIG_DIR / "parser_enums.v1.json"
QUESTION_FAMILIES_PATH = CONFIG_DIR / "question_families.v1.json"
COUNTRY_CATALOG_PATH = CONFIG_DIR / "country_catalog.v1.json"
INDICATOR_CATALOG_PATH = CONFIG_DIR / "indicator_catalog.v1.json"
BASE_PLANS_PATH = DATASET_DIR / "base_plans.v1.jsonl"
DETERMINISTIC_PATH = DATASET_DIR / "parser_deterministic.v1.jsonl"
SAMPLES_PATH = DATASET_DIR / "parser_paraphrase.v1.jsonl"
REPORT_PATH = DATASET_DIR / "parser_paraphrase_report.v1.json"

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


def fail(message):
    raise SystemExit(f"Phase 7 paraphrase sample check failed: {message}")


def load_json(path):
    if not path.exists():
        fail(f"missing file: {path}")
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def read_jsonl(path, label, required=True, allow_empty=False):
    if not path.exists():
        if required:
            print("No paraphrase samples imported yet. Run export, fill paraphrase_outputs, then run import.")
            raise SystemExit(1)
        return []
    rows = []
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                fail(f"empty line in {label} JSONL at line {line_number}")
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                fail(f"invalid {label} JSONL at line {line_number}: {exc}")
    if not rows and not allow_empty:
        fail(f"{label} JSONL is empty")
    return rows


def has_mojibake(text):
    if any(marker in text for marker in MOJIBAKE_MARKERS):
        return True
    return any(pattern.search(text) for pattern in MOJIBAKE_REGEXES)


def validate_messages(sample):
    sample_id = sample["sample_id"]
    messages = sample["messages"]
    if not isinstance(messages, list) or len(messages) != 3:
        fail(f"{sample_id} messages must be length 3")
    roles = [message.get("role") for message in messages if isinstance(message, dict)]
    if roles != ["system", "user", "assistant"]:
        fail(f"{sample_id} message roles must be system/user/assistant")
    if messages[1].get("content") != sample["user_message"]:
        fail(f"{sample_id} messages[1].content != user_message")
    try:
        assistant_content = json.loads(messages[2].get("content"))
    except (TypeError, json.JSONDecodeError) as exc:
        fail(f"{sample_id} assistant content is not valid JSON: {exc}")
    if assistant_content != sample["assistant_json"]:
        fail(f"{sample_id} assistant content != assistant_json")


def validate_assistant_json(sample, plan, schema_fields, intents, enums, families, country_codes, indicator_codes):
    sample_id = sample["sample_id"]
    assistant_json = sample["assistant_json"]
    if assistant_json != plan["parsed_query"]:
        fail(f"{sample_id} assistant_json does not exactly equal base_plan.parsed_query")
    missing = sorted(schema_fields - set(assistant_json))
    extra = sorted(set(assistant_json) - schema_fields)
    if missing:
        fail(f"{sample_id} assistant_json missing fields: {missing}")
    if extra:
        fail(f"{sample_id} assistant_json has extra fields: {extra}")
    if assistant_json["intent"] not in intents:
        fail(f"{sample_id} invalid intent: {assistant_json['intent']}")
    if assistant_json["question_family"] not in families:
        fail(f"{sample_id} invalid question_family: {assistant_json['question_family']}")
    for field in ("chart_preference", "ranking_order", "aggregation", "relative_time", "event_time"):
        if assistant_json[field] not in enums[field]:
            fail(f"{sample_id} assistant_json.{field} invalid enum value: {assistant_json[field]}")
    invalid_countries = sorted(set(assistant_json["countries"]) - country_codes)
    if invalid_countries:
        fail(f"{sample_id} unknown countries: {invalid_countries}")
    invalid_indicators = sorted(set(assistant_json["indicators"]) - indicator_codes)
    if invalid_indicators:
        fail(f"{sample_id} unknown indicators: {invalid_indicators}")
    invalid_groups = sorted(set(assistant_json["country_groups"]) - set(enums["country_groups"]))
    if invalid_groups:
        fail(f"{sample_id} unknown country_groups: {invalid_groups}")


def validate_user_message(sample, deterministic_messages):
    sample_id = sample["sample_id"]
    user_message = sample["user_message"]
    if not isinstance(user_message, str) or not user_message.strip():
        fail(f"{sample_id} user_message is empty")
    if len(user_message) > 500:
        fail(f"{sample_id} user_message too long: {len(user_message)}")
    if PLACEHOLDER_RE.search(user_message):
        fail(f"{sample_id} user_message contains placeholder")
    if has_mojibake(user_message):
        fail(f"{sample_id} user_message contains mojibake")
    if user_message in deterministic_messages:
        fail(f"{sample_id} duplicates deterministic user_message")


def validate_report(report, target_samples, samples, samples_by_intent, samples_by_language_style):
    if report.get("target_samples") != target_samples:
        fail(f"report target_samples {report.get('target_samples')} != computed {target_samples}")
    if report.get("imported_samples") != len(samples):
        fail(f"report imported_samples {report.get('imported_samples')} != computed {len(samples)}")
    if report.get("samples_by_intent") != dict(sorted(samples_by_intent.items())):
        fail("report samples_by_intent does not match computed values")
    if report.get("samples_by_language_style") != dict(sorted(samples_by_language_style.items())):
        fail("report samples_by_language_style does not match computed values")


def main():
    config = load_json(CONFIG_PATH)
    schema = load_json(SCHEMA_PATH)
    intents = set(load_json(INTENTS_PATH))
    enums = load_json(ENUMS_PATH)
    question_families = load_json(QUESTION_FAMILIES_PATH)
    country_catalog = load_json(COUNTRY_CATALOG_PATH)
    indicator_catalog = load_json(INDICATOR_CATALOG_PATH)
    base_plans = read_jsonl(BASE_PLANS_PATH, "base plans")
    deterministic_samples = read_jsonl(DETERMINISTIC_PATH, "deterministic samples", required=False, allow_empty=True)
    samples = read_jsonl(SAMPLES_PATH, "paraphrase samples", required=True, allow_empty=True)
    report = load_json(REPORT_PATH)

    target_bucket = config["target_generation_bucket"]
    target_plans = [plan for plan in base_plans if plan["generation_bucket"] == target_bucket]
    target_samples = sum(plan["target_sample_count"] for plan in target_plans)
    base_by_id = {plan["plan_group_id"]: plan for plan in target_plans}
    schema_fields = set(schema["required"])
    family_ids = {family["id"] for family in question_families["families"]}
    country_codes = {country["code"] for country in country_catalog["countries"]}
    indicator_codes = {indicator["code"] for indicator in indicator_catalog["indicators"]}
    deterministic_messages = {sample["user_message"] for sample in deterministic_samples}
    language_styles = set(config["language_mix"])

    sample_ids = set()
    user_messages = set()
    duplicate_count = 0
    samples_by_intent = Counter()
    samples_by_language_style = Counter()
    countries = Counter()
    indicators = Counter()
    warnings = []

    for line_number, sample in enumerate(samples, start=1):
        missing = sorted(SAMPLE_FIELDS - set(sample))
        if missing:
            fail(f"sample line {line_number} missing fields: {missing}")
        sample_id = sample["sample_id"]
        if sample_id in sample_ids:
            fail(f"duplicate sample_id: {sample_id}")
        sample_ids.add(sample_id)
        if sample["generation_source"] != "llm_paraphrase":
            fail(f"{sample_id} generation_source must be llm_paraphrase")
        if sample["language_style"] not in language_styles:
            fail(f"{sample_id} invalid language_style: {sample['language_style']}")
        plan_id = sample["plan_group_id"]
        if plan_id not in base_by_id:
            fail(f"{sample_id} plan_group_id is not llm_paraphrase base plan: {plan_id}")
        plan = base_by_id[plan_id]
        if sample["intent"] != plan["intent"] or sample["question_family"] != plan["question_family"]:
            fail(f"{sample_id} intent/question_family mismatch with base plan")
        validate_messages(sample)
        validate_user_message(sample, deterministic_messages)
        validate_assistant_json(sample, plan, schema_fields, intents, enums, family_ids, country_codes, indicator_codes)

        if sample["user_message"] in user_messages:
            duplicate_count += 1
        user_messages.add(sample["user_message"])
        samples_by_intent[sample["intent"]] += 1
        samples_by_language_style[sample["language_style"]] += 1
        for country in sample["assistant_json"].get("countries") or []:
            countries[country] += 1
        for indicator in sample["assistant_json"].get("indicators") or []:
            indicators[indicator] += 1

    if duplicate_count:
        fail(f"duplicate paraphrase user_messages: {duplicate_count}")

    fill_rate = len(samples) / target_samples if target_samples else 0
    if len(samples) < int(target_samples * 0.95):
        fail(f"imported_samples {len(samples)} below 95% target {target_samples}; need more paraphrase outputs")

    if len(samples) >= int(target_samples * 0.95):
        if len(countries) < 70:
            warnings.append(f"unique countries low: {len(countries)}")
        if len(indicators) < 40:
            warnings.append(f"unique indicators low: {len(indicators)}")

    validate_report(report, target_samples, samples, samples_by_intent, samples_by_language_style)

    report_warning_count = len(report.get("warnings") or [])
    warning_count = len(warnings) + report_warning_count
    print(f"target samples: {target_samples}")
    print(f"imported samples: {len(samples)}")
    print(f"fill rate: {fill_rate:.3f}")
    print(f"unique messages: {len(user_messages)}")
    print(f"duplicate count: {duplicate_count}")
    print(f"samples by language style: {dict(sorted(samples_by_language_style.items()))}")
    print(f"dropped variants from report: {report.get('dropped_variants', 0)}")
    print(
        "requests attempted/succeeded/failed: "
        f"{report.get('requests_attempted', 0)}/"
        f"{report.get('requests_succeeded', 0)}/"
        f"{report.get('requests_failed', 0)}"
    )
    print(f"warning count: {warning_count}")
    for warning in warnings[:20]:
        print(f"WARNING {warning}")
    print("PASS")


if __name__ == "__main__":
    main()
