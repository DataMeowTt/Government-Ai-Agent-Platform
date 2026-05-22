import json
import re
from collections import Counter
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT_DIR / "configs"
DATASET_DIR = ROOT_DIR / "datasets" / "parser"

QUESTION_TEMPLATES_PATH = CONFIG_DIR / "question_templates.v1.json"
COUNTRY_CATALOG_PATH = CONFIG_DIR / "country_catalog.v1.json"
INDICATOR_CATALOG_PATH = CONFIG_DIR / "indicator_catalog.v1.json"
ALIAS_RULES_PATH = CONFIG_DIR / "alias_generation_rules.v1.json"
BASE_PLANS_PATH = DATASET_DIR / "base_plans.v1.jsonl"
OUTPUT_PATH = DATASET_DIR / "parser_deterministic.v1.jsonl"
REPORT_PATH = DATASET_DIR / "parser_deterministic_report.v1.json"

SYSTEM_PROMPT = (
    "You are a semantic parser for a Government Economic Indicator AI Agent. "
    "Output only valid JSON. Do not answer the question."
)

PLACEHOLDER_RE = re.compile(r"{([^{}]+)}")
SPACE_RE = re.compile(r"\s+")


def load_json(path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def read_jsonl(path):
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


def normalize_message(text):
    text = SPACE_RE.sub(" ", text).strip()
    text = text.replace(" .", ".").replace(" ?", "?").replace(" ,", ",")
    return text


def lower_first(text):
    if not text:
        return text
    return text[:1].lower() + text[1:]


def strip_terminal_punctuation(text):
    return text.rstrip().rstrip(".?!").rstrip()


def with_question_mark(text):
    return strip_terminal_punctuation(text) + "?"


def with_period(text):
    stripped = text.rstrip()
    if stripped.endswith((".", "?", "!")):
        return stripped
    return stripped + "."


def join_aliases(values, style):
    values = [str(value) for value in values if value is not None and str(value)]
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    if style == "technical_code":
        return ", ".join(values)
    connector = " and " if style == "en" else " và "
    if style == "mixed_vi_en":
        connector = " and "
    return ", ".join(values[:-1]) + connector + values[-1]


class AliasRenderer:
    def __init__(self, country_catalog, indicator_catalog):
        self.countries = {item["code"]: item for item in country_catalog["countries"]}
        self.indicators = {item["code"]: item for item in indicator_catalog["indicators"]}

    def indicator_codes(self, plan):
        context = plan["render_context"]
        parsed = plan["parsed_query"]
        codes = []
        if context.get("indicator"):
            codes.append(context["indicator"])
        for key in ("indicator_2",):
            if context.get(key):
                codes.append(context[key])
        for code in context.get("indicator_list") or []:
            codes.append(code)
        for code in parsed.get("indicators") or []:
            codes.append(code)
        return self.unique(codes)

    def country_codes(self, plan):
        context = plan["render_context"]
        parsed = plan["parsed_query"]
        codes = []
        if context.get("country"):
            codes.append(context["country"])
        if context.get("country_2"):
            codes.append(context["country_2"])
        for code in context.get("country_list") or []:
            codes.append(code)
        for code in parsed.get("countries") or []:
            codes.append(code)
        return self.unique(codes)

    @staticmethod
    def unique(values):
        result = []
        for value in values:
            if value is not None and value not in result:
                result.append(value)
        return result

    def style_key(self, style, seed):
        if style == "technical_code":
            return "technical"
        if style == "mixed_vi_en":
            return "vi" if seed % 2 == 0 else "en"
        if style == "short_chat":
            return "vi_no_diacritics"
        return style

    def fallback_indicator(self, style):
        if style == "en":
            return "all indicators"
        if style == "technical_code":
            return "ALL_INDICATORS"
        if style == "vi_no_diacritics" or style == "short_chat":
            return "tat ca chi so"
        return "tất cả chỉ số"

    def fallback_country(self, style):
        if style == "en":
            return "all countries"
        if style == "technical_code":
            return "ALL_COUNTRIES"
        if style == "vi_no_diacritics" or style == "short_chat":
            return "tat ca quoc gia"
        return "tất cả quốc gia"

    def indicator_alias(self, code, style, seed=0):
        if not code:
            return self.fallback_indicator(style)
        if style == "technical_code":
            return code
        item = self.indicators.get(code)
        if not item:
            return code
        hints = item.get("question_templates_hint") or {}
        key = self.style_key(style, seed)
        if hints.get(key):
            return hints[key]
        aliases = item.get("aliases") or []
        if style == "short_chat":
            candidates = [alias for alias in aliases if alias != code]
            return min(candidates or aliases or [code], key=len)
        return aliases[0] if aliases else code

    def country_alias(self, code, style, seed=0):
        if not code:
            return self.fallback_country(style)
        if style == "technical_code":
            return code
        item = self.countries.get(code)
        if not item:
            return code
        hints = item.get("question_templates_hint") or {}
        key = "iso3" if style == "technical_code" else self.style_key(style, seed)
        if hints.get(key):
            return hints[key]
        aliases = item.get("aliases") or []
        if style == "short_chat":
            candidates = [alias for alias in aliases if alias != code]
            return min(candidates or aliases or [code], key=len)
        return aliases[0] if aliases else code

    def event_alias(self, value, style):
        if not value:
            value = "COVID"
        aliases = {
            "COVID": {
                "vi": "đại dịch COVID",
                "vi_no_diacritics": "dai dich COVID",
                "en": "COVID-19",
                "mixed_vi_en": "COVID-19",
                "technical_code": "COVID",
                "short_chat": "COVID",
            },
            "GFC_2008": {
                "vi": "khủng hoảng tài chính 2008",
                "vi_no_diacritics": "khung hoang tai chinh 2008",
                "en": "the 2008 financial crisis",
                "mixed_vi_en": "2008 financial crisis",
                "technical_code": "GFC_2008",
                "short_chat": "GFC 2008",
            },
            "ASIAN_FINANCIAL_CRISIS_1997": {
                "vi": "khủng hoảng tài chính châu Á 1997",
                "vi_no_diacritics": "khung hoang tai chinh chau A 1997",
                "en": "the 1997 Asian financial crisis",
                "mixed_vi_en": "Asian financial crisis 1997",
                "technical_code": "ASIAN_FINANCIAL_CRISIS_1997",
                "short_chat": "AFC 1997",
            },
        }
        return aliases.get(value, {}).get(style) or aliases.get(value, {}).get("en") or str(value)

    def relative_time_alias(self, value, style, event_text):
        if not value:
            value = "recent"
        vi = {
            "latest": "mới nhất",
            "recent": "gần đây",
            "last_3_years": "3 năm gần nhất",
            "last_5_years": "5 năm gần nhất",
            "last_10_years": "10 năm gần nhất",
            "after_event": f"sau {event_text}",
            "before_event": f"trước {event_text}",
        }
        vi_plain = {
            "latest": "moi nhat",
            "recent": "gan day",
            "last_3_years": "3 nam gan nhat",
            "last_5_years": "5 nam gan nhat",
            "last_10_years": "10 nam gan nhat",
            "after_event": f"sau {event_text}",
            "before_event": f"truoc {event_text}",
        }
        en = {
            "latest": "latest",
            "recent": "recent",
            "last_3_years": "last 3 years",
            "last_5_years": "last 5 years",
            "last_10_years": "last 10 years",
            "after_event": f"after {event_text}",
            "before_event": f"before {event_text}",
        }
        if style == "en" or style == "technical_code":
            return en.get(value, str(value))
        if style == "vi_no_diacritics" or style == "short_chat":
            return vi_plain.get(value, str(value))
        return vi.get(value, str(value))

    def chart_alias(self, value, style):
        if not value:
            value = "none"
        if style == "en":
            mapping = {
                "line": "line chart",
                "bar": "bar chart",
                "table": "table",
                "scatter": "scatter plot",
                "none": "no chart",
            }
        elif style == "technical_code":
            mapping = {"line": "line", "bar": "bar", "table": "table", "scatter": "scatter", "none": "none"}
        elif style == "vi_no_diacritics" or style == "short_chat":
            mapping = {
                "line": "bieu do duong",
                "bar": "bieu do cot",
                "table": "bang",
                "scatter": "scatter plot",
                "none": "khong bieu do",
            }
        else:
            mapping = {
                "line": "biểu đồ đường",
                "bar": "biểu đồ cột",
                "table": "bảng",
                "scatter": "scatter plot",
                "none": "không biểu đồ",
            }
        return mapping.get(value, str(value))

    def output_format_alias(self, value, style):
        if not value:
            value = "table"
        if value == "short_summary":
            return "short summary" if style == "en" else "tóm tắt ngắn"
        if value == "report_paragraph":
            return "report paragraph" if style == "en" else "đoạn báo cáo"
        return str(value)

    def context_ref_alias(self, value, style):
        if value:
            return str(value)
        if style == "en":
            return "the previous result"
        if style == "short_chat":
            return "cái này"
        if style == "vi_no_diacritics":
            return "ket qua truoc"
        return "kết quả trước"

    def theme_alias(self, value, style):
        if not value:
            value = "fiscal_monetary"
        vi = {
            "fiscal_monetary": "tài khóa và tiền tệ",
            "growth_dynamics": "tăng trưởng",
            "social_welfare": "xã hội",
            "structural_composition": "cấu trúc kinh tế",
            "crisis_risk": "rủi ro khủng hoảng",
        }
        vi_plain = {
            "fiscal_monetary": "tai khoa va tien te",
            "growth_dynamics": "tang truong",
            "social_welfare": "xa hoi",
            "structural_composition": "cau truc kinh te",
            "crisis_risk": "rui ro khung hoang",
        }
        en = {
            "fiscal_monetary": "fiscal and monetary indicators",
            "growth_dynamics": "growth",
            "social_welfare": "social indicators",
            "structural_composition": "structural indicators",
            "crisis_risk": "crisis risk",
        }
        if style == "en" or style == "technical_code":
            return en.get(value, str(value))
        if style == "vi_no_diacritics" or style == "short_chat":
            return vi_plain.get(value, str(value))
        return vi.get(value, str(value))

    def condition_alias(self, plan, style, seed):
        context = plan["render_context"]
        if context.get("condition"):
            return str(context["condition"])
        parsed = plan["parsed_query"]
        threshold = context.get("threshold", parsed.get("threshold"))
        indicator = self.indicator_alias((self.indicator_codes(plan) or [None])[0], style, seed)
        if threshold is not None:
            if style == "en":
                return f"{indicator} above {threshold}"
            return f"{indicator} trên {threshold}"
        return indicator

    def render_values(self, plan, style, seed):
        context = plan["render_context"]
        parsed = plan["parsed_query"]
        indicator_codes = self.indicator_codes(plan)
        country_codes = self.country_codes(plan)
        event_value = context.get("event") or parsed.get("event_time")
        event_text = self.event_alias(event_value, style)
        chart_value = context.get("chart_type") or parsed.get("chart_preference")
        theme_value = context.get("theme")
        if not theme_value and indicator_codes and indicator_codes[0] in self.indicators:
            theme_value = self.indicators[indicator_codes[0]].get("category")

        values = {
            "indicator": self.indicator_alias(indicator_codes[0] if indicator_codes else None, style, seed),
            "indicator_2": self.indicator_alias(
                indicator_codes[1] if len(indicator_codes) > 1 else (indicator_codes[0] if indicator_codes else None),
                style,
                seed + 1,
            ),
            "indicator_list": join_aliases(
                [self.indicator_alias(code, style, seed + index) for index, code in enumerate(indicator_codes)]
                or [self.fallback_indicator(style)],
                style,
            ),
            "country": self.country_alias(country_codes[0] if country_codes else None, style, seed),
            "country_2": self.country_alias(
                country_codes[1] if len(country_codes) > 1 else (country_codes[0] if country_codes else None),
                style,
                seed + 1,
            ),
            "country_list": join_aliases(
                [self.country_alias(code, style, seed + index) for index, code in enumerate(country_codes)]
                or [self.fallback_country(style)],
                style,
            ),
            "country_group": self.country_group_alias(plan, style),
            "year": context.get("year") or parsed.get("start_year") or parsed.get("end_year") or "",
            "start_year": context.get("start_year") or parsed.get("start_year") or "",
            "end_year": context.get("end_year") or parsed.get("end_year") or "",
            "period_1": context.get("period_1") or self.period_from_query(parsed) or "",
            "period_2": context.get("period_2") or "",
            "event": event_text,
            "relative_time": self.relative_time_alias(context.get("relative_time") or parsed.get("relative_time"), style, event_text),
            "top_n": context.get("top_n") or parsed.get("limit") or "",
            "threshold": context.get("threshold") if context.get("threshold") is not None else parsed.get("threshold"),
            "chart_type": self.chart_alias(chart_value, style),
            "output_format": self.output_format_alias(context.get("output_format"), style),
            "context_ref": self.context_ref_alias(context.get("context_ref"), style),
            "condition": self.condition_alias(plan, style, seed),
            "theme": self.theme_alias(theme_value, style),
        }
        return {key: "" if value is None else str(value) for key, value in values.items()}

    def country_group_alias(self, plan, style):
        context = plan["render_context"]
        parsed = plan["parsed_query"]
        value = context.get("country_group")
        if not value and parsed.get("country_groups"):
            value = parsed["country_groups"][0]
        if not value:
            value = "ASEAN"
        return str(value)

    @staticmethod
    def period_from_query(parsed):
        start = parsed.get("start_year")
        end = parsed.get("end_year")
        if start is not None and end is not None:
            return f"{start}-{end}"
        if start is not None:
            return str(start)
        if end is not None:
            return str(end)
        return None


def template_placeholders(template):
    return set(PLACEHOLDER_RE.findall(template))


def allowed_template_for_plan(plan, template):
    placeholders = template_placeholders(template)
    family = plan["question_family"]
    if plan["intent"] == "NEED_CLARIFICATION":
        if family in {"missing_indicator", "ambiguous_indicator"} and placeholders & {
            "indicator",
            "indicator_2",
            "indicator_list",
        }:
            return False
        if family in {"missing_country", "ambiguous_country"} and placeholders & {
            "country",
            "country_2",
            "country_list",
        }:
            return False
        if family == "missing_year_for_ranking" and placeholders & {"year", "start_year", "end_year"}:
            return False
    return True


def family_candidates(family_config, language_order, plan):
    templates_by_style = family_config.get("templates") or {}
    candidates = []
    for style in language_order:
        for index, template in enumerate(templates_by_style.get(style) or []):
            if allowed_template_for_plan(plan, template):
                candidates.append((style, template, index))
    if not candidates:
        for style, templates in templates_by_style.items():
            for index, template in enumerate(templates):
                candidates.append((style, template, index))
    return candidates


def render_template(template, values):
    missing = sorted(template_placeholders(template) - set(values))
    if missing:
        raise SystemExit(f"template has unsupported placeholders: {missing}")
    return normalize_message(template.format(**values))


def variants_for(text, style):
    base = with_period(text)
    question = with_question_mark(text)
    core = strip_terminal_punctuation(text)
    lowered = lower_first(core)
    if style == "en":
        variants = [
            base,
            question,
            f"Please {lowered}.",
            f"Could you {lowered}?",
            f"{core}, please.",
            f"I need this: {lowered}.",
            f"For this query, {lowered}.",
            f"Can you {lowered}?",
        ]
        prefixes = ["Please ", "Now ", "Also ", "For this query, ", "In this context, ", "For the current result, "]
        suffixes = [
            " please",
            " for this query",
            " in this context",
            " for the current result",
            " this time",
            " here",
            " again",
            " only",
        ]
    elif style == "technical_code":
        variants = [
            base,
            question,
            f"QUERY: {core}.",
            f"GET {core}.",
            f"RUN {core}.",
            f"{core} pls.",
            f"Need {core}.",
            f"Check {core}.",
        ]
        prefixes = ["QUERY ", "GET ", "RUN ", "CHECK ", "NEED ", "FILTER "]
        suffixes = [" now", " pls", " current_context", " this_time", " only", " again"]
    elif style == "short_chat":
        variants = [
            base,
            question,
            f"giúp tôi {lowered}.",
            f"cho tôi {lowered}.",
            f"{core} nhé.",
            f"{core} giúp tôi.",
            f"check {lowered}.",
            f"xem {lowered}.",
        ]
        prefixes = ["giúp tôi ", "cho tôi ", "xem ", "check ", "thử ", "lần này "]
        suffixes = [" giúp tôi", " cho tôi", " nhé", " nha", " lần này", " thôi", " trong ngữ cảnh này", " ở truy vấn này"]
    else:
        variants = [
            base,
            question,
            f"Giúp tôi {lowered}.",
            f"Cho tôi {lowered}.",
            f"Vui lòng {lowered}.",
            f"{core} giúp tôi.",
            f"{core} cho tôi.",
            f"Bạn xem {lowered}.",
        ]
        if style == "vi_no_diacritics":
            prefixes = ["Giup toi ", "Cho toi ", "Vui long ", "Ban xem ", "Hay ", "Lan nay "]
            suffixes = [
                " giup toi",
                " cho toi",
                " nhe",
                " lan nay",
                " thoi",
                " trong ngu canh nay",
                " o truy van nay",
                " cho ket qua truoc",
            ]
        else:
            prefixes = ["Giúp tôi ", "Cho tôi ", "Vui lòng ", "Bạn xem ", "Hãy ", "Lần này "]
            suffixes = [
                " giúp tôi",
                " cho tôi",
                " nhé",
                " lần này",
                " thôi",
                " trong ngữ cảnh này",
                " ở truy vấn này",
                " cho kết quả trước",
            ]

    for prefix in prefixes:
        variants.append(f"{prefix}{lowered}.")
        variants.append(f"{prefix}{lowered}?")
    for suffix in suffixes:
        variants.append(f"{core}{suffix}.")
        variants.append(f"{core}{suffix}?")
    for prefix in prefixes:
        for suffix in suffixes:
            variants.append(f"{prefix}{lowered}{suffix}.")
            variants.append(f"{prefix}{lowered}{suffix}?")

    result = []
    for variant in variants:
        variant = normalize_message(variant)
        if variant and variant not in result:
            result.append(variant)
    return result


def build_sample(sample_id, plan, style, template, template_index, user_message, aliases_used):
    assistant_json = plan["parsed_query"]
    assistant_content = json.dumps(assistant_json, ensure_ascii=False, separators=(",", ":"))
    return {
        "sample_id": sample_id,
        "plan_group_id": plan["plan_group_id"],
        "version": "v1",
        "generation_source": "deterministic_template",
        "intent": plan["intent"],
        "question_family": plan["question_family"],
        "language_style": style,
        "user_message": user_message,
        "assistant_json": assistant_json,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": assistant_content},
        ],
        "render_metadata": {
            "template_id": f"{plan['question_family']}::{style}::{template_index}",
            "template": template,
            "aliases_used": aliases_used,
        },
    }


def aliases_used_for(template, values):
    placeholders = template_placeholders(template)
    return {key: values[key] for key in sorted(placeholders) if key in values}


def render_samples(plans, templates, alias_renderer):
    language_order = templates["template_language_styles"]
    family_configs = templates["families"]
    samples = []
    global_messages = set()
    sample_number = 1

    for plan_index, plan in enumerate(plans):
        if plan["generation_bucket"] != "deterministic_template":
            continue
        family_id = plan["question_family"]
        if family_id not in family_configs:
            raise SystemExit(f"{plan['plan_group_id']} has no templates for family {family_id}")
        candidates = family_candidates(family_configs[family_id], language_order, plan)
        if not candidates:
            raise SystemExit(f"{plan['plan_group_id']} has no usable templates")

        messages_in_plan = set()
        target_count = plan["target_sample_count"]
        for sample_offset in range(target_count):
            selected = None
            search_budget = max(1, len(candidates)) * 12
            for attempt in range(search_budget):
                candidate_index = (plan_index + sample_offset + attempt) % len(candidates)
                style, template, template_index = candidates[candidate_index]
                values = alias_renderer.render_values(plan, style, sample_offset + attempt)
                rendered = render_template(template, values)
                for variant in variants_for(rendered, style):
                    if variant not in messages_in_plan and variant not in global_messages:
                        selected = (style, template, template_index, variant, aliases_used_for(template, values))
                        break
                if selected:
                    break
            if not selected:
                style, template, template_index = candidates[(plan_index + sample_offset) % len(candidates)]
                values = alias_renderer.render_values(plan, style, sample_offset)
                rendered = render_template(template, values)
                variants = variants_for(rendered, style)
                for variant in variants:
                    if variant not in messages_in_plan:
                        selected = (style, template, template_index, variant, aliases_used_for(template, values))
                        break
            if not selected:
                raise SystemExit(f"could not create unique message inside {plan['plan_group_id']}")

            style, template, template_index, user_message, aliases_used = selected
            sample_id = f"det_{sample_number:06d}"
            samples.append(build_sample(sample_id, plan, style, template, template_index, user_message, aliases_used))
            messages_in_plan.add(user_message)
            global_messages.add(user_message)
            sample_number += 1
    return samples


def build_report(samples):
    samples_by_intent = Counter()
    samples_by_family = Counter()
    samples_by_language_style = Counter()
    indicators = Counter()
    countries = Counter()
    user_messages = Counter()
    plan_groups = set()

    for sample in samples:
        assistant_json = sample["assistant_json"]
        plan_groups.add(sample["plan_group_id"])
        samples_by_intent[sample["intent"]] += 1
        samples_by_family[sample["question_family"]] += 1
        samples_by_language_style[sample["language_style"]] += 1
        user_messages[sample["user_message"]] += 1
        for code in assistant_json.get("indicators") or []:
            indicators[code] += 1
        for code in assistant_json.get("countries") or []:
            countries[code] += 1

    duplicate_user_messages = sum(count - 1 for count in user_messages.values() if count > 1)
    return {
        "version": "v1",
        "generation_source": "deterministic_template",
        "total_samples": len(samples),
        "total_plan_groups_used": len(plan_groups),
        "samples_by_intent": dict(sorted(samples_by_intent.items())),
        "samples_by_family": dict(sorted(samples_by_family.items())),
        "samples_by_language_style": dict(sorted(samples_by_language_style.items())),
        "unique_user_messages": len(user_messages),
        "duplicate_user_messages": duplicate_user_messages,
        "unique_indicators_used": len(indicators),
        "unique_countries_used": len(countries),
        "top_indicators": [[code, count] for code, count in indicators.most_common(20)],
        "top_countries": [[code, count] for code, count in countries.most_common(20)],
    }


def write_outputs(samples, report):
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8", newline="\n") as file:
        for sample in samples:
            file.write(json.dumps(sample, ensure_ascii=False, separators=(",", ":")) + "\n")
    with REPORT_PATH.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)
        file.write("\n")


def main():
    templates = load_json(QUESTION_TEMPLATES_PATH)
    country_catalog = load_json(COUNTRY_CATALOG_PATH)
    indicator_catalog = load_json(INDICATOR_CATALOG_PATH)
    load_json(ALIAS_RULES_PATH)
    plans = read_jsonl(BASE_PLANS_PATH)

    alias_renderer = AliasRenderer(country_catalog, indicator_catalog)
    samples = render_samples(plans, templates, alias_renderer)
    report = build_report(samples)
    write_outputs(samples, report)

    print(f"total samples: {report['total_samples']}")
    print(f"total plan groups used: {report['total_plan_groups_used']}")
    print(f"samples by language style: {report['samples_by_language_style']}")
    print(f"unique user messages: {report['unique_user_messages']}")
    print(f"duplicate user messages: {report['duplicate_user_messages']}")
    print(f"wrote: {OUTPUT_PATH}")
    print(f"wrote: {REPORT_PATH}")


if __name__ == "__main__":
    main()
