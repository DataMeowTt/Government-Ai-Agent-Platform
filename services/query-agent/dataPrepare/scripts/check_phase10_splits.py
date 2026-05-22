import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT_DIR / "configs"
DATASET_DIR = ROOT_DIR / "datasets" / "parser"
FINAL_DIR = DATASET_DIR / "final"

DISTRIBUTION_PATH = CONFIG_DIR / "dataset_distribution.v1.json"
INTENTS_PATH = CONFIG_DIR / "parser_intents.v1.json"
FAMILIES_PATH = CONFIG_DIR / "question_families.v1.json"
COUNTRY_CATALOG_PATH = CONFIG_DIR / "country_catalog.v1.json"
INDICATOR_CATALOG_PATH = CONFIG_DIR / "indicator_catalog.v1.json"

FULL_PATH = DATASET_DIR / "parser_full.v1.jsonl"
TRAIN_PATH = FINAL_DIR / "parser_train.v1.jsonl"
VALIDATION_PATH = FINAL_DIR / "parser_validation.v1.jsonl"
TEST_PATH = FINAL_DIR / "parser_test.v1.jsonl"
SPLIT_REPORT_PATH = FINAL_DIR / "parser_split_report.v1.json"
FINAL_REPORT_PATH = FINAL_DIR / "parser_final_report.v1.json"

SPLIT_FILES = {
    "train": TRAIN_PATH,
    "validation": VALIDATION_PATH,
    "test": TEST_PATH,
}
GENERATION_SOURCES = {
    "deterministic_template",
    "llm_paraphrase",
    "hard_cases",
    "off_topic_unsupported",
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
MOJIBAKE_MARKERS = ["Ãƒ", "Ã‚Â²", "Ã„", "Ã¡Â»", "Ã¡Âº", "Ã†", "ï¿½"]
MOJIBAKE_REGEXES = [
    re.compile(r"[A-Za-zÀ-ỹ]\?[A-Za-zÀ-ỹ]"),
    re.compile(r"\?\?"),
    re.compile(r"(?:^|\s)\?[A-Za-zÀ-ỹ]"),
    re.compile(r"\b(?:d|ch|k|n|l|t|h|qu)\?", re.IGNORECASE),
    re.compile(r"tr\?\?", re.IGNORECASE),
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
    raise SystemExit(f"Phase 10 split check failed: {message}")


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


def count_by(rows, field):
    return dict(sorted(Counter(row[field] for row in rows).items()))


def compare_dict(label, expected, actual):
    if expected != actual:
        fail(f"{label} mismatch", [f"expected={expected}", f"actual={actual}"])


def validate_chatml(sample, errors):
    messages = sample.get("messages")
    if not isinstance(messages, list) or len(messages) != 3:
        errors["chatml_errors"] += 1
        return
    roles = [message.get("role") for message in messages if isinstance(message, dict)]
    if roles != ["system", "user", "assistant"]:
        errors["chatml_errors"] += 1
        return
    if messages[1].get("content") != sample.get("user_message"):
        errors["chatml_errors"] += 1
    try:
        assistant_content = json.loads(messages[2].get("content"))
    except (TypeError, json.JSONDecodeError):
        errors["chatml_errors"] += 1
        return
    if assistant_content != sample.get("assistant_json"):
        errors["chatml_errors"] += 1


def validate_user_message(sample, errors):
    text = sample.get("user_message")
    if not isinstance(text, str) or not text.strip():
        errors["empty_messages"] += 1
        return
    if len(text) > 500:
        errors["too_long_messages"] += 1
    if PLACEHOLDER_RE.search(text):
        errors["placeholder_findings"] += 1
    if has_mojibake(text):
        errors["mojibake_findings"] += 1
    if has_artifact(text):
        errors["synthetic_artifact_findings"] += 1


def validate_integrity(split_rows, full_by_id, split):
    problems = []
    for sample in split_rows:
        sample_id = sample.get("sample_id")
        if sample.get("split") != split:
            problems.append(f"{sample_id}: split field={sample.get('split')} file={split}")
            continue
        if sample_id not in full_by_id:
            problems.append(f"{sample_id}: not found in parser_full")
            continue
        splitless = dict(sample)
        splitless.pop("split", None)
        if splitless != full_by_id[sample_id]:
            problems.append(f"{sample_id}: split sample differs from parser_full")
    if problems:
        fail("sample integrity mismatch", problems)


def validate_uniqueness(full_rows, rows_by_split):
    all_rows = [row for rows in rows_by_split.values() for row in rows]
    full_ids = {row["sample_id"] for row in full_rows}
    split_ids = [row["sample_id"] for row in all_rows]
    split_id_set = set(split_ids)
    if len(split_ids) != len(split_id_set):
        duplicates = [sample_id for sample_id, count in Counter(split_ids).items() if count > 1]
        fail("duplicate sample_id across splits", duplicates)
    if split_id_set != full_ids:
        missing = sorted(full_ids - split_id_set)
        extra = sorted(split_id_set - full_ids)
        fail("split sample_id union does not match parser_full", [f"missing={missing[:10]}", f"extra={extra[:10]}"])

    for field in ("source_sample_id", "user_message"):
        values = [row.get(field) for row in all_rows]
        duplicates = [value for value, count in Counter(values).items() if count > 1]
        if duplicates:
            fail(f"duplicate {field} across splits", duplicates)


def validate_leakage(rows_by_split):
    plan_group_splits = defaultdict(set)
    for split, rows in rows_by_split.items():
        for row in rows:
            plan_group_splits[row["plan_group_id"]].add(split)
    leaks = [
        f"{plan_group_id}: {sorted(splits)}"
        for plan_group_id, splits in plan_group_splits.items()
        if len(splits) > 1
    ]
    if leaks:
        fail("plan_group_id leakage across splits", leaks)
    return 0


def validate_quality(rows_by_split):
    errors = Counter()
    for rows in rows_by_split.values():
        for sample in rows:
            validate_chatml(sample, errors)
            validate_user_message(sample, errors)
    hard_errors = sum(errors.values())
    if hard_errors:
        fail("quality errors in split files", [f"{key}={value}" for key, value in sorted(errors.items())])
    return errors


def validate_coverage(rows_by_split, intents, families, warnings):
    family_target = len(families)
    min_heldout_families = math.ceil(family_target * 0.80)
    coverage = {}
    for split, rows in rows_by_split.items():
        split_intents = {row["intent"] for row in rows}
        split_families = {row["question_family"] for row in rows}
        split_sources = {row["generation_source"] for row in rows}
        split_styles = {row["language_style"] for row in rows}
        coverage[split] = {
            "intents": len(split_intents),
            "question_families": len(split_families),
            "generation_sources": len(split_sources),
            "language_styles": len(split_styles),
        }
        if split == "train":
            missing_intents = set(intents) - split_intents
            missing_families = set(families) - split_families
            if missing_intents:
                fail("train split missing intents", sorted(missing_intents))
            if missing_families:
                fail("train split missing question families", sorted(missing_families))
        elif len(split_families) < min_heldout_families:
            fail(f"{split} covers only {len(split_families)} question families, expected at least {min_heldout_families}")
        if split_sources != GENERATION_SOURCES:
            fail(f"{split} missing generation sources", sorted(GENERATION_SOURCES - split_sources))
        if len(split_styles) < 2:
            fail(f"{split} has fewer than two language styles")
    return coverage


def validate_distribution(full_rows, rows_by_split, warnings):
    full_total = len(full_rows)
    full_intents = Counter(row["intent"] for row in full_rows)
    full_sources = Counter(row["generation_source"] for row in full_rows)
    for split in ("validation", "test"):
        rows = rows_by_split[split]
        split_total = len(rows)
        split_intents = Counter(row["intent"] for row in rows)
        split_sources = Counter(row["generation_source"] for row in rows)
        for intent, full_count in full_intents.items():
            diff = abs(split_intents[intent] / split_total - full_count / full_total)
            if diff > 0.05:
                warnings.append(f"{split} intent proportion drift >5pp for {intent}: {diff:.3f}")
        for source, full_count in full_sources.items():
            diff = abs(split_sources[source] / split_total - full_count / full_total)
            if diff > 0.08:
                warnings.append(f"{split} generation_source drift >8pp for {source}: {diff:.3f}")


def validate_reports(rows_by_split, full_rows, split_report, final_report):
    actual_sizes = {split: len(rows) for split, rows in rows_by_split.items()}
    compare_dict("split_report actual_sizes", actual_sizes, split_report.get("actual_sizes"))
    if split_report.get("leakage_check", {}).get("plan_group_id_overlap_between_splits") != 0:
        fail("split_report leakage overlap is not 0")
    if final_report.get("total_samples") != len(full_rows):
        fail("parser_final_report total_samples mismatch")
    compare_dict("parser_final_report splits", actual_sizes, final_report.get("splits"))
    quality = final_report.get("quality", {})
    nonzero_quality = {key: value for key, value in quality.items() if value != 0}
    if nonzero_quality:
        fail("parser_final_report quality fields must be 0", [str(nonzero_quality)])


def main():
    distribution = load_json(DISTRIBUTION_PATH)
    intents = load_json(INTENTS_PATH)
    families_payload = load_json(FAMILIES_PATH)
    load_json(COUNTRY_CATALOG_PATH)
    load_json(INDICATOR_CATALOG_PATH)
    split_report = load_json(SPLIT_REPORT_PATH)
    final_report = load_json(FINAL_REPORT_PATH)

    target_sizes = distribution["splits"]
    family_ids = [family["id"] for family in families_payload["families"]]
    full_rows = read_jsonl(FULL_PATH, "parser_full")
    full_by_id = {row["sample_id"]: row for row in full_rows}
    if len(full_by_id) != len(full_rows):
        fail("parser_full has duplicate sample_id")

    rows_by_split = {
        split: read_jsonl(path, split)
        for split, path in SPLIT_FILES.items()
    }

    for split, rows in rows_by_split.items():
        if len(rows) != target_sizes[split]:
            fail(f"{split} size {len(rows)} != target {target_sizes[split]}")
        validate_integrity(rows, full_by_id, split)

    total = sum(len(rows) for rows in rows_by_split.values())
    if total != len(full_rows):
        fail(f"split total {total} != full total {len(full_rows)}")

    validate_uniqueness(full_rows, rows_by_split)
    leakage_overlap = validate_leakage(rows_by_split)
    quality_errors = validate_quality(rows_by_split)

    warnings = []
    coverage = validate_coverage(rows_by_split, intents, family_ids, warnings)
    validate_distribution(full_rows, rows_by_split, warnings)
    validate_reports(rows_by_split, full_rows, split_report, final_report)

    print(f"split sizes: {{'train': {len(rows_by_split['train'])}, 'validation': {len(rows_by_split['validation'])}, 'test': {len(rows_by_split['test'])}}}")
    print(
        "plan group counts by split: "
        + str({split: len({row["plan_group_id"] for row in rows}) for split, rows in rows_by_split.items()})
    )
    print(f"leakage overlap: {leakage_overlap}")
    print(f"coverage by split: {coverage}")
    print(
        "generation source distribution by split: "
        + str({split: count_by(rows, "generation_source") for split, rows in rows_by_split.items()})
    )
    print(f"warning count: {len(warnings)}")
    if warnings:
        print("warnings:")
        for warning in warnings[:30]:
            print(f"  {warning}")
    print("PASS")


if __name__ == "__main__":
    main()
