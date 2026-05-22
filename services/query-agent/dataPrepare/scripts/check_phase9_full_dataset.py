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
FAMILIES_PATH = CONFIG_DIR / "question_families.v1.json"
DISTRIBUTION_PATH = CONFIG_DIR / "dataset_distribution.v1.json"
COUNTRY_CATALOG_PATH = CONFIG_DIR / "country_catalog.v1.json"
INDICATOR_CATALOG_PATH = CONFIG_DIR / "indicator_catalog.v1.json"
ANALYTICS_PATH = CONFIG_DIR / "analytics_metadata.v1.json"
BASE_PLANS_PATH = DATASET_DIR / "base_plans.v1.jsonl"
FULL_PATH = DATASET_DIR / "parser_full.v1.jsonl"
REPORT_PATH = DATASET_DIR / "parser_full_report.v1.json"
QUALITY_REPORT_PATH = DATASET_DIR / "parser_full_quality_report.v1.json"

SOURCE_FILES = {
    "deterministic_template": DATASET_DIR / "parser_deterministic.v1.jsonl",
    "llm_paraphrase": DATASET_DIR / "parser_paraphrase.v1.jsonl",
    "hard_cases": DATASET_DIR / "parser_hard_cases.v1.jsonl",
    "off_topic_unsupported": DATASET_DIR / "parser_offtopic_unsupported.v1.jsonl",
}
VALID_GENERATION_SOURCES = set(SOURCE_FILES)
PLACEHOLDER_RE = re.compile(r"{[^{}]+}")
MOJIBAKE_LITERALS = [
    "d? li?u",
    "ch? s?",
    "qu?c",
    "k?t",
    "d??i",
    "d?ng",
    "hi?n",
    "n? công",
    "l?m phát",
    "th?t nghi?p",
    "t?ng tr",
    "kh?ng ho?ng",
    "c?nh báo",
    "r?i ro",
    "phân t?ch",
    "xu h??ng",
]
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


def fail(message, examples=None):
    if examples:
        print("examples:")
        for example in examples[:30]:
            print(f"  {example}")
    raise SystemExit(f"Phase 9 full dataset check failed: {message}")


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
                fail(f"empty line in {label}", [f"line {line_number}"])
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                fail(f"invalid JSONL in {label}", [f"line {line_number}: {exc}"])
    return rows


def has_mojibake(text):
    lowered = text.lower()
    if any(literal.lower() in lowered for literal in MOJIBAKE_LITERALS):
        return True
    if any(marker in text for marker in MOJIBAKE_MARKERS):
        return True
    return any(pattern.search(text) for pattern in MOJIBAKE_REGEXES)


def has_artifact(text):
    return any(pattern.search(text) for pattern in ARTIFACT_PATTERNS)


def validate_messages(sample, quality):
    messages = sample.get("messages")
    if not isinstance(messages, list) or len(messages) != 3:
        quality["chatml_errors"] += 1
        return False
    roles = [message.get("role") for message in messages if isinstance(message, dict)]
    if roles != ["system", "user", "assistant"]:
        quality["chatml_errors"] += 1
        return False
    system_content = messages[0].get("content", "")
    if "semantic parser" not in system_content or "Output only valid JSON" not in system_content:
        quality["chatml_errors"] += 1
        return False
    if messages[1].get("content") != sample.get("user_message"):
        quality["chatml_errors"] += 1
        return False
    try:
        assistant_content = json.loads(messages[2].get("content"))
    except (TypeError, json.JSONDecodeError):
        quality["assistant_json_errors"] += 1
        return False
    if assistant_content != sample.get("assistant_json"):
        quality["assistant_json_errors"] += 1
        return False
    return True


def validate_user_message(sample, quality):
    text = sample.get("user_message")
    ok = True
    if not isinstance(text, str) or not text.strip():
        quality["schema_errors"] += 1
        ok = False
    else:
        if len(text) > 500:
            quality["too_long_messages"] += 1
            ok = False
        if PLACEHOLDER_RE.search(text):
            quality["placeholder_findings"] += 1
            ok = False
        if has_mojibake(text):
            quality["mojibake_findings"] += 1
            ok = False
        if has_artifact(text):
            quality["synthetic_artifact_findings"] += 1
            ok = False
    return ok


def validate_assistant_schema(sample, schema_fields, intents, enums, quality):
    parsed = sample.get("assistant_json")
    if not isinstance(parsed, dict):
        quality["assistant_json_errors"] += 1
        return False
    ok = True
    if set(parsed) != schema_fields:
        quality["schema_errors"] += 1
        ok = False
    if parsed.get("intent") not in intents:
        quality["schema_errors"] += 1
        ok = False
    for field in ("indicators", "countries", "country_groups", "clarification_questions"):
        if not isinstance(parsed.get(field), list):
            quality["schema_errors"] += 1
            ok = False
    for field in ("start_year", "end_year"):
        value = parsed.get(field)
        if value is not None and not isinstance(value, int):
            quality["schema_errors"] += 1
            ok = False
    if not isinstance(parsed.get("needs_clarification"), bool):
        quality["schema_errors"] += 1
        ok = False
    confidence = parsed.get("confidence")
    if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        quality["schema_errors"] += 1
        ok = False
    for field, enum_name in (
        ("chart_preference", "chart_preference"),
        ("ranking_order", "ranking_order"),
        ("aggregation", "aggregation"),
        ("relative_time", "relative_time"),
        ("event_time", "event_time"),
    ):
        if parsed.get(field) not in enums[enum_name]:
            quality["schema_errors"] += 1
            ok = False
    if parsed.get("start_year") is not None and parsed.get("end_year") is not None:
        if parsed["start_year"] > parsed["end_year"]:
            quality["semantic_errors"] += 1
            ok = False
    return ok


def validate_semantics(sample, family_meta, indicator_by_code, cluster_years, quality):
    parsed = sample["assistant_json"]
    intent = parsed["intent"]
    family_id = parsed["question_family"]
    ok = True
    if family_id not in family_meta or family_meta[family_id]["intent"] != intent:
        quality["label_consistency_errors"] += 1
        ok = False
    if intent == "NEED_CLARIFICATION":
        if parsed["needs_clarification"] is not True or not parsed["clarification_questions"]:
            quality["semantic_errors"] += 1
            ok = False
    elif parsed["needs_clarification"] is not False:
        quality["semantic_errors"] += 1
        ok = False
    if intent == "OFF_TOPIC":
        if parsed["indicators"] or parsed["countries"] or parsed["country_groups"]:
            quality["semantic_errors"] += 1
            ok = False
        if parsed["start_year"] is not None or parsed["end_year"] is not None or parsed["chart_preference"] != "none":
            quality["semantic_errors"] += 1
            ok = False
    if intent == "UNSUPPORTED" and parsed["needs_clarification"] is not False:
        quality["semantic_errors"] += 1
        ok = False
    if intent == "RANKING":
        if parsed["limit"] is None or parsed["ranking_order"] not in {"asc", "desc"}:
            quality["semantic_errors"] += 1
            ok = False
    if family_id == "ranking_top_n" and parsed["ranking_order"] != "desc":
        quality["semantic_errors"] += 1
        ok = False
    if family_id == "ranking_bottom_n" and parsed["ranking_order"] != "asc":
        quality["semantic_errors"] += 1
        ok = False
    if intent == "LATEST_VALUE":
        if parsed["relative_time"] != "latest" or parsed["aggregation"] != "latest":
            quality["semantic_errors"] += 1
            ok = False
    if intent in {"ANOMALY_DETECTION", "ANOMALY_EXPLANATION"}:
        for indicator in parsed["indicators"]:
            if not indicator_by_code[indicator]["supports_anomaly"]:
                quality["semantic_errors"] += 1
                ok = False
    if intent == "TREND_ANALYSIS":
        for indicator in parsed["indicators"]:
            if not indicator_by_code[indicator]["supports_trend"]:
                quality["semantic_errors"] += 1
                ok = False
    if sample["question_family"].startswith("cluster_") or intent.startswith("CLUSTER"):
        for field in ("start_year", "end_year"):
            year = parsed[field]
            if year is not None and year not in cluster_years:
                quality["semantic_errors"] += 1
                ok = False
    return ok


def validate_catalog(parsed, country_codes, indicator_codes, country_groups, quality):
    ok = True
    if set(parsed["countries"]) - country_codes:
        quality["catalog_errors"] += 1
        ok = False
    if set(parsed["indicators"]) - indicator_codes:
        quality["catalog_errors"] += 1
        ok = False
    if set(parsed["country_groups"]) - country_groups:
        quality["catalog_errors"] += 1
        ok = False
    return ok


def build_quality_report(samples, quality, warnings, parser_intents, all_family_ids, base_plan_count):
    by_source = Counter(sample["generation_source"] for sample in samples)
    by_intent = Counter(sample["intent"] for sample in samples)
    by_style = Counter(sample["language_style"] for sample in samples)
    by_family = Counter(sample["question_family"] for sample in samples)
    countries = {country for sample in samples for country in sample["assistant_json"].get("countries", [])}
    indicators = {indicator for sample in samples for indicator in sample["assistant_json"].get("indicators", [])}
    plan_groups = {sample["plan_group_id"] for sample in samples}
    return {
        "version": "v1",
        "total_samples": len(samples),
        "quality_checks": dict(quality),
        "coverage": {
            "intents_covered": sum(1 for intent in parser_intents if by_intent[intent] > 0),
            "question_families_covered": sum(1 for family in all_family_ids if by_family[family] > 0),
            "countries_covered": len(countries),
            "indicators_covered": len(indicators),
            "plan_groups_covered": len(plan_groups),
        },
        "distribution": {
            "samples_by_generation_source": dict(sorted(by_source.items())),
            "samples_by_intent": dict(sorted(by_intent.items())),
            "samples_by_language_style": dict(sorted(by_style.items())),
            "samples_by_question_family_top_20": [[family, count] for family, count in by_family.most_common(20)],
        },
        "warnings": warnings,
    }


def write_quality_report(report):
    with QUALITY_REPORT_PATH.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)
        file.write("\n")


def main():
    schema = load_json(SCHEMA_PATH)
    parser_intents = load_json(INTENTS_PATH)
    parser_intent_set = set(parser_intents)
    enums = load_json(ENUMS_PATH)
    families_config = load_json(FAMILIES_PATH)
    distribution = load_json(DISTRIBUTION_PATH)
    country_catalog = load_json(COUNTRY_CATALOG_PATH)
    indicator_catalog = load_json(INDICATOR_CATALOG_PATH)
    analytics = load_json(ANALYTICS_PATH)
    base_plans = read_jsonl(BASE_PLANS_PATH, "base plans")
    samples = read_jsonl(FULL_PATH, "parser_full")
    report = load_json(REPORT_PATH)

    source_counts = {source: len(read_jsonl(path, source)) for source, path in SOURCE_FILES.items()}
    base_by_id = {plan["plan_group_id"]: plan for plan in base_plans}
    expected_source_counts = Counter()
    for plan in base_plans:
        expected_source_counts[plan["generation_bucket"]] += plan["target_sample_count"]
    schema_fields = set(schema["required"])
    family_meta = {family["id"]: family for family in families_config["families"]}
    all_family_ids = set(family_meta)
    country_codes = {country["code"] for country in country_catalog["countries"]}
    indicator_by_code = {indicator["code"]: indicator for indicator in indicator_catalog["indicators"]}
    indicator_codes = set(indicator_by_code)
    country_groups = set(enums["country_groups"])
    cluster_years = set(analytics["cluster"]["target_years"])
    quality = Counter(
        {
            "jsonl_parse_errors": 0,
            "chatml_errors": 0,
            "assistant_json_errors": 0,
            "schema_errors": 0,
            "label_consistency_errors": 0,
            "catalog_errors": 0,
            "semantic_errors": 0,
            "duplicate_user_messages": 0,
            "mojibake_findings": 0,
            "placeholder_findings": 0,
            "synthetic_artifact_findings": 0,
            "too_long_messages": 0,
        }
    )
    warnings = []
    sample_ids = set()
    source_sample_ids = set()
    user_messages = Counter()
    examples = []

    for index, sample in enumerate(samples, start=1):
        sample_id = sample.get("sample_id")
        if sample_id in sample_ids:
            examples.append(f"duplicate sample_id {sample_id}")
        sample_ids.add(sample_id)
        source_sample_id = sample.get("source_sample_id")
        if not source_sample_id:
            examples.append(f"{sample_id} missing source_sample_id")
        if source_sample_id in source_sample_ids:
            examples.append(f"duplicate source_sample_id {source_sample_id}")
        source_sample_ids.add(source_sample_id)
        plan_id = sample.get("plan_group_id")
        if plan_id not in base_by_id:
            examples.append(f"{sample_id} unknown plan_group_id {plan_id}")
            continue
        plan = base_by_id[plan_id]
        source = sample.get("generation_source")
        if source not in VALID_GENERATION_SOURCES:
            examples.append(f"{sample_id} invalid generation_source {source}")
        elif source != plan["generation_bucket"]:
            quality["label_consistency_errors"] += 1
            examples.append(f"{sample_id} generation_source does not match base plan")

        validate_user_message(sample, quality)
        validate_messages(sample, quality)
        if not validate_assistant_schema(sample, schema_fields, parser_intent_set, enums, quality):
            examples.append(f"{sample_id} assistant schema invalid")
            continue
        parsed = sample["assistant_json"]
        if sample.get("intent") != parsed["intent"] or sample.get("question_family") != parsed["question_family"]:
            quality["label_consistency_errors"] += 1
            examples.append(f"{sample_id} sample labels mismatch assistant_json")
        if parsed != plan["parsed_query"]:
            quality["label_consistency_errors"] += 1
            examples.append(f"{sample_id} assistant_json != base plan parsed_query")
        validate_catalog(parsed, country_codes, indicator_codes, country_groups, quality)
        validate_semantics(sample, family_meta, indicator_by_code, cluster_years, quality)
        user_messages[sample["user_message"]] += 1

    duplicate_user_messages = sum(count - 1 for count in user_messages.values() if count > 1)
    quality["duplicate_user_messages"] = duplicate_user_messages
    if duplicate_user_messages:
        for message, count in user_messages.items():
            if count > 1:
                examples.append(f"duplicate user_message x{count}: {message}")
                if len(examples) >= 30:
                    break

    by_source = Counter(sample["generation_source"] for sample in samples)
    by_intent = Counter(sample["intent"] for sample in samples)
    by_family = Counter(sample["question_family"] for sample in samples)
    by_style = Counter(sample["language_style"] for sample in samples)
    countries = {country for sample in samples for country in sample["assistant_json"].get("countries", [])}
    indicators = {indicator for sample in samples for indicator in sample["assistant_json"].get("indicators", [])}
    plan_groups = {sample["plan_group_id"] for sample in samples}

    if len(samples) != distribution["target_total_samples"]:
        examples.append(f"total samples {len(samples)} != {distribution['target_total_samples']}")
    if dict(sorted(by_source.items())) != dict(sorted(expected_source_counts.items())):
        examples.append(f"generation source counts mismatch: {dict(by_source)} != {dict(expected_source_counts)}")
    if dict(sorted(by_intent.items())) != dict(sorted(distribution["intent_targets"].items())):
        examples.append("samples_by_intent does not match dataset_distribution.intent_targets")
    missing_intents = [intent for intent in parser_intents if by_intent[intent] == 0]
    if missing_intents:
        examples.append(f"missing intents: {missing_intents}")
    missing_families = sorted(all_family_ids - set(by_family))
    if missing_families:
        examples.append(f"missing question families: {missing_families[:20]}")
    required_styles = {"vi", "vi_no_diacritics", "en", "mixed_vi_en", "short_chat", "technical_code"}
    missing_styles = sorted(required_styles - set(by_style))
    if missing_styles:
        examples.append(f"missing language styles: {missing_styles}")
    if len(countries) < 88:
        examples.append(f"unique countries too low: {len(countries)}")
    if len(indicators) < 56:
        examples.append(f"unique indicators too low: {len(indicators)}")
    if len(plan_groups) != len(base_plans):
        examples.append(f"plan groups covered {len(plan_groups)} != base plan groups {len(base_plans)}")

    computed_report = {
        "total_samples": len(samples),
        "source_counts": dict(sorted(source_counts.items())),
        "merged_counts": dict(sorted(by_source.items())),
        "samples_by_intent": dict(sorted(by_intent.items())),
        "samples_by_family": dict(sorted(by_family.items())),
        "samples_by_language_style": dict(sorted(by_style.items())),
        "unique_user_messages": len(user_messages),
        "unique_countries_used": len(countries),
        "unique_indicators_used": len(indicators),
    }
    for key, value in computed_report.items():
        if report.get(key) != value:
            examples.append(f"report {key} mismatch")
    if report.get("dropped_duplicates") != 0 or report.get("dropped_invalid") != 0:
        examples.append("merge report has dropped samples")

    quality_report = build_quality_report(samples, quality, warnings, parser_intents, all_family_ids, len(base_plans))
    write_quality_report(quality_report)
    quality_issue_count = sum(quality.values())
    warning_count = len(warnings)

    if quality_issue_count or examples:
        fail(f"quality issues={quality_issue_count}, validation errors={len(examples)}", examples)

    print(f"total samples: {len(samples)}")
    print(f"source counts: {source_counts}")
    print(f"samples by generation_source: {dict(sorted(by_source.items()))}")
    print(f"samples by intent: {dict(sorted(by_intent.items()))}")
    print(f"samples by language_style: {dict(sorted(by_style.items()))}")
    print(f"question families covered: {len(by_family)}/{len(all_family_ids)}")
    print(f"unique countries: {len(countries)}")
    print(f"unique indicators: {len(indicators)}")
    print(f"duplicate count: {duplicate_user_messages}")
    print(f"quality issue count: {quality_issue_count}")
    print(f"warning count: {warning_count}")
    print("PASS")


if __name__ == "__main__":
    main()
