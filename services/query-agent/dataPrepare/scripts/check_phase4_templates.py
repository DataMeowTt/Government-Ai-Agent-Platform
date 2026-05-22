import json
import re
import string
from collections import Counter
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
REQUIRED_LANGUAGE_STYLES = {
    "vi",
    "vi_no_diacritics",
    "en",
    "mixed_vi_en",
    "technical_code",
    "short_chat",
}
OFF_TOPIC_FORBIDDEN_PLACEHOLDERS = {
    "indicator",
    "indicator_2",
    "indicator_list",
    "country",
    "country_2",
    "country_list",
    "year",
    "start_year",
    "end_year",
}
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
MOJIBAKE_MARKERS = [
    "Ã",
    "Â²",
    "Ä",
    "á»",
    "áº",
    "Æ",
    "�",
]
MOJIBAKE_REGEXES = [
    re.compile(r"[A-Za-zÀ-ỹ]\?[A-Za-zÀ-ỹ]"),
    re.compile(r"\?\?"),
    re.compile(r"(?:^|\s)\?[A-Za-zÀ-ỹ]"),
    re.compile(r"\b(?:d|ch|k|n|l|t|h|qu)\?", re.IGNORECASE),
    re.compile(r"tr\?\?", re.IGNORECASE),
]


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
    raise SystemExit(f"Phase 4 template check failed: {message}")


def iter_template_strings(templates):
    for language_style, values in templates.items():
        for template in values:
            yield language_style, template


def has_mojibake(text):
    lowered = text.lower()
    if any(literal.lower() in lowered for literal in MOJIBAKE_LITERALS):
        return True
    if any(marker in text for marker in MOJIBAKE_MARKERS):
        return True
    return any(pattern.search(text) for pattern in MOJIBAKE_REGEXES)


def printable(text):
    return text.encode("ascii", errors="backslashreplace").decode("ascii")


def collect_mojibake_findings(question_templates):
    findings = []

    placeholder_contract = question_templates.get("placeholder_contract", {})
    if isinstance(placeholder_contract, dict):
        for placeholder, description in placeholder_contract.items():
            if isinstance(description, str) and has_mojibake(description):
                findings.append(
                    {
                        "family_id": "placeholder_contract",
                        "language": placeholder,
                        "template": description,
                    }
                )

    families = question_templates.get("families", {})
    if not isinstance(families, dict):
        return findings

    for family_id, family in families.items():
        if not isinstance(family, dict):
            continue
        templates = family.get("templates", {})
        if not isinstance(templates, dict):
            continue
        for language_style, values in templates.items():
            if not isinstance(values, list):
                continue
            for template in values:
                if isinstance(template, str) and has_mojibake(template):
                    findings.append(
                        {
                            "family_id": family_id,
                            "language": language_style,
                            "template": template,
                        }
                    )
    return findings


def extract_placeholders(template, family_id):
    placeholders = set()
    formatter = string.Formatter()
    try:
        parsed = list(formatter.parse(template))
    except ValueError as exc:
        fail(f"{family_id} has invalid template braces: {template!r} ({exc})")

    for _literal, field_name, _format_spec, _conversion in parsed:
        if field_name is None:
            continue
        if not field_name:
            fail(f"{family_id} has empty placeholder in template: {template!r}")
        root_name = field_name.split(".", 1)[0].split("[", 1)[0]
        placeholders.add(root_name)
    return placeholders


def validate_root(question_templates):
    if "version" not in question_templates:
        fail("question_templates.version is required")

    language_styles = question_templates.get("template_language_styles")
    if not isinstance(language_styles, list):
        fail("question_templates.template_language_styles must be a list")
    missing_styles = sorted(REQUIRED_LANGUAGE_STYLES - set(language_styles))
    if missing_styles:
        fail(f"template_language_styles missing required styles: {missing_styles}")

    placeholder_contract = question_templates.get("placeholder_contract")
    if not isinstance(placeholder_contract, dict) or not placeholder_contract:
        fail("question_templates.placeholder_contract must be a non-empty object")

    families = question_templates.get("families")
    if not isinstance(families, dict) or not families:
        fail("question_templates.families must be a non-empty object")

    return language_styles, placeholder_contract, families


def validate_family_coverage(template_families, question_family_config):
    question_families = question_family_config.get("families")
    if not isinstance(question_families, list):
        fail("question_families.families must be a list")

    family_meta = {}
    for family in question_families:
        if not isinstance(family, dict) or not isinstance(family.get("id"), str):
            fail("question_families.families contains invalid family metadata")
        family_meta[family["id"]] = family

    expected_ids = set(family_meta)
    template_ids = set(template_families)
    missing_ids = sorted(expected_ids - template_ids)
    extra_ids = sorted(template_ids - expected_ids)
    if missing_ids:
        fail(f"missing template families: {missing_ids}")
    if extra_ids:
        fail(f"unknown template families: {extra_ids}")

    return family_meta


def validate_template_family(
    family_id,
    template_family,
    family_meta,
    language_styles,
    placeholder_contract,
):
    if not isinstance(template_family, dict):
        fail(f"{family_id} template family must be an object")

    if template_family.get("intent") != family_meta["intent"]:
        fail(
            f"{family_id}.intent mismatch: "
            f"{template_family.get('intent')} != {family_meta['intent']}"
        )

    if template_family.get("default_chart_preference") != family_meta["default_chart_preference"]:
        fail(
            f"{family_id}.default_chart_preference mismatch: "
            f"{template_family.get('default_chart_preference')} != "
            f"{family_meta['default_chart_preference']}"
        )

    templates = template_family.get("templates")
    if not isinstance(templates, dict):
        fail(f"{family_id}.templates must be an object")

    language_set = set(language_styles)
    unknown_languages = sorted(set(templates) - language_set)
    if unknown_languages:
        fail(f"{family_id}.templates has unknown language styles: {unknown_languages}")

    total_templates = 0
    language_counts = Counter()
    family_placeholders = set()

    for language_style, values in templates.items():
        if not isinstance(values, list):
            fail(f"{family_id}.templates.{language_style} must be a list")
        for template in values:
            if not isinstance(template, str) or not template.strip():
                fail(f"{family_id} has an empty template in {language_style}")
            placeholders = extract_placeholders(template, family_id)
            unknown_placeholders = sorted(set(placeholders) - set(placeholder_contract))
            if unknown_placeholders:
                fail(
                    f"{family_id} uses unknown placeholders {unknown_placeholders} "
                    f"in template: {template!r}"
                )
            family_placeholders.update(placeholders)
            total_templates += 1
            language_counts[language_style] += 1

    if total_templates == 0:
        fail(f"{family_id} must have at least one template string")

    priority = family_meta.get("priority")
    intent = family_meta["intent"]
    if priority == "high":
        vi_count = len(templates.get("vi", []))
        if intent in {"OFF_TOPIC", "UNSUPPORTED"}:
            if total_templates < 2:
                fail(f"{family_id} high priority OFF_TOPIC/UNSUPPORTED needs at least 2 templates")
        else:
            if vi_count < 2:
                fail(f"{family_id} high priority needs at least 2 vi templates")
            if not templates.get("en") and not templates.get("mixed_vi_en"):
                fail(f"{family_id} high priority needs at least one en or mixed_vi_en template")
            if not templates.get("short_chat"):
                fail(f"{family_id} high priority needs at least one short_chat template")

    return total_templates, language_counts, family_placeholders


def validate_domain_rules(family_id, family_meta, placeholders):
    warnings = []
    intent = family_meta["intent"]

    if intent == "OFF_TOPIC":
        forbidden = sorted(OFF_TOPIC_FORBIDDEN_PLACEHOLDERS & placeholders)
        if forbidden:
            fail(f"{family_id} OFF_TOPIC uses forbidden placeholders: {forbidden}")

    if intent == "FOLLOW_UP" and "context_ref" not in placeholders:
        warnings.append(f"WARNING {family_id}: FOLLOW_UP template has no context_ref placeholder")

    if intent == "VISUALIZATION_REQUEST" and not ({"chart_type", "output_format"} & placeholders):
        warnings.append(
            f"WARNING {family_id}: VISUALIZATION_REQUEST template has no chart_type/output_format"
        )

    if intent == "RANKING" and not ({"top_n", "year"} & placeholders):
        warnings.append(f"WARNING {family_id}: RANKING template has no top_n/year placeholder")

    if family_id in {
        "rank_by_absolute_change",
        "rank_by_pct_change",
        "rank_by_increase",
        "rank_by_decrease",
        "rank_by_recovery_after_event",
    } and "top_n" not in placeholders:
        warnings.append(f"WARNING {family_id}: rank-by-change template has no top_n placeholder")

    if family_id.startswith("visualization_") and not ({"chart_type", "output_format"} & placeholders):
        warnings.append(f"WARNING {family_id}: visualization family lacks output placeholder")

    if family_id in {
        "missing_indicator",
        "missing_country",
        "missing_year_for_ranking",
        "ambiguous_indicator",
        "ambiguous_country",
        "ambiguous_time_range",
    } and intent != "NEED_CLARIFICATION":
        fail(f"{family_id} must have intent NEED_CLARIFICATION")

    return warnings


def main():
    question_templates = load_json("configs/question_templates.v1.json")
    question_families = load_json("configs/question_families.v1.json")
    parser_intents = load_json("configs/parser_intents.v1.json")
    parser_enums = load_json("configs/parser_enums.v1.json")
    alias_rules = load_json("configs/alias_generation_rules.v1.json")

    if not isinstance(parser_intents, list) or not parser_intents:
        fail("parser_intents.v1.json must be a non-empty list")
    if not isinstance(parser_enums, dict) or not parser_enums:
        fail("parser_enums.v1.json must be a non-empty object")
    if not isinstance(alias_rules, dict) or not alias_rules:
        fail("alias_generation_rules.v1.json must be a non-empty object")

    language_styles, placeholder_contract, template_families = validate_root(question_templates)
    family_meta_by_id = validate_family_coverage(template_families, question_families)

    total_template_strings = 0
    templates_per_language = Counter()
    warnings = []
    mojibake_findings = collect_mojibake_findings(question_templates)

    for family_id in sorted(template_families):
        total, language_counts, placeholders = validate_template_family(
            family_id,
            template_families[family_id],
            family_meta_by_id[family_id],
            language_styles,
            placeholder_contract,
        )
        total_template_strings += total
        templates_per_language.update(language_counts)
        warnings.extend(validate_domain_rules(family_id, family_meta_by_id[family_id], placeholders))

    for warning in warnings:
        print(warning)

    print(f"total question families: {len(family_meta_by_id)}")
    print(f"total template families: {len(template_families)}")
    print(f"total template strings: {total_template_strings}")
    print(f"mojibake findings count: {len(mojibake_findings)}")
    print("templates per language style:")
    for language_style in language_styles:
        print(f"  {language_style}: {templates_per_language[language_style]}")
    print(f"warning count: {len(warnings)}")
    if mojibake_findings:
        print("mojibake examples:")
        for finding in mojibake_findings[:30]:
            print(
                "  "
                f"{finding['family_id']} / {finding['language']}: "
                f"{printable(finding['template'])}"
            )
        fail(f"mojibake findings detected: {len(mojibake_findings)}")
    print("PASS")


if __name__ == "__main__":
    main()
