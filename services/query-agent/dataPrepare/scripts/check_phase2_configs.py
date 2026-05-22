import json
from collections import Counter
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT_DIR / "configs"
TARGET_TOTAL_SAMPLES = 30000


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
    raise SystemExit(f"Phase 2 config check failed: {message}")


def require_string_array(value, field_name, family_id):
    if not isinstance(value, list):
        fail(f"{family_id}.{field_name} must be a list")
    invalid = [item for item in value if not isinstance(item, str)]
    if invalid:
        fail(f"{family_id}.{field_name} must contain only strings: {invalid}")


def validate_question_families(intents, enums, question_families):
    families = question_families.get("families")
    if not isinstance(families, list):
        fail("question_families.families must be a list")

    declared_total = question_families.get("total_question_families")
    if declared_total != len(families):
        fail(
            "question_families.total_question_families "
            f"({declared_total}) != len(families) ({len(families)})"
        )

    chart_preferences = enums.get("chart_preference", [])
    aggregations = enums.get("aggregation", [])
    intent_set = set(intents)
    family_ids = []
    family_counts = Counter()

    for index, family in enumerate(families):
        if not isinstance(family, dict):
            fail(f"family at index {index} must be an object")

        family_id = family.get("id")
        if not isinstance(family_id, str) or not family_id:
            fail(f"family at index {index} has invalid id")
        family_ids.append(family_id)

        intent = family.get("intent")
        if intent not in intent_set:
            fail(f"{family_id}.intent is not valid: {intent}")
        family_counts[intent] += 1

        required_slots = family.get("required_slots")
        optional_slots = family.get("optional_slots")
        require_string_array(required_slots, "required_slots", family_id)
        require_string_array(optional_slots, "optional_slots", family_id)

        chart_preference = family.get("default_chart_preference")
        if chart_preference not in chart_preferences:
            fail(
                f"{family_id}.default_chart_preference is not in "
                f"chart_preference enum: {chart_preference}"
            )

        aggregation = family.get("default_aggregation")
        if aggregation not in aggregations:
            fail(
                f"{family_id}.default_aggregation is not in aggregation enum: "
                f"{aggregation}"
            )

        needs_clarification = family.get("needs_clarification")
        if intent == "NEED_CLARIFICATION" and needs_clarification is not True:
            fail(f"{family_id} must have needs_clarification=true")
        if intent != "NEED_CLARIFICATION" and needs_clarification is True:
            fail(f"{family_id} uses needs_clarification=true outside NEED_CLARIFICATION")

        if intent == "OFF_TOPIC":
            forbidden_slots = {"indicators", "countries", "start_year", "end_year"}
            normalized_slots = {slot.split(">=", 1)[0] for slot in required_slots}
            forbidden_present = sorted(forbidden_slots & normalized_slots)
            if forbidden_present:
                fail(
                    f"{family_id} OFF_TOPIC required_slots contains forbidden slots: "
                    f"{forbidden_present}"
                )

    duplicate_ids = sorted(
        family_id for family_id, count in Counter(family_ids).items() if count > 1
    )
    if duplicate_ids:
        fail(f"duplicate question family ids: {duplicate_ids}")

    missing_family_intents = [intent for intent in intents if family_counts[intent] == 0]
    if missing_family_intents:
        fail(f"intents missing question families: {missing_family_intents}")

    return family_counts


def validate_dataset_distribution(intents, dataset_distribution):
    target_total = dataset_distribution.get("target_total_samples")
    if target_total != TARGET_TOTAL_SAMPLES:
        fail(
            "dataset_distribution.target_total_samples "
            f"({target_total}) != {TARGET_TOTAL_SAMPLES}"
        )

    splits = dataset_distribution.get("splits")
    if not isinstance(splits, dict):
        fail("dataset_distribution.splits must be an object")
    split_total = sum(splits.get(name, 0) for name in ("train", "validation", "test"))
    if split_total != target_total:
        fail(f"train + validation + test ({split_total}) != target_total_samples")

    intent_targets = dataset_distribution.get("intent_targets")
    if not isinstance(intent_targets, dict):
        fail("dataset_distribution.intent_targets must be an object")

    intent_set = set(intents)
    target_intents = set(intent_targets)
    missing_intents = sorted(intent_set - target_intents)
    extra_intents = sorted(target_intents - intent_set)
    if missing_intents:
        fail(f"dataset_distribution.intent_targets missing intents: {missing_intents}")
    if extra_intents:
        fail(f"dataset_distribution.intent_targets has unknown intents: {extra_intents}")

    invalid_targets = {
        intent: value
        for intent, value in intent_targets.items()
        if not isinstance(value, int) or value < 0
    }
    if invalid_targets:
        fail(f"intent target values must be non-negative integers: {invalid_targets}")

    target_sum = sum(intent_targets.values())
    if target_sum != target_total:
        fail(f"sum(intent_targets.values()) ({target_sum}) != target_total_samples")

    return intent_targets


def main():
    intents = load_json("configs/parser_intents.v1.json")
    enums = load_json("configs/parser_enums.v1.json")
    question_families = load_json("configs/question_families.v1.json")
    dataset_distribution = load_json("configs/dataset_distribution.v1.json")

    if not isinstance(intents, list) or not all(isinstance(item, str) for item in intents):
        fail("parser_intents.v1.json must be a list of strings")
    if not isinstance(enums, dict):
        fail("parser_enums.v1.json must be an object")

    family_counts = validate_question_families(intents, enums, question_families)
    intent_targets = validate_dataset_distribution(intents, dataset_distribution)

    print(f"total intents: {len(intents)}")
    print(f"total question families: {question_families['total_question_families']}")
    print("family count per intent:")
    for intent in intents:
        print(f"  {intent}: {family_counts[intent]}")
    print("target samples per intent:")
    for intent in intents:
        print(f"  {intent}: {intent_targets[intent]}")
    print("PASS")


if __name__ == "__main__":
    main()
