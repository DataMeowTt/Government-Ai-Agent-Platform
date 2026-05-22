import json
from pathlib import Path

from render_deterministic_samples import (
    AliasRenderer,
    family_candidates,
    render_template,
    variants_for,
)


ROOT_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT_DIR / "configs"
DATASET_DIR = ROOT_DIR / "datasets" / "parser"
PROMPT_DIR = ROOT_DIR / "prompts"
BATCH_DIR = DATASET_DIR / "paraphrase_batches"
OUTPUT_DIR = DATASET_DIR / "paraphrase_outputs"

CONFIG_PATH = CONFIG_DIR / "paraphrase_generation.v1.json"
COUNTRY_CATALOG_PATH = CONFIG_DIR / "country_catalog.v1.json"
INDICATOR_CATALOG_PATH = CONFIG_DIR / "indicator_catalog.v1.json"
QUESTION_TEMPLATES_PATH = CONFIG_DIR / "question_templates.v1.json"
BASE_PLANS_PATH = DATASET_DIR / "base_plans.v1.jsonl"
PROMPT_TEMPLATE_PATH = PROMPT_DIR / "paraphrase_prompt_template.v1.txt"
MANIFEST_PATH = BATCH_DIR / "batch_manifest.v1.json"
README_PATH = OUTPUT_DIR / "README_INPUT_FORMAT.txt"


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


def unique(values):
    result = []
    for value in values:
        if value is not None and value != "" and value not in result:
            result.append(value)
    return result


def alias_terms(code, catalog_by_code):
    item = catalog_by_code.get(code)
    if not item:
        return [code]
    terms = [code, item.get("name")]
    hints = item.get("question_templates_hint") or {}
    for key in ("vi", "vi_no_diacritics", "en", "technical", "iso3"):
        terms.append(hints.get(key))
    terms.extend(item.get("aliases") or [])
    return unique([term for term in terms if isinstance(term, str)])[:12]


def weighted_language_sequence(language_mix):
    sequence = []
    for style, ratio in language_mix.items():
        count = max(1, int(round(ratio * 20)))
        sequence.extend([style] * count)
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
    family_id = plan["question_family"]
    family_config = templates["families"].get(family_id)
    if not family_config:
        raise SystemExit(f"{plan['plan_group_id']} has no template family {family_id}")
    style_order = ["vi", "en", "vi_no_diacritics", "mixed_vi_en", "short_chat", "technical_code"]
    candidates = family_candidates(family_config, style_order, plan)
    if not candidates:
        raise SystemExit(f"{plan['plan_group_id']} has no usable source template")
    style, template, _template_index = candidates[plan_index % len(candidates)]
    values = alias_renderer.render_values(plan, style, plan_index)
    rendered = render_template(template, values)
    return variants_for(rendered, style)[0]


def build_batch_item(plan, config, templates, alias_renderer, country_by_code, indicator_by_code, plan_index):
    parsed_query = plan["parsed_query"]
    requested_variants = plan["target_sample_count"]
    source_user_message = render_source_message(plan, templates, alias_renderer, plan_index)
    indicator_terms = []
    for code in parsed_query.get("indicators") or []:
        indicator_terms.extend(alias_terms(code, indicator_by_code))
    country_terms = []
    for code in parsed_query.get("countries") or []:
        country_terms.extend(alias_terms(code, country_by_code))
    must_preserve = {
        "indicators": parsed_query.get("indicators") or [],
        "indicator_surface_terms": unique(indicator_terms),
        "countries": parsed_query.get("countries") or [],
        "country_surface_terms": unique(country_terms),
        "country_groups": parsed_query.get("country_groups") or [],
        "start_year": parsed_query.get("start_year"),
        "end_year": parsed_query.get("end_year"),
        "relative_time": parsed_query.get("relative_time"),
        "event_time": parsed_query.get("event_time"),
        "ranking_order": parsed_query.get("ranking_order"),
        "limit": parsed_query.get("limit"),
        "threshold": parsed_query.get("threshold"),
        "aggregation": parsed_query.get("aggregation"),
        "chart_preference": parsed_query.get("chart_preference"),
    }
    return {
        "plan_group_id": plan["plan_group_id"],
        "intent": plan["intent"],
        "question_family": plan["question_family"],
        "source_user_message": source_user_message,
        "must_preserve": must_preserve,
        "requested_variants": requested_variants,
        "language_styles": language_styles_for_plan(config, plan_index, requested_variants),
    }


def render_copy_prompt(prompt_template, items):
    batch_json = json.dumps(items, ensure_ascii=False, indent=2)
    return prompt_template.replace("{{BATCH_JSON}}", batch_json)


def split_batches(items, config, prompt_template):
    max_prompt_chars = config["batching"]["max_prompt_chars"]
    max_items = config["batching"]["plans_per_batch"]
    batches = []
    current = []
    for item in items:
        candidate = current + [item]
        prompt = render_copy_prompt(prompt_template, candidate)
        if current and (len(candidate) > max_items or len(prompt) > max_prompt_chars):
            batches.append(current)
            current = [item]
        else:
            current = candidate
    if current:
        batches.append(current)
    return batches


def write_readme():
    text = """Manual paraphrase input format

1. Open each batch file in datasets/parser/paraphrase_batches/, for example:
   datasets/parser/paraphrase_batches/batch_0001.json
2. Copy the copy_prompt field value.
3. Paste it into DeepSeek/Qwen/ChatGPT or another manual AI platform.
4. Save the raw JSON array output to:
   datasets/parser/paraphrase_outputs/batch_0001.output.json
5. Do not add markdown or code fences.
6. If the platform returns markdown, remove ```json and ``` before saving.
7. Repeat for every batch you want to import.
8. Run:
   python services/query-agent/scripts/import_paraphrase_outputs.py
   python services/query-agent/scripts/check_phase7_paraphrase_samples.py
   python services/query-agent/scripts/check_text_quality.py
"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    README_PATH.write_text(text, encoding="utf-8")


def main():
    config = load_json(CONFIG_PATH)
    country_catalog = load_json(COUNTRY_CATALOG_PATH)
    indicator_catalog = load_json(INDICATOR_CATALOG_PATH)
    templates = load_json(QUESTION_TEMPLATES_PATH)
    prompt_template = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
    plans = read_jsonl(BASE_PLANS_PATH)

    target_bucket = config["target_generation_bucket"]
    target_plans = [plan for plan in plans if plan["generation_bucket"] == target_bucket]
    target_samples = sum(plan["target_sample_count"] for plan in target_plans)
    if target_samples != config["target_samples"]:
        print(f"WARNING config target_samples {config['target_samples']} != computed {target_samples}")

    country_by_code = {item["code"]: item for item in country_catalog["countries"]}
    indicator_by_code = {item["code"]: item for item in indicator_catalog["indicators"]}
    alias_renderer = AliasRenderer(country_catalog, indicator_catalog)

    items = [
        build_batch_item(plan, config, templates, alias_renderer, country_by_code, indicator_by_code, index)
        for index, plan in enumerate(target_plans)
    ]
    batch_items = split_batches(items, config, prompt_template)

    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    write_readme()

    manifest_batches = []
    for index, items_in_batch in enumerate(batch_items, start=1):
        batch_id = f"batch_{index:04d}"
        copy_prompt = render_copy_prompt(prompt_template, items_in_batch)
        batch_payload = {
            "batch_id": batch_id,
            "version": "v1",
            "prompt_template_path": "prompts/paraphrase_prompt_template.v1.txt",
            "items": items_in_batch,
            "copy_prompt": copy_prompt,
        }
        batch_path = BATCH_DIR / f"{batch_id}.json"
        with batch_path.open("w", encoding="utf-8", newline="\n") as file:
            json.dump(batch_payload, file, ensure_ascii=False, indent=2)
            file.write("\n")
        expected_variants = sum(item["requested_variants"] for item in items_in_batch)
        manifest_batches.append(
            {
                "batch_id": batch_id,
                "path": str(batch_path.relative_to(ROOT_DIR)).replace("\\", "/"),
                "item_count": len(items_in_batch),
                "expected_variants": expected_variants,
                "prompt_chars": len(copy_prompt),
            }
        )

    manifest = {
        "version": "v1",
        "target_generation_bucket": target_bucket,
        "total_batches": len(manifest_batches),
        "total_plan_groups": len(target_plans),
        "expected_variants": target_samples,
        "batches": manifest_batches,
    }
    with MANIFEST_PATH.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(manifest, file, ensure_ascii=False, indent=2)
        file.write("\n")

    print(f"total paraphrase target samples: {target_samples}")
    print(f"total paraphrase plan groups: {len(target_plans)}")
    print(f"total batches exported: {len(manifest_batches)}")
    print(f"expected variants: {target_samples}")
    print(f"batch manifest: {MANIFEST_PATH}")
    print(f"manual output folder: {OUTPUT_DIR}")
    print("READY_FOR_MANUAL_PARAPHRASE")
    print("Next steps:")
    print("1. Open datasets/parser/paraphrase_batches/batch_0001.json")
    print("2. Copy field copy_prompt")
    print("3. Paste into DeepSeek/Qwen")
    print("4. Save output to datasets/parser/paraphrase_outputs/batch_0001.output.json")
    print("5. Repeat for needed batches")
    print("6. Run python services/query-agent/scripts/import_paraphrase_outputs.py")
    print("7. Run python services/query-agent/scripts/check_phase7_paraphrase_samples.py")
    print("8. Run python services/query-agent/scripts/check_text_quality.py")


if __name__ == "__main__":
    main()
