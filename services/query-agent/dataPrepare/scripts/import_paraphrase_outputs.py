import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from render_deterministic_samples import SYSTEM_PROMPT, variants_for


ROOT_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT_DIR / "configs"
DATASET_DIR = ROOT_DIR / "datasets" / "parser"
BATCH_DIR = DATASET_DIR / "paraphrase_batches"
OUTPUT_DIR = DATASET_DIR / "paraphrase_outputs"

CONFIG_PATH = CONFIG_DIR / "paraphrase_generation.v1.json"
SCHEMA_PATH = CONFIG_DIR / "parsed_query_schema.v1.json"
ENUMS_PATH = CONFIG_DIR / "parser_enums.v1.json"
COUNTRY_CATALOG_PATH = CONFIG_DIR / "country_catalog.v1.json"
INDICATOR_CATALOG_PATH = CONFIG_DIR / "indicator_catalog.v1.json"
BASE_PLANS_PATH = DATASET_DIR / "base_plans.v1.jsonl"
DETERMINISTIC_PATH = DATASET_DIR / "parser_deterministic.v1.jsonl"
MANIFEST_PATH = BATCH_DIR / "batch_manifest.v1.json"
SAMPLES_PATH = DATASET_DIR / "parser_paraphrase.v1.jsonl"
REPORT_PATH = DATASET_DIR / "parser_paraphrase_report.v1.json"

PLACEHOLDER_RE = re.compile(r"{[^{}]+}")
CODE_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)
MOJIBAKE_MARKERS = ["Ãƒ", "Ã‚", "Ã„", "Ã¡Â", "Ã†", "ï¿½"]
MOJIBAKE_REGEXES = [
    re.compile(r"[A-Za-z]\?[A-Za-z]"),
    re.compile(r"\?\?"),
    re.compile(r"(?:^|\s)\?[A-Za-z]"),
    re.compile(r"\b(?:d|ch|k|n|l|t|h|qu)\?", re.IGNORECASE),
]


def load_json(path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def read_jsonl(path, required=True):
    if not path.exists():
        if required:
            raise SystemExit(f"missing JSONL file: {path}")
        return []
    rows = []
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"invalid JSONL in {path} line {line_number}: {exc}") from exc
    return rows


def unique(values):
    result = []
    for value in values:
        if value is not None and value != "" and value not in result:
            result.append(value)
    return result


def has_mojibake(text):
    if any(marker in text for marker in MOJIBAKE_MARKERS):
        return True
    return any(pattern.search(text) for pattern in MOJIBAKE_REGEXES)


def strip_code_fence(text):
    text = text.strip()
    if text.startswith("```"):
        text = CODE_FENCE_RE.sub("", text).strip()
    return text


def parse_output_file(path):
    text = strip_code_fence(path.read_text(encoding="utf-8"))
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid output JSON in {path}: {exc}") from exc
    if not isinstance(data, list):
        raise SystemExit(f"{path} must contain a JSON array")
    return data


def alias_terms(code, catalog_by_code):
    item = catalog_by_code.get(code)
    if not item:
        return [code]
    terms = [code, item.get("name")]
    hints = item.get("question_templates_hint") or {}
    for key in ("vi", "vi_no_diacritics", "en", "technical", "iso3"):
        terms.append(hints.get(key))
    terms.extend(item.get("aliases") or [])
    return unique([term.lower() for term in terms if isinstance(term, str)])


def contains_any(text, terms):
    lowered = text.lower()
    return any(term and term in lowered for term in terms)


def build_sample(sample_number, plan, language_style, user_message, batch_id, source_user_message, warnings):
    assistant_json = plan["parsed_query"]
    assistant_content = json.dumps(assistant_json, ensure_ascii=False, separators=(",", ":"))
    return {
        "sample_id": f"para_{sample_number:06d}",
        "plan_group_id": plan["plan_group_id"],
        "version": "v1",
        "generation_source": "llm_paraphrase",
        "intent": plan["intent"],
        "question_family": plan["question_family"],
        "language_style": language_style,
        "user_message": user_message,
        "assistant_json": assistant_json,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": assistant_content},
        ],
        "render_metadata": {
            "source": "llm_paraphrase",
            "batch_id": batch_id,
            "source_user_message": source_user_message,
            "import_warnings": warnings,
        },
    }


def load_batches(manifest):
    batches = {}
    items_by_plan = {}
    for batch_info in manifest.get("batches", []):
        batch_path = ROOT_DIR / batch_info["path"]
        batch = load_json(batch_path)
        batch_id = batch["batch_id"]
        batches[batch_id] = batch
        for item in batch.get("items") or []:
            items_by_plan[item["plan_group_id"]] = (batch_id, item)
    return batches, items_by_plan


def output_batch_id(path):
    name = path.name
    return name.removesuffix(".output.json")


def validate_variant(
    plan,
    batch_item,
    variant,
    config,
    country_by_code,
    indicator_by_code,
    deterministic_messages,
    seen_messages,
):
    warnings = []
    policy = config["validation_policy"]
    if not isinstance(variant, dict):
        return None, "variant_not_object", warnings
    language_style = variant.get("language_style")
    user_message = variant.get("user_message")
    if language_style not in batch_item["language_styles"]:
        return None, "invalid_language_style", warnings
    if not isinstance(user_message, str) or not user_message.strip():
        return None, "empty_user_message", warnings
    user_message = re.sub(r"\s+", " ", user_message).strip()
    if len(user_message) > policy["drop_if_too_long_chars"]:
        return None, "too_long", warnings
    if policy["drop_if_contains_unrendered_placeholder"] and PLACEHOLDER_RE.search(user_message):
        return None, "unrendered_placeholder", warnings
    if policy["drop_if_mojibake"] and has_mojibake(user_message):
        return None, "mojibake", warnings
    if policy["drop_if_duplicate_global"] and (
        user_message in deterministic_messages or user_message in seen_messages
    ):
        return None, "duplicate_global", warnings

    parsed = plan["parsed_query"]
    lowered = user_message.lower()
    if plan["intent"] != "FOLLOW_UP":
        years = unique([parsed.get("start_year"), parsed.get("end_year")])
        for year in years:
            if year is not None and str(year) not in user_message:
                return None, "missing_year_surface", warnings
        for country in parsed.get("countries") or []:
            if not contains_any(user_message, alias_terms(country, country_by_code)):
                return None, "missing_country_surface", warnings
        indicator_skip_intents = {"FOLLOW_UP", "COUNTRY_PROFILE", "THEME_SUMMARY", "RISK_ALERT"}
        if plan["intent"] not in indicator_skip_intents:
            for indicator in parsed.get("indicators") or []:
                if not contains_any(user_message, alias_terms(indicator, indicator_by_code)):
                    message = f"missing indicator surface for {indicator}"
                    if policy["drop_if_missing_required_surface_terms"]:
                        return None, "missing_indicator_surface", warnings
                    warnings.append(message)

    if parsed.get("ranking_order") == "desc":
        if any(term in lowered for term in ["thấp nhất", "thap nhat", "lowest", "bottom", "smallest"]):
            return None, "ranking_direction_flip", warnings
    if parsed.get("ranking_order") == "asc":
        if any(term in lowered for term in ["cao nhất", "cao nhat", "highest", "top", "largest"]):
            return None, "ranking_direction_flip", warnings

    relative_time = parsed.get("relative_time")
    if relative_time == "after_event":
        if any(term in lowered for term in ["trước", "truoc", "before"]):
            return None, "event_direction_flip", warnings
    if relative_time == "before_event":
        if any(term in lowered for term in ["sau", "after"]):
            return None, "event_direction_flip", warnings

    return (language_style, user_message), None, warnings


def build_report(target_samples, samples, dropped, fallback_filled, warnings):
    samples_by_intent = Counter(sample["intent"] for sample in samples)
    samples_by_family = Counter(sample["question_family"] for sample in samples)
    samples_by_language_style = Counter(sample["language_style"] for sample in samples)
    user_messages = Counter(sample["user_message"] for sample in samples)
    return {
        "version": "v1",
        "generation_source": "llm_paraphrase",
        "target_samples": target_samples,
        "imported_samples": len(samples),
        "dropped_variants": sum(dropped.values()),
        "fallback_filled_samples": fallback_filled,
        "missing_samples": max(0, target_samples - len(samples)),
        "samples_by_intent": dict(sorted(samples_by_intent.items())),
        "samples_by_family": dict(sorted(samples_by_family.items())),
        "samples_by_language_style": dict(sorted(samples_by_language_style.items())),
        "unique_user_messages": len(user_messages),
        "duplicate_user_messages_dropped": dropped.get("duplicate_global", 0),
        "drop_reasons": dict(sorted(dropped.items())),
        "warnings": warnings[:200],
    }


def write_outputs(samples, report):
    with SAMPLES_PATH.open("w", encoding="utf-8", newline="\n") as file:
        for sample in samples:
            file.write(json.dumps(sample, ensure_ascii=False, separators=(",", ":")) + "\n")
    with REPORT_PATH.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)
        file.write("\n")


def fallback_fill(samples, config, target_samples, target_plans, items_by_plan, deterministic_messages, seen_messages):
    if not samples:
        return 0
    fallback_policy = config["fallback_policy"]
    if not fallback_policy["allow_fill_missing_with_deterministic_variants"]:
        return 0
    fill_limit = int(target_samples * fallback_policy["max_fill_ratio"])
    needed = min(target_samples - len(samples), fill_limit)
    if needed <= 0:
        return 0
    sample_number = len(samples) + 1
    filled = 0
    for plan in target_plans:
        if filled >= needed:
            break
        batch_id, item = items_by_plan.get(plan["plan_group_id"], ("fallback", None))
        if not item:
            continue
        for style in item["language_styles"]:
            for variant in variants_for(item["source_user_message"], style):
                if variant in deterministic_messages or variant in seen_messages:
                    continue
                samples.append(
                    build_sample(
                        sample_number,
                        plan,
                        style,
                        variant,
                        batch_id,
                        item["source_user_message"],
                        ["fallback deterministic surface variant"],
                    )
                )
                seen_messages.add(variant)
                sample_number += 1
                filled += 1
                break
            if filled >= needed:
                break
    return filled


def main():
    config = load_json(CONFIG_PATH)
    load_json(SCHEMA_PATH)
    load_json(ENUMS_PATH)
    country_catalog = load_json(COUNTRY_CATALOG_PATH)
    indicator_catalog = load_json(INDICATOR_CATALOG_PATH)
    base_plans = read_jsonl(BASE_PLANS_PATH)
    deterministic_samples = read_jsonl(DETERMINISTIC_PATH, required=False)
    if not MANIFEST_PATH.exists():
        raise SystemExit("Missing batch manifest. Run export_paraphrase_batches.py first.")
    manifest = load_json(MANIFEST_PATH)
    _batches, items_by_plan = load_batches(manifest)

    target_bucket = config["target_generation_bucket"]
    target_plans = [plan for plan in base_plans if plan["generation_bucket"] == target_bucket]
    base_by_id = {plan["plan_group_id"]: plan for plan in target_plans}
    target_samples = sum(plan["target_sample_count"] for plan in target_plans)
    country_by_code = {item["code"]: item for item in country_catalog["countries"]}
    indicator_by_code = {item["code"]: item for item in indicator_catalog["indicators"]}
    deterministic_messages = {sample["user_message"] for sample in deterministic_samples}

    output_files = sorted(OUTPUT_DIR.glob("batch_*.output.json")) if OUTPUT_DIR.exists() else []
    samples = []
    seen_messages = set()
    dropped = Counter()
    report_warnings = []
    sample_number = 1

    if not output_files:
        report_warnings.append("No paraphrase output files found.")
    for output_path in output_files:
        batch_id = output_batch_id(output_path)
        output_items = parse_output_file(output_path)
        for output_item in output_items:
            if not isinstance(output_item, dict):
                dropped["output_item_not_object"] += 1
                continue
            plan_id = output_item.get("plan_group_id")
            if plan_id not in base_by_id or plan_id not in items_by_plan:
                dropped["invalid_plan_group_id"] += 1
                continue
            variants = output_item.get("variants")
            if not isinstance(variants, list):
                dropped["variants_not_list"] += 1
                continue
            plan = base_by_id[plan_id]
            batch_item_id, batch_item = items_by_plan[plan_id]
            for variant in variants[: config["validation_policy"]["max_variants_per_plan"]]:
                valid, drop_reason, warnings = validate_variant(
                    plan,
                    batch_item,
                    variant,
                    config,
                    country_by_code,
                    indicator_by_code,
                    deterministic_messages,
                    seen_messages,
                )
                if drop_reason:
                    dropped[drop_reason] += 1
                    continue
                language_style, user_message = valid
                samples.append(
                    build_sample(
                        sample_number,
                        plan,
                        language_style,
                        user_message,
                        batch_id or batch_item_id,
                        batch_item["source_user_message"],
                        warnings,
                    )
                )
                for warning in warnings:
                    report_warnings.append(f"{plan_id}: {warning}")
                seen_messages.add(user_message)
                sample_number += 1

    fallback_filled = fallback_fill(
        samples,
        config,
        target_samples,
        target_plans,
        items_by_plan,
        deterministic_messages,
        seen_messages,
    )
    report = build_report(target_samples, samples, dropped, fallback_filled, report_warnings)
    write_outputs(samples, report)

    print(f"target samples: {target_samples}")
    print(f"imported samples: {len(samples)}")
    print(f"dropped variants: {report['dropped_variants']}")
    print(f"fallback filled samples: {fallback_filled}")
    print(f"missing samples: {report['missing_samples']}")
    print(f"warnings: {len(report_warnings)}")
    if not output_files:
        print("READY_FOR_MANUAL_PARAPHRASE")
        print("No paraphrase outputs found. Fill datasets/parser/paraphrase_outputs/*.output.json and rerun import.")


if __name__ == "__main__":
    main()
