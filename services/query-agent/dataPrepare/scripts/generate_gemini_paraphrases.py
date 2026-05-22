import json
import os
import re
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from render_deterministic_samples import (
    AliasRenderer,
    SYSTEM_PROMPT,
    family_candidates,
    render_template,
    variants_for,
)


ROOT_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT_DIR / "configs"
DATASET_DIR = ROOT_DIR / "datasets" / "parser"
PROMPT_DIR = ROOT_DIR / "prompts"
RAW_DIR = DATASET_DIR / "paraphrase_raw"

CONFIG_PATH = CONFIG_DIR / "paraphrase_generation.v1.json"
COUNTRY_CATALOG_PATH = CONFIG_DIR / "country_catalog.v1.json"
INDICATOR_CATALOG_PATH = CONFIG_DIR / "indicator_catalog.v1.json"
QUESTION_TEMPLATES_PATH = CONFIG_DIR / "question_templates.v1.json"
BASE_PLANS_PATH = DATASET_DIR / "base_plans.v1.jsonl"
DETERMINISTIC_PATH = DATASET_DIR / "parser_deterministic.v1.jsonl"
PROMPT_TEMPLATE_PATH = PROMPT_DIR / "paraphrase_prompt_template.v1.txt"
ENV_PATH = ROOT_DIR / ".env"
SAMPLES_PATH = DATASET_DIR / "parser_paraphrase.v1.jsonl"
REPORT_PATH = DATASET_DIR / "parser_paraphrase_report.v1.json"
RAW_LOG_PATH = RAW_DIR / "gemini_responses.v1.jsonl"

PLACEHOLDER_RE = re.compile(r"{[^{}]+}")
CODE_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)
MOJIBAKE_MARKERS = ["Ãƒ", "Ã‚", "Ã„", "Ã¡Â", "Ã†", "ï¿½"]
MOJIBAKE_REGEXES = [
    re.compile(r"[A-Za-z]\?[A-Za-z]"),
    re.compile(r"\?\?"),
    re.compile(r"(?:^|\s)\?[A-Za-z]"),
    re.compile(r"\b(?:d|ch|k|n|l|t|h|qu)\?", re.IGNORECASE),
]


def load_dotenv_file(path):
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def env_int(name, default):
    value = os.environ.get(name)
    if value in (None, ""):
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise SystemExit(f"{name} must be an integer") from exc


def env_float(name, default):
    value = os.environ.get(name)
    if value in (None, ""):
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise SystemExit(f"{name} must be a number") from exc


def load_runtime(config):
    load_dotenv_file(ENV_PATH)
    api_keys = [
        key.strip()
        for key in (os.environ.get("GEMINI_API_KEYS") or "").split(",")
        if key.strip() and not key.strip().lower().startswith("key")
    ]
    if not api_keys:
        raise SystemExit("Missing GEMINI_API_KEYS. Create services/query-agent/.env from .env.example.")
    model = os.environ.get("GEMINI_MODEL") or config["model"]["default"]
    max_workers = config["concurrency"]["max_workers"]
    concurrency = min(env_int("GEMINI_CONCURRENCY", config["concurrency"]["default_workers"]), len(api_keys), max_workers)
    return {
        "api_keys": api_keys,
        "model": model,
        "concurrency": max(1, concurrency),
        "max_retries": env_int("GEMINI_MAX_RETRIES", 4),
        "timeout_seconds": env_int("GEMINI_REQUEST_TIMEOUT_SECONDS", 60),
        "temperature": env_float("GEMINI_TEMPERATURE", config["model"]["temperature"]),
        "top_p": env_float("GEMINI_TOP_P", config["model"]["top_p"]),
        "max_output_tokens": env_int("GEMINI_MAX_OUTPUT_TOKENS", config["model"]["max_output_tokens"]),
        "plans_per_request": env_int("GEMINI_BATCH_PLANS", config["batching"]["plans_per_request"]),
    }


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


def parse_json_array(text):
    text = strip_code_fence(text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("[")
        end = text.rfind("]")
        if start == -1 or end == -1 or end <= start:
            raise
        data = json.loads(text[start : end + 1])
    if not isinstance(data, list):
        raise ValueError("Gemini response is not a JSON array")
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
    return unique([term for term in terms if isinstance(term, str)])


def contains_any(text, terms):
    lowered = text.lower()
    return any(term and term.lower() in lowered for term in terms)


def weighted_language_sequence(language_mix):
    sequence = []
    for style, ratio in language_mix.items():
        sequence.extend([style] * max(1, int(round(ratio * 20))))
    return sequence or ["vi", "en"]


def language_styles_for_plan(config, plan_index, requested_variants):
    sequence = weighted_language_sequence(config["language_mix"])
    selected = []
    for offset in range(max(requested_variants, len(sequence))):
        style = sequence[(plan_index + offset) % len(sequence)]
        if style not in selected:
            selected.append(style)
        if len(selected) >= min(requested_variants, len(config["language_mix"])):
            break
    return selected or ["vi"]


def render_source_message(plan, templates, alias_renderer, plan_index):
    family_config = templates["families"].get(plan["question_family"])
    if not family_config:
        raise SystemExit(f"{plan['plan_group_id']} has no template family {plan['question_family']}")
    style_order = ["vi", "en", "vi_no_diacritics", "mixed_vi_en", "short_chat", "technical_code"]
    candidates = family_candidates(family_config, style_order, plan)
    if not candidates:
        raise SystemExit(f"{plan['plan_group_id']} has no usable source template")
    style, template, _template_index = candidates[plan_index % len(candidates)]
    values = alias_renderer.render_values(plan, style, plan_index)
    rendered = render_template(template, values)
    source = variants_for(rendered, style)[0]
    if PLACEHOLDER_RE.search(source) or has_mojibake(source):
        raise SystemExit(f"{plan['plan_group_id']} source_user_message failed quality checks")
    return source


def build_batch_item(plan, config, templates, alias_renderer, country_by_code, indicator_by_code, plan_index, requested_variants):
    parsed = plan["parsed_query"]
    indicator_terms = []
    for code in parsed.get("indicators") or []:
        indicator_terms.extend(alias_terms(code, indicator_by_code))
    country_terms = []
    country_terms_by_country = {}
    for code in parsed.get("countries") or []:
        terms = alias_terms(code, country_by_code)
        country_terms.extend(terms)
        country_terms_by_country[code] = terms
    return {
        "plan_group_id": plan["plan_group_id"],
        "intent": plan["intent"],
        "question_family": plan["question_family"],
        "source_user_message": render_source_message(plan, templates, alias_renderer, plan_index),
        "must_preserve": {
            "indicators": parsed.get("indicators") or [],
            "indicator_surface_terms": unique(indicator_terms),
            "countries": parsed.get("countries") or [],
            "country_surface_terms": unique(country_terms),
            "country_surface_terms_by_country": country_terms_by_country,
            "country_groups": parsed.get("country_groups") or [],
            "start_year": parsed.get("start_year"),
            "end_year": parsed.get("end_year"),
            "relative_time": parsed.get("relative_time"),
            "event_time": parsed.get("event_time"),
            "ranking_order": parsed.get("ranking_order"),
            "limit": parsed.get("limit"),
            "threshold": parsed.get("threshold"),
            "aggregation": parsed.get("aggregation"),
            "chart_preference": parsed.get("chart_preference"),
        },
        "requested_variants": requested_variants,
        "language_styles": language_styles_for_plan(config, plan_index, requested_variants),
    }


def render_prompt(prompt_template, items):
    batch_json = json.dumps(items, ensure_ascii=False, indent=2)
    return prompt_template.replace("{{BATCH_JSON}}", batch_json)


def split_batches(items, plans_per_request, max_prompt_chars, prompt_template):
    batches = []
    current = []
    for item in items:
        candidate = current + [item]
        prompt = render_prompt(prompt_template, candidate)
        if current and (len(candidate) > plans_per_request or len(prompt) > max_prompt_chars):
            batches.append(current)
            current = [item]
        else:
            current = candidate
    if current:
        batches.append(current)
    return batches


def call_gemini(batch_id, items, api_key, api_key_index, prompt_template, runtime):
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise SystemExit("Missing dependency google-genai. Run python -m pip install -r requirements.txt") from exc

    prompt = render_prompt(prompt_template, items)
    last_error = None
    raw_text = ""
    for attempt in range(1, runtime["max_retries"] + 1):
        try:
            client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(timeout=runtime["timeout_seconds"] * 1000),
            )
            response = client.models.generate_content(
                model=runtime["model"],
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=runtime["temperature"],
                    top_p=runtime["top_p"],
                    max_output_tokens=runtime["max_output_tokens"],
                    response_mime_type="application/json",
                ),
            )
            raw_text = getattr(response, "text", "") or ""
            parsed = parse_json_array(raw_text)
            return {
                "batch_id": batch_id,
                "api_key_index": api_key_index,
                "success": True,
                "attempts": attempt,
                "items": items,
                "raw_text": raw_text,
                "parsed": parsed,
                "error": None,
            }
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            time.sleep(min(2 ** (attempt - 1), 30))
    return {
        "batch_id": batch_id,
        "api_key_index": api_key_index,
        "success": False,
        "attempts": runtime["max_retries"],
        "items": items,
        "raw_text": raw_text,
        "parsed": [],
        "error": last_error,
    }


def validate_variant(plan, batch_item, variant, config, country_by_code, indicator_by_code, deterministic_messages, seen_messages):
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
    if policy["drop_if_duplicate_global"] and (user_message in deterministic_messages or user_message in seen_messages):
        return None, "duplicate_global", warnings

    parsed = plan["parsed_query"]
    lowered = user_message.lower()
    if plan["intent"] != "FOLLOW_UP":
        if policy["drop_if_year_missing_for_non_followup"]:
            for year in unique([parsed.get("start_year"), parsed.get("end_year")]):
                if year is not None and str(year) not in user_message:
                    return None, "missing_year_surface", warnings
        if policy["drop_if_country_missing_for_non_followup"]:
            for country in parsed.get("countries") or []:
                if not contains_any(user_message, alias_terms(country, country_by_code)):
                    return None, "missing_country_surface", warnings

        skip_indicator_intents = {"FOLLOW_UP", "COUNTRY_PROFILE", "THEME_SUMMARY", "RISK_ALERT"}
        if plan["intent"] not in skip_indicator_intents:
            for indicator in parsed.get("indicators") or []:
                if not contains_any(user_message, alias_terms(indicator, indicator_by_code)):
                    if policy["drop_if_missing_required_surface_terms"]:
                        return None, "missing_indicator_surface", warnings
                    warnings.append(f"missing indicator surface for {indicator}")

    if parsed.get("ranking_order") == "desc":
        if any(term in lowered for term in ["thấp nhất", "thap nhat", "lowest", "bottom", "smallest"]):
            return None, "ranking_direction_flip", warnings
    if parsed.get("ranking_order") == "asc":
        if any(term in lowered for term in ["cao nhất", "cao nhat", "highest", "top", "largest"]):
            return None, "ranking_direction_flip", warnings
    if parsed.get("relative_time") == "after_event" and any(term in lowered for term in ["trước", "truoc", "before"]):
        return None, "event_direction_flip", warnings
    if parsed.get("relative_time") == "before_event" and any(term in lowered for term in ["sau", "after"]):
        return None, "event_direction_flip", warnings

    return (language_style, user_message), None, warnings


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
            "source": "gemini",
            "batch_id": batch_id,
            "source_user_message": source_user_message,
            "import_warnings": warnings,
        },
    }


def fallback_source_variants(source_user_message, style, parsed):
    variants = variants_for(source_user_message, style)
    start_year = parsed.get("start_year")
    end_year = parsed.get("end_year")
    if start_year is not None and end_year is not None:
        replacements = [
            (f"từ {start_year} đến {end_year}", f"giai đoạn {start_year}-{end_year}"),
            (f"tu {start_year} den {end_year}", f"giai doan {start_year}-{end_year}"),
            (f"from {start_year} to {end_year}", f"during {start_year}-{end_year}"),
        ]
        for original, replacement in replacements:
            if original in source_user_message:
                variants.extend(variants_for(source_user_message.replace(original, replacement), style))
    safe_swaps = [
        ("So sánh", "Đối chiếu"),
        ("so sánh", "đối chiếu"),
        ("Compare", "Contrast"),
        ("compare", "contrast"),
    ]
    for original, replacement in safe_swaps:
        if original in source_user_message:
            variants.extend(variants_for(source_user_message.replace(original, replacement), style))
    result = []
    for variant in variants:
        if variant not in result:
            result.append(variant)
    return result


def first_surface(terms, fallback):
    for term in terms:
        if term and term != fallback:
            return term
    return fallback


def fallback_period_phrase(parsed, style):
    start_year = parsed.get("start_year")
    end_year = parsed.get("end_year")
    if start_year is None and end_year is None:
        return ""
    if start_year is not None and end_year is not None and start_year != end_year:
        if style == "en":
            return f"from {start_year} to {end_year}"
        return f"giai đoạn {start_year}-{end_year}"
    year = start_year if start_year is not None else end_year
    if style == "en":
        return f"in {year}"
    return f"năm {year}"


def canonical_fallback_message(plan, batch_item, style):
    parsed = plan["parsed_query"]
    preserve = batch_item["must_preserve"]
    indicator = first_surface(preserve.get("indicator_surface_terms") or [], "the indicator")
    country_terms_by_country = preserve.get("country_surface_terms_by_country") or {}
    country_aliases = []
    for code in parsed.get("countries") or []:
        country_aliases.append(first_surface(country_terms_by_country.get(code) or [code], code))
    connector = " and " if style == "en" else " và "
    country_text = connector.join(country_aliases)
    if not country_text:
        country_text = "all countries" if style == "en" else "tất cả quốc gia"
    period = fallback_period_phrase(parsed, style)
    event = parsed.get("event_time")
    event_text = ""
    if event == "COVID":
        event_text = " after COVID-19" if style == "en" else " sau COVID"
    elif event == "GFC_2008":
        event_text = " after the 2008 financial crisis" if style == "en" else " sau khủng hoảng tài chính 2008"
    elif event == "ASIAN_FINANCIAL_CRISIS_1997":
        event_text = " after the 1997 Asian financial crisis" if style == "en" else " sau khủng hoảng tài chính châu Á 1997"

    limit = parsed.get("limit") or 10
    order = parsed.get("ranking_order")
    intent = plan["intent"]
    family = plan["question_family"]
    if style == "en":
        if intent == "RANKING":
            direction = "bottom" if order == "asc" else "top"
            return f"Rank the {direction} {limit} countries by {indicator} {period}."
        if intent == "RANK_BY_CHANGE":
            if order == "asc" or "decrease" in family:
                return f"Rank {limit} countries by decrease in {indicator} {period}{event_text}."
            return f"Rank {limit} countries by increase in {indicator} {period}{event_text}."
        if intent == "ANOMALY_DETECTION":
            return f"Find anomalies in {indicator} for {country_text} {period}{event_text}."
        if intent == "CRISIS_ANALYSIS":
            return f"Analyze crisis risk for {country_text} {period}{event_text}."
        if intent == "COMPARE_PERIODS":
            return f"Compare {indicator} for {country_text} {period}."
        return f"{batch_item['source_user_message']} {period}."

    if intent == "RANKING":
        direction = "thấp nhất" if order == "asc" else "cao nhất"
        return f"Xếp hạng {limit} quốc gia {direction} theo {indicator} {period}."
    if intent == "RANK_BY_CHANGE":
        if order == "asc" or "decrease" in family:
            return f"Xếp hạng {limit} quốc gia theo mức giảm của {indicator} {period}{event_text}."
        return f"Xếp hạng {limit} quốc gia theo mức tăng của {indicator} {period}{event_text}."
    if intent == "ANOMALY_DETECTION":
        return f"Tìm bất thường của {indicator} cho {country_text} {period}{event_text}."
    if intent == "CRISIS_ANALYSIS":
        return f"Phân tích rủi ro khủng hoảng của {country_text} {period}{event_text}."
    if intent == "COMPARE_PERIODS":
        return f"So sánh {indicator} của {country_text} {period}."
    return f"{batch_item['source_user_message']} {period}."


def fallback_candidate_messages(plan, batch_item, style):
    parsed = plan["parsed_query"]
    source = batch_item["source_user_message"]
    year_tokens = set(re.findall(r"\b(?:19|20)\d{2}\b", source))
    expected_years = {str(year) for year in (parsed.get("start_year"), parsed.get("end_year")) if year is not None}
    candidates = []
    if expected_years and not expected_years.issuperset(year_tokens):
        candidates.extend(variants_for(canonical_fallback_message(plan, batch_item, style), style))
    else:
        candidates.extend(fallback_source_variants(source, style, parsed))
        period = fallback_period_phrase(parsed, style)
        if period and any(year not in source for year in expected_years):
            candidates.extend(variants_for(f"{source.rstrip('.?!')} {period}.", style))
    candidates.extend(variants_for(canonical_fallback_message(plan, batch_item, style), style))
    result = []
    for candidate in candidates:
        if candidate not in result:
            result.append(candidate)
    return result


def fallback_fill_missing(
    samples,
    sample_number,
    config,
    target_samples,
    target_plans,
    plan_counts,
    templates,
    alias_renderer,
    country_by_code,
    indicator_by_code,
    plan_index_by_id,
    deterministic_messages,
    seen_messages,
    dropped,
    warnings,
):
    fallback_policy = config.get("fallback_policy") or {}
    if not fallback_policy.get("allow_fill_missing_with_deterministic_variants"):
        return 0, sample_number

    max_fill = int(target_samples * float(fallback_policy.get("max_fill_ratio", 0)))
    existing_fallback = sum(
        1
        for sample in samples
        if (sample.get("render_metadata") or {}).get("source") == "deterministic_fallback_fill"
    )
    fill_budget = max(0, max_fill - existing_fallback)
    needed_total = target_samples - len(samples)
    if fill_budget <= 0 or needed_total <= 0:
        return 0, sample_number

    filled = 0
    for plan in target_plans:
        if filled >= fill_budget or len(samples) >= target_samples:
            break
        plan_id = plan["plan_group_id"]
        missing_for_plan = plan["target_sample_count"] - plan_counts[plan_id]
        if missing_for_plan <= 0:
            continue
        batch_item = build_batch_item(
            plan,
            config,
            templates,
            alias_renderer,
            country_by_code,
            indicator_by_code,
            plan_index_by_id[plan_id],
            missing_for_plan,
        )
        for style in batch_item["language_styles"]:
            for user_message in fallback_candidate_messages(plan, batch_item, style):
                if filled >= fill_budget or len(samples) >= target_samples or plan_counts[plan_id] >= plan["target_sample_count"]:
                    break
                valid, drop_reason, variant_warnings = validate_variant(
                    plan,
                    batch_item,
                    {"language_style": style, "user_message": user_message},
                    config,
                    country_by_code,
                    indicator_by_code,
                    deterministic_messages,
                    seen_messages,
                )
                if drop_reason:
                    dropped[f"fallback_{drop_reason}"] += 1
                    continue
                language_style, valid_message = valid
                fallback_warnings = ["filled_without_llm_after_gemini_no_progress"] + variant_warnings
                samples.append(
                    build_sample(
                        sample_number,
                        plan,
                        language_style,
                        valid_message,
                        "deterministic_fallback_fill",
                        batch_item["source_user_message"],
                        fallback_warnings,
                    )
                )
                samples[-1]["render_metadata"]["source"] = "deterministic_fallback_fill"
                sample_number += 1
                plan_counts[plan_id] += 1
                seen_messages.add(valid_message)
                filled += 1
                for warning in fallback_warnings:
                    warnings.append(f"{plan_id}: {warning}")
        if filled >= fill_budget or len(samples) >= target_samples:
            break
    return filled, sample_number


def load_existing_samples(config, target_plan_ids):
    if not config["resume_policy"]["resume_from_existing_output"]:
        return []
    samples = []
    for sample in read_jsonl(SAMPLES_PATH, required=False):
        if (
            isinstance(sample, dict)
            and sample.get("generation_source") == "llm_paraphrase"
            and sample.get("plan_group_id") in target_plan_ids
            and isinstance(sample.get("user_message"), str)
        ):
            samples.append(sample)
    return samples


def next_sample_number(samples):
    max_number = 0
    for sample in samples:
        sample_id = sample.get("sample_id", "")
        if sample_id.startswith("para_"):
            try:
                max_number = max(max_number, int(sample_id.split("_", 1)[1]))
            except ValueError:
                pass
    return max_number + 1


def append_raw_log(record):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    safe_record = {
        "batch_id": record["batch_id"],
        "api_key_index": record["api_key_index"],
        "success": record["success"],
        "attempts": record["attempts"],
        "plan_group_ids": [item["plan_group_id"] for item in record["items"]],
        "raw_text": record.get("raw_text", ""),
        "error": record.get("error"),
    }
    with RAW_LOG_PATH.open("a", encoding="utf-8", newline="\n") as file:
        file.write(json.dumps(safe_record, ensure_ascii=False, separators=(",", ":")) + "\n")


def write_samples(samples):
    with SAMPLES_PATH.open("w", encoding="utf-8", newline="\n") as file:
        for sample in samples:
            file.write(json.dumps(sample, ensure_ascii=False, separators=(",", ":")) + "\n")


def build_report(samples, config, runtime, target_samples, dropped, warnings, request_stats, fallback_filled):
    samples_by_intent = Counter(sample["intent"] for sample in samples)
    samples_by_family = Counter(sample["question_family"] for sample in samples)
    samples_by_language_style = Counter(sample["language_style"] for sample in samples)
    user_messages = Counter(sample["user_message"] for sample in samples)
    return {
        "version": "v1",
        "generation_source": "llm_paraphrase",
        "provider": "gemini",
        "model": runtime["model"],
        "target_samples": target_samples,
        "imported_samples": len(samples),
        "dropped_variants": sum(dropped.values()),
        "fallback_filled_samples": fallback_filled,
        "missing_samples": max(0, target_samples - len(samples)),
        "requests_attempted": request_stats["attempted"],
        "requests_succeeded": request_stats["succeeded"],
        "requests_failed": request_stats["failed"],
        "samples_by_intent": dict(sorted(samples_by_intent.items())),
        "samples_by_family": dict(sorted(samples_by_family.items())),
        "samples_by_language_style": dict(sorted(samples_by_language_style.items())),
        "unique_user_messages": len(user_messages),
        "duplicate_user_messages_dropped": dropped.get("duplicate_global", 0),
        "drop_reasons": dict(sorted(dropped.items())),
        "warnings": warnings[:300],
        "api_key_count": len(runtime["api_keys"]),
        "concurrency": runtime["concurrency"],
    }


def write_report(report):
    with REPORT_PATH.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)
        file.write("\n")


def load_prior_report():
    if not REPORT_PATH.exists():
        return {}
    try:
        report = load_json(REPORT_PATH)
    except (OSError, json.JSONDecodeError):
        return {}
    return report if isinstance(report, dict) else {}


def load_raw_request_stats():
    stats = Counter({"attempted": 0, "succeeded": 0, "failed": 0})
    if not RAW_LOG_PATH.exists():
        return stats
    with RAW_LOG_PATH.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            stats["attempted"] += 1
            if record.get("success"):
                stats["succeeded"] += 1
            else:
                stats["failed"] += 1
    return stats
    try:
        return load_json(REPORT_PATH)
    except (OSError, json.JSONDecodeError):
        return {}


def main():
    config = load_json(CONFIG_PATH)
    runtime = load_runtime(config)
    country_catalog = load_json(COUNTRY_CATALOG_PATH)
    indicator_catalog = load_json(INDICATOR_CATALOG_PATH)
    templates = load_json(QUESTION_TEMPLATES_PATH)
    prompt_template = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
    base_plans = read_jsonl(BASE_PLANS_PATH)
    deterministic_samples = read_jsonl(DETERMINISTIC_PATH)

    target_bucket = config["target_generation_bucket"]
    target_plans = [plan for plan in base_plans if plan["generation_bucket"] == target_bucket]
    target_samples = sum(plan["target_sample_count"] for plan in target_plans)
    if target_samples != config["target_samples"]:
        print(f"WARNING config target_samples {config['target_samples']} != computed {target_samples}")

    country_by_code = {item["code"]: item for item in country_catalog["countries"]}
    indicator_by_code = {item["code"]: item for item in indicator_catalog["indicators"]}
    alias_renderer = AliasRenderer(country_catalog, indicator_catalog)
    plan_by_id = {plan["plan_group_id"]: plan for plan in target_plans}
    plan_index_by_id = {plan["plan_group_id"]: index for index, plan in enumerate(target_plans)}
    samples = load_existing_samples(config, set(plan_by_id))
    sample_number = next_sample_number(samples)
    seen_messages = {sample["user_message"] for sample in samples}
    deterministic_messages = {sample["user_message"] for sample in deterministic_samples}
    plan_counts = Counter(sample["plan_group_id"] for sample in samples)
    plan_attempts = Counter()
    dropped = Counter()
    warnings = []
    request_stats = load_raw_request_stats()
    checkpoint_every = config["resume_policy"]["checkpoint_every_requests"]
    prior_report = load_prior_report()
    fallback_filled = sum(
        1
        for sample in samples
        if (sample.get("render_metadata") or {}).get("source") == "deterministic_fallback_fill"
    )
    max_no_progress_rounds = int((config.get("fallback_policy") or {}).get("max_no_progress_rounds", 3))
    no_progress_rounds = 0

    print(f"model: {runtime['model']}")
    print(f"api key count: {len(runtime['api_keys'])}")
    print(f"concurrency: {runtime['concurrency']}")
    print(f"target samples: {target_samples}")
    print(f"resume samples loaded: {len(samples)}")

    skip_gemini_this_run = (
        prior_report.get("imported_samples") == len(samples)
        and prior_report.get("missing_samples", target_samples) == target_samples - len(samples)
        and (
            (
                prior_report.get("requests_failed", 0) > 0
                and prior_report.get("requests_succeeded", 0) == 0
            )
            or prior_report.get("fallback_filled_samples", 0) > 0
        )
        and (config.get("fallback_policy") or {}).get("allow_fill_missing_with_deterministic_variants")
    )
    if skip_gemini_this_run:
        print("Previous run made no Gemini progress; using deterministic fallback fill for remaining samples.")

    while len(samples) < target_samples and not skip_gemini_this_run:
        pending_items = []
        for plan in target_plans:
            current = plan_counts[plan["plan_group_id"]]
            remaining = plan["target_sample_count"] - current
            if remaining <= 0:
                continue
            if plan_attempts[plan["plan_group_id"]] >= runtime["max_retries"]:
                continue
            requested_variants = min(
                remaining + 2,
                config["validation_policy"]["max_variants_per_plan"],
            )
            pending_items.append(
                build_batch_item(
                    plan,
                    config,
                    templates,
                    alias_renderer,
                    country_by_code,
                    indicator_by_code,
                    plan_index_by_id[plan["plan_group_id"]],
                    requested_variants,
                )
            )
        if not pending_items:
            break

        batches = split_batches(
            pending_items,
            runtime["plans_per_request"],
            config["batching"]["max_prompt_chars"],
            prompt_template,
        )
        before_round = len(samples)
        futures = {}
        with ThreadPoolExecutor(max_workers=runtime["concurrency"]) as executor:
            for batch_index, batch_items in enumerate(batches, start=1):
                batch_id = f"gemini_{request_stats['attempted'] + batch_index:05d}"
                api_key_index = (request_stats["attempted"] + batch_index - 1) % len(runtime["api_keys"])
                for item in batch_items:
                    plan_attempts[item["plan_group_id"]] += 1
                future = executor.submit(
                    call_gemini,
                    batch_id,
                    batch_items,
                    runtime["api_keys"][api_key_index],
                    api_key_index,
                    prompt_template,
                    runtime,
                )
                futures[future] = batch_items

            for future in as_completed(futures):
                record = future.result()
                request_stats["attempted"] += 1
                if config["resume_policy"]["raw_response_log"]:
                    append_raw_log(record)
                if not record["success"]:
                    request_stats["failed"] += 1
                else:
                    request_stats["succeeded"] += 1
                    batch_item_by_id = {item["plan_group_id"]: item for item in record["items"]}
                    for output_item in record["parsed"]:
                        if not isinstance(output_item, dict):
                            dropped["output_item_not_object"] += 1
                            continue
                        plan_id = output_item.get("plan_group_id")
                        if plan_id not in plan_by_id or plan_id not in batch_item_by_id:
                            dropped["invalid_plan_group_id"] += 1
                            continue
                        variants = output_item.get("variants")
                        if not isinstance(variants, list):
                            dropped["variants_not_list"] += 1
                            continue
                        plan = plan_by_id[plan_id]
                        batch_item = batch_item_by_id[plan_id]
                        for variant in variants[: config["validation_policy"]["max_variants_per_plan"]]:
                            if plan_counts[plan_id] >= plan["target_sample_count"]:
                                dropped["over_target_for_plan"] += 1
                                continue
                            valid, drop_reason, variant_warnings = validate_variant(
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
                                    record["batch_id"],
                                    batch_item["source_user_message"],
                                    variant_warnings,
                                )
                            )
                            sample_number += 1
                            plan_counts[plan_id] += 1
                            seen_messages.add(user_message)
                            for warning in variant_warnings:
                                warnings.append(f"{plan_id}: {warning}")
                            if len(samples) >= target_samples:
                                break
                        if len(samples) >= target_samples:
                            break

                if request_stats["attempted"] % checkpoint_every == 0:
                    write_samples(samples)
                    report = build_report(
                        samples,
                        config,
                        runtime,
                        target_samples,
                        dropped,
                        warnings,
                        request_stats,
                        fallback_filled,
                    )
                    write_report(report)
                    print(
                        f"progress requests={request_stats['attempted']} "
                        f"imported={len(samples)}/{target_samples} "
                        f"dropped={sum(dropped.values())} failed={request_stats['failed']}"
                    )

        if len(samples) == before_round:
            no_progress_rounds += 1
            print(
                f"No new valid samples imported in round {no_progress_rounds}/"
                f"{max_no_progress_rounds}; continuing with remaining plans."
            )
            if no_progress_rounds >= max_no_progress_rounds:
                break
        else:
            no_progress_rounds = 0

    if len(samples) < target_samples:
        filled_now, sample_number = fallback_fill_missing(
            samples,
            sample_number,
            config,
            target_samples,
            target_plans,
            plan_counts,
            templates,
            alias_renderer,
            country_by_code,
            indicator_by_code,
            plan_index_by_id,
            deterministic_messages,
            seen_messages,
            dropped,
            warnings,
        )
        fallback_filled += filled_now
        if filled_now:
            print(f"fallback filled samples: {filled_now}")

    write_samples(samples)
    report = build_report(samples, config, runtime, target_samples, dropped, warnings, request_stats, fallback_filled)
    write_report(report)
    print(f"imported samples: {len(samples)}")
    print(f"missing samples: {report['missing_samples']}")
    print(f"fallback_filled_samples: {report['fallback_filled_samples']}")
    print(f"dropped variants: {report['dropped_variants']}")
    print(f"drop_reasons: {report['drop_reasons']}")
    print(
        "requests attempted/succeeded/failed: "
        f"{report['requests_attempted']}/{report['requests_succeeded']}/{report['requests_failed']}"
    )
    print(f"samples by language style: {report['samples_by_language_style']}")


if __name__ == "__main__":
    main()
