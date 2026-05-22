import json
import random
import re
import unicodedata
from collections import Counter
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

HARD_CONFIG_PATH = CONFIG_DIR / "hard_case_generation.v1.json"
OFFUNS_CONFIG_PATH = CONFIG_DIR / "offtopic_unsupported_generation.v1.json"
QUESTION_TEMPLATES_PATH = CONFIG_DIR / "question_templates.v1.json"
COUNTRY_CATALOG_PATH = CONFIG_DIR / "country_catalog.v1.json"
INDICATOR_CATALOG_PATH = CONFIG_DIR / "indicator_catalog.v1.json"
PARSER_ENUMS_PATH = CONFIG_DIR / "parser_enums.v1.json"
BASE_PLANS_PATH = DATASET_DIR / "base_plans.v1.jsonl"
DETERMINISTIC_PATH = DATASET_DIR / "parser_deterministic.v1.jsonl"
PARAPHRASE_PATH = DATASET_DIR / "parser_paraphrase.v1.jsonl"

HARD_OUTPUT_PATH = DATASET_DIR / "parser_hard_cases.v1.jsonl"
HARD_REPORT_PATH = DATASET_DIR / "parser_hard_cases_report.v1.json"
OFFUNS_OUTPUT_PATH = DATASET_DIR / "parser_offtopic_unsupported.v1.jsonl"
OFFUNS_REPORT_PATH = DATASET_DIR / "parser_offtopic_unsupported_report.v1.json"

PLACEHOLDER_RE = re.compile(r"{[^{}]+}")
MOJIBAKE_MARKERS = ["Ãƒ", "Ã‚", "Ã„", "Ã¡Â", "Ã†", "ï¿½"]
MOJIBAKE_REGEXES = [
    re.compile(r"[A-Za-z]\?[A-Za-z]"),
    re.compile(r"\?\?"),
    re.compile(r"(?:^|\s)\?[A-Za-z]"),
    re.compile(r"\b(?:d|ch|k|n|l|t|h|qu)\?", re.IGNORECASE),
]
NATURAL_VARIATION_SUFFIXES = [
    "",
    " nhé",
    " giúp tôi",
    " cho tôi",
    " được không",
    " với",
    " nhanh thôi",
    " bản ngắn",
    " theo cách dễ hiểu",
    " cho người mới",
    " trong hôm nay",
    " khi rảnh",
    " thật gọn",
    " chi tiết vừa đủ",
    " bằng ví dụ đơn giản",
    " theo từng bước",
    " không cần dài",
    " theo kiểu thực hành",
    " để tôi tham khảo",
    " cho buổi tối nay",
    " theo giọng tự nhiên",
    " với vài lựa chọn",
    " theo cách thân thiện",
    " ngắn gọn thôi",
]


def load_json(path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def read_jsonl(path):
    if not path.exists():
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


def write_jsonl(path, rows):
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def write_json(path, data):
    with path.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")


def normalize(text):
    text = re.sub(r"\s+", " ", text).strip()
    return text.replace(" .", ".").replace(" ?", "?").replace(" ,", ",")


def naturalize_template(template, n):
    suffix = NATURAL_VARIATION_SUFFIXES[n % len(NATURAL_VARIATION_SUFFIXES)]
    text = template.format(suffix=suffix)
    if suffix and text.endswith("."):
        return text
    return text


def strip_diacritics(text):
    text = unicodedata.normalize("NFD", text)
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return text.replace("đ", "d").replace("Đ", "D")


def has_mojibake(text):
    if any(marker in text for marker in MOJIBAKE_MARKERS):
        return True
    return any(pattern.search(text) for pattern in MOJIBAKE_REGEXES)


def unique(values):
    result = []
    for value in values:
        if value is not None and value != "" and value not in result:
            result.append(value)
    return result


def weighted_sequence(weights):
    sequence = []
    for key, value in weights.items():
        sequence.extend([key] * max(1, int(round(value * 100))))
    return sequence or list(weights)


def style_for(index):
    styles = ["vi", "vi_no_diacritics", "en", "mixed_vi_en", "short_chat"]
    return styles[index % len(styles)]


def render_source_message(plan, templates, alias_renderer, plan_index):
    family_config = templates["families"].get(plan["question_family"])
    if not family_config:
        raise SystemExit(f"{plan['plan_group_id']} has no template family")
    language_order = ["vi", "en", "vi_no_diacritics", "mixed_vi_en", "short_chat", "technical_code"]
    candidates = family_candidates(family_config, language_order, plan)
    if not candidates:
        raise SystemExit(f"{plan['plan_group_id']} has no usable template")
    style, template, _index = candidates[plan_index % len(candidates)]
    values = alias_renderer.render_values(plan, style, plan_index)
    return variants_for(render_template(template, values), style)[0]


def indicator_alias(plan, alias_renderer, style="vi"):
    codes = alias_renderer.indicator_codes(plan)
    return alias_renderer.indicator_alias(codes[0] if codes else None, style)


def country_aliases(plan, alias_renderer, style="vi"):
    codes = alias_renderer.country_codes(plan)
    return [alias_renderer.country_alias(code, style) for code in codes]


def period_text(parsed, style="vi"):
    start = parsed.get("start_year")
    end = parsed.get("end_year")
    if start is None and end is None:
        return ""
    if start == end or end is None:
        return f"in {start}" if style == "en" else f"năm {start}"
    if start is None:
        return f"to {end}" if style == "en" else f"đến {end}"
    return f"from {start} to {end}" if style == "en" else f"giai đoạn {start}-{end}"


def compact_hard_message(plan, alias_renderer, style):
    parsed = plan["parsed_query"]
    indicator = indicator_alias(plan, alias_renderer, "vi_no_diacritics" if style != "en" else "en")
    countries = country_aliases(plan, alias_renderer, "vi_no_diacritics" if style != "en" else "en")
    country_text = " ".join(countries) if countries else ("all countries" if style == "en" else "tat ca nuoc")
    period = period_text(parsed, "en" if style == "en" else "vi")
    limit = parsed.get("limit")
    if plan["intent"] == "FOLLOW_UP":
        return follow_up_short_message(plan, alias_renderer, 0)
    if plan["intent"] == "NEED_CLARIFICATION":
        return clarification_short_message(plan, alias_renderer)
    if plan["intent"] in {"RANKING", "RANK_BY_CHANGE"}:
        direction = "bottom" if parsed.get("ranking_order") == "asc" else "top"
        if style != "en":
            direction = "thap nhat" if parsed.get("ranking_order") == "asc" else "cao nhat"
        return normalize(f"{direction} {limit or 10} {indicator} {period}?")
    return normalize(f"{country_text} {indicator} {period}?")


def follow_up_short_message(plan, alias_renderer, offset):
    options = [
        "còn Thái Lan?",
        "thêm Mỹ vào",
        "đổi sang lạm phát",
        "vẽ chart đi",
        "giải thích kết quả này",
        "chỉ xem ASEAN",
        "bỏ Việt Nam ra",
    ]
    context = plan["render_context"].get("context_ref")
    if context:
        options.append(f"{context} thì sao?")
    return options[offset % len(options)]


def clarification_short_message(plan, alias_renderer):
    family = plan["question_family"]
    parsed = plan["parsed_query"]
    year = parsed.get("start_year") or parsed.get("end_year") or plan["render_context"].get("year") or 2020
    if family == "missing_indicator":
        countries = country_aliases(plan, alias_renderer, "vi_no_diacritics")
        return f"{countries[0] if countries else 'Vietnam'} {year} chỉ số nào?"
    if family == "missing_country":
        return f"{indicator_alias(plan, alias_renderer, 'vi_no_diacritics')} {year} nước nào?"
    if family == "missing_year_for_ranking":
        return f"top {parsed.get('limit') or 10} {indicator_alias(plan, alias_renderer, 'vi_no_diacritics')} năm nào?"
    if family == "ambiguous_time_range":
        return f"{indicator_alias(plan, alias_renderer, 'vi_no_diacritics')} mấy năm gần đây?"
    return normalize(render_source_message(plan, GLOBAL_TEMPLATES, GLOBAL_ALIAS_RENDERER, 0))


def light_typo(text, rng, max_typos):
    protected = re.compile(r"^\d+(?:\.\d+)?$|^[A-Z]{3}$|^[A-Za-z0-9_]+_[A-Za-z0-9_]+$")
    words = text.split()
    indexes = [i for i, word in enumerate(words) if len(re.sub(r"\W", "", word)) > 5 and not protected.match(word.strip(".,?!:;"))]
    rng.shuffle(indexes)
    for index in indexes[:max_typos]:
        word = words[index]
        core = word.strip(".,?!:;")
        if len(core) > 5:
            pos = min(2, len(core) - 2)
            typo = core[:pos] + core[pos + 1] + core[pos] + core[pos + 2 :]
            words[index] = word.replace(core, typo, 1)
    return " ".join(words)


def abbreviate(text):
    replacements = {
        "Việt Nam": "VN",
        "Viet Nam": "VN",
        "Vietnam": "VN",
        "Thailand": "Thai",
        "Thái Lan": "Thai",
        "United States": "US",
        "Mỹ": "US",
        "public debt": "debt",
        "government debt": "debt",
        "nợ công": "debt",
        "inflation": "infl",
        "lạm phát": "infl",
        "unemployment": "unemp",
        "thất nghiệp": "unemp",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def mixed_language_message(plan, alias_renderer):
    parsed = plan["parsed_query"]
    indicator = indicator_alias(plan, alias_renderer, "vi")
    countries = country_aliases(plan, alias_renderer, "en")
    country_text = " and ".join(countries) if countries else "all countries"
    return normalize(f"Show {indicator} cho {country_text} {period_text(parsed, 'en')}.")


def punctuation_noise_message(plan, alias_renderer):
    parsed = plan["parsed_query"]
    indicator = indicator_alias(plan, alias_renderer, "vi_no_diacritics")
    countries = country_aliases(plan, alias_renderer, "vi_no_diacritics")
    return normalize(f"{', '.join(countries) if countries else 'all'} - {indicator}: {period_text(parsed)}?")


def case_noise(text):
    lowered = text.lower()
    for token in re.findall(r"\b[A-Z]{3}\b", text):
        lowered = re.sub(rf"\b{token.lower()}\b", token, lowered)
    return lowered


def hard_case_allowed(case_type, plan):
    family = plan["question_family"]
    intent = plan["intent"]
    if case_type == "ambiguous_alias":
        return intent == "NEED_CLARIFICATION" and family in {"ambiguous_country", "ambiguous_indicator"}
    if case_type == "missing_slot_clarification":
        return intent == "NEED_CLARIFICATION"
    if case_type == "follow_up_short":
        return intent == "FOLLOW_UP"
    return True


def hard_case_transform(case_type, plan, base_message, alias_renderer, rng, sample_offset):
    transformations = [case_type]
    if case_type == "missing_diacritics":
        return strip_diacritics(base_message), transformations
    if case_type == "light_typo":
        return light_typo(base_message, rng, 2), transformations
    if case_type == "abbreviation":
        return abbreviate(base_message), transformations
    if case_type == "short_chat":
        return compact_hard_message(plan, alias_renderer, "short_chat"), transformations
    if case_type == "mixed_language":
        return mixed_language_message(plan, alias_renderer), transformations
    if case_type == "punctuation_noise":
        return punctuation_noise_message(plan, alias_renderer), transformations
    if case_type == "case_noise":
        return case_noise(base_message), transformations
    if case_type == "ambiguous_alias":
        return base_message, transformations
    if case_type == "missing_slot_clarification":
        return clarification_short_message(plan, alias_renderer), transformations
    if case_type == "follow_up_short":
        return follow_up_short_message(plan, alias_renderer, sample_offset), transformations
    return base_message, ["safe_template_fill"]


def fallback_variants(message, style):
    extra = []
    core = message.rstrip(".?!")
    extra.extend(variants_for(message, style))
    extra.extend(
        [
            normalize(f"giúp tôi {core}."),
            normalize(f"cho tôi {core}."),
            normalize(f"{core} nhé."),
            normalize(f"{core} lần này."),
            normalize(f"{core} trong ngữ cảnh này."),
            normalize(f"{core}?"),
        ]
    )
    return unique(extra)


def valid_message(text, seen_messages):
    if not isinstance(text, str) or not text.strip():
        return False
    if len(text) > 500:
        return False
    if PLACEHOLDER_RE.search(text):
        return False
    if has_mojibake(text):
        return False
    if text in seen_messages:
        return False
    return True


def build_sample(sample_id, generation_source, plan, language_style, user_message, render_metadata, hard_case_type=None):
    assistant_json = plan["parsed_query"]
    assistant_content = json.dumps(assistant_json, ensure_ascii=False, separators=(",", ":"))
    sample = {
        "sample_id": sample_id,
        "plan_group_id": plan["plan_group_id"],
        "version": "v1",
        "generation_source": generation_source,
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
        "render_metadata": render_metadata,
    }
    if hard_case_type:
        sample["hard_case_type"] = hard_case_type
    return sample


def generate_hard_cases(plans, config, templates, alias_renderer, existing_messages):
    rng = random.Random(config["random_seed"])
    case_sequence = weighted_sequence(config["hard_case_types"])
    samples = []
    warnings = []
    fallback_filled = 0
    samples_by_type = Counter()
    seen_messages = set(existing_messages)
    plan_index_by_id = {plan["plan_group_id"]: index for index, plan in enumerate(plans)}

    for plan in plans:
        base_message = render_source_message(plan, templates, alias_renderer, plan_index_by_id[plan["plan_group_id"]])
        messages_in_plan = set()
        for offset in range(plan["target_sample_count"]):
            selected = None
            for attempt in range(80):
                case_type = case_sequence[(len(samples) + offset + attempt) % len(case_sequence)]
                if not hard_case_allowed(case_type, plan):
                    continue
                style = style_for(len(samples) + attempt)
                message, transformations = hard_case_transform(case_type, plan, base_message, alias_renderer, rng, offset + attempt)
                if style == "vi_no_diacritics" or case_type == "missing_diacritics":
                    message = strip_diacritics(message)
                message = normalize(message)
                for candidate in fallback_variants(message, style):
                    if candidate not in messages_in_plan and valid_message(candidate, seen_messages):
                        selected = (case_type, style, candidate, transformations)
                        break
                if selected:
                    break
            if not selected:
                fallback_filled += 1
                style = "vi"
                case_type = "short_chat" if plan["intent"] != "NEED_CLARIFICATION" else "missing_slot_clarification"
                for candidate in fallback_variants(compact_hard_message(plan, alias_renderer, style), style):
                    if candidate not in messages_in_plan and valid_message(candidate, seen_messages):
                        selected = (case_type, style, candidate, ["safe_template_fill"])
                        break
            if not selected:
                raise SystemExit(f"could not generate hard case for {plan['plan_group_id']}")
            case_type, style, user_message, transformations = selected
            sample_id = f"hard_{len(samples) + 1:06d}"
            samples.append(
                build_sample(
                    sample_id,
                    "hard_cases",
                    plan,
                    style,
                    user_message,
                    {
                        "source": "hard_case_generator",
                        "hard_case_type": case_type,
                        "base_message": base_message,
                        "transformations": transformations,
                    },
                    hard_case_type=case_type,
                )
            )
            samples_by_type[case_type] += 1
            seen_messages.add(user_message)
            messages_in_plan.add(user_message)

    target = sum(plan["target_sample_count"] for plan in plans)
    return samples, build_hard_report(samples, target, samples_by_type, fallback_filled, warnings)


OFF_TOPIC_MESSAGES = {
    "off_topic_programming": [
        "Viết giúp tôi một component React cho màn hình đăng nhập{suffix}.",
        "Debug đoạn JavaScript này giúp tôi{suffix}.",
        "Create a Python utility for sorting nested lists{suffix}.",
        "Làm một hàm parse CSV nhỏ bằng Go{suffix}.",
        "Gợi ý cấu trúc folder cho app mobile{suffix}.",
    ],
    "off_topic_personal_advice": [
        "Tôi nên ngủ sớm hơn như thế nào{suffix}?",
        "Cho tôi lời khuyên học tiếng Nhật cuối tuần{suffix}.",
        "Should I learn guitar or piano first{suffix}?",
        "Lên lịch tập gym nhẹ cho người mới{suffix}.",
        "Tư vấn cách quản lý thời gian cá nhân{suffix}.",
    ],
    "off_topic_general_knowledge": [
        "Vì sao bầu trời có màu xanh{suffix}?",
        "Ai phát minh ra bóng đèn{suffix}?",
        "Explain how rainbows form{suffix}.",
        "Kể ngắn về lịch sử cờ vua{suffix}.",
        "Mặt trăng cách Trái Đất bao xa{suffix}?",
    ],
    "off_topic_entertainment": [
        "Kể một chuyện cười ngắn{suffix}.",
        "Gợi ý phim hài tối nay{suffix}.",
        "Write a short fantasy scene{suffix}.",
        "Tóm tắt một bài hát pop tưởng tượng{suffix}.",
        "Đặt tên cho một ban nhạc indie{suffix}.",
    ],
    "off_topic_unrelated_business": [
        "Review laptop văn phòng này giúp tôi{suffix}.",
        "Viết mô tả sản phẩm cho balo du lịch{suffix}.",
        "Suggest a cafe menu layout{suffix}.",
        "Lập kế hoạch bán bánh cuối tuần{suffix}.",
        "Đặt slogan cho shop hoa nhỏ{suffix}.",
    ],
}


def unsupported_message(plan, alias_renderer, n):
    family = plan["question_family"]
    parsed = plan["parsed_query"]
    indicator = indicator_alias(plan, alias_renderer, "vi")
    countries = country_aliases(plan, alias_renderer, "vi")
    country = countries[0] if countries else "Việt Nam"
    year = parsed.get("end_year") or parsed.get("start_year") or 2050
    suffix = NATURAL_VARIATION_SUFFIXES[n % len(NATURAL_VARIATION_SUFFIXES)]
    if family == "unsupported_forecast_advanced":
        return f"Dự báo nâng cao {indicator} của {country} đến năm {year} bằng mô hình chuyên sâu{suffix}."
    if family == "unsupported_arima_modeling":
        return f"Chạy ARIMA cho {indicator} của {country}{suffix}."
    if family == "unsupported_causal_claim":
        return f"Chứng minh {indicator} gây ra thất nghiệp ở {country}{suffix}."
    if family == "unsupported_no_data_year":
        return f"{indicator} của {country} năm {year} là bao nhiêu{suffix}?"
    if family == "unsupported_raw_sql_request":
        return f"Viết SQL query trực tiếp lấy bảng gold_fiscal_monetary{suffix}."
    return f"Yêu cầu phân tích không được hỗ trợ{suffix}."


def generate_offtopic_unsupported(plans, config, alias_renderer, existing_messages):
    samples = []
    warnings = []
    seen_messages = set(existing_messages)
    for plan in plans:
        messages_in_plan = set()
        for offset in range(plan["target_sample_count"]):
            n = len(samples) + 1
            style = config["language_styles"][n % len(config["language_styles"])]
            if plan["intent"] == "OFF_TOPIC":
                pool = OFF_TOPIC_MESSAGES.get(plan["question_family"], OFF_TOPIC_MESSAGES["off_topic_programming"])
                user_message = naturalize_template(pool[(n + offset) % len(pool)], n + offset)
            else:
                user_message = unsupported_message(plan, alias_renderer, n)
            user_message = normalize(user_message)
            if style == "vi_no_diacritics":
                user_message = strip_diacritics(user_message)
            for candidate in fallback_variants(user_message, style):
                if candidate not in messages_in_plan and valid_message(candidate, seen_messages):
                    user_message = candidate
                    break
            if not valid_message(user_message, seen_messages):
                raise SystemExit(f"could not generate off_topic_unsupported for {plan['plan_group_id']}")
            sample_id = f"offuns_{len(samples) + 1:06d}"
            samples.append(
                build_sample(
                    sample_id,
                    "off_topic_unsupported",
                    plan,
                    style,
                    user_message,
                    {"source": "off_topic_unsupported_generator"},
                )
            )
            seen_messages.add(user_message)
            messages_in_plan.add(user_message)
    target = sum(plan["target_sample_count"] for plan in plans)
    return samples, build_offuns_report(samples, target, warnings)


def common_counters(samples):
    return (
        Counter(sample["intent"] for sample in samples),
        Counter(sample["question_family"] for sample in samples),
        Counter(sample["language_style"] for sample in samples),
        Counter(sample["user_message"] for sample in samples),
    )


def build_hard_report(samples, target, samples_by_type, fallback_filled, warnings):
    by_intent, by_family, by_style, messages = common_counters(samples)
    countries = Counter()
    indicators = Counter()
    for sample in samples:
        for code in sample["assistant_json"].get("countries") or []:
            countries[code] += 1
        for code in sample["assistant_json"].get("indicators") or []:
            indicators[code] += 1
    return {
        "version": "v1",
        "generation_source": "hard_cases",
        "target_samples": target,
        "generated_samples": len(samples),
        "missing_samples": max(0, target - len(samples)),
        "samples_by_intent": dict(sorted(by_intent.items())),
        "samples_by_family": dict(sorted(by_family.items())),
        "samples_by_language_style": dict(sorted(by_style.items())),
        "samples_by_hard_case_type": dict(sorted(samples_by_type.items())),
        "unique_user_messages": len(messages),
        "duplicate_user_messages": sum(count - 1 for count in messages.values() if count > 1),
        "unique_countries_used": len(countries),
        "unique_indicators_used": len(indicators),
        "fallback_filled_samples": fallback_filled,
        "warnings": warnings,
    }


def build_offuns_report(samples, target, warnings):
    by_intent, by_family, by_style, messages = common_counters(samples)
    return {
        "version": "v1",
        "generation_source": "off_topic_unsupported",
        "target_samples": target,
        "generated_samples": len(samples),
        "missing_samples": max(0, target - len(samples)),
        "samples_by_intent": dict(sorted(by_intent.items())),
        "samples_by_family": dict(sorted(by_family.items())),
        "samples_by_language_style": dict(sorted(by_style.items())),
        "unique_user_messages": len(messages),
        "duplicate_user_messages": sum(count - 1 for count in messages.values() if count > 1),
        "warnings": warnings,
    }


def main():
    global GLOBAL_TEMPLATES, GLOBAL_ALIAS_RENDERER
    hard_config = load_json(HARD_CONFIG_PATH)
    offuns_config = load_json(OFFUNS_CONFIG_PATH)
    templates = load_json(QUESTION_TEMPLATES_PATH)
    country_catalog = load_json(COUNTRY_CATALOG_PATH)
    indicator_catalog = load_json(INDICATOR_CATALOG_PATH)
    load_json(PARSER_ENUMS_PATH)
    plans = read_jsonl(BASE_PLANS_PATH)
    deterministic = read_jsonl(DETERMINISTIC_PATH)
    paraphrase = read_jsonl(PARAPHRASE_PATH)

    alias_renderer = AliasRenderer(country_catalog, indicator_catalog)
    GLOBAL_TEMPLATES = templates
    GLOBAL_ALIAS_RENDERER = alias_renderer
    existing_messages = {sample["user_message"] for sample in deterministic + paraphrase}

    hard_plans = [plan for plan in plans if plan["generation_bucket"] == hard_config["target_generation_bucket"]]
    offuns_plans = [plan for plan in plans if plan["generation_bucket"] == offuns_config["target_generation_bucket"]]
    hard_target = sum(plan["target_sample_count"] for plan in hard_plans)
    offuns_target = sum(plan["target_sample_count"] for plan in offuns_plans)
    if hard_target != hard_config["target_samples"]:
        print(f"WARNING hard config target {hard_config['target_samples']} != computed {hard_target}")
    if offuns_target != offuns_config["target_samples"]:
        print(f"WARNING off-topic config target {offuns_config['target_samples']} != computed {offuns_target}")

    hard_samples, hard_report = generate_hard_cases(hard_plans, hard_config, templates, alias_renderer, existing_messages)
    existing_plus_hard = existing_messages | {sample["user_message"] for sample in hard_samples}
    offuns_samples, offuns_report = generate_offtopic_unsupported(offuns_plans, offuns_config, alias_renderer, existing_plus_hard)

    write_jsonl(HARD_OUTPUT_PATH, hard_samples)
    write_json(HARD_REPORT_PATH, hard_report)
    write_jsonl(OFFUNS_OUTPUT_PATH, offuns_samples)
    write_json(OFFUNS_REPORT_PATH, offuns_report)

    print(f"hard target/generated: {hard_target}/{len(hard_samples)}")
    print(f"off_topic_unsupported target/generated: {offuns_target}/{len(offuns_samples)}")
    print(f"projected full dataset total: {len(deterministic) + len(paraphrase) + len(hard_samples) + len(offuns_samples)}")
    print(f"samples by hard_case_type: {hard_report['samples_by_hard_case_type']}")
    print(f"hard language styles: {hard_report['samples_by_language_style']}")
    print(f"offuns language styles: {offuns_report['samples_by_language_style']}")


if __name__ == "__main__":
    main()
