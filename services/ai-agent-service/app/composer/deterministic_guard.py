from typing import Any


def append_result_warnings(answer: str, warnings: list[str]) -> str:
    cleaned = []
    semantic_seen: set[str] = set()
    answer_lowered = str(answer or "").lower()
    first_sentence = str(answer or "").split(".")[0].strip().lower()
    for warning in warnings or []:
        text = str(warning or "").strip()
        if not text:
            continue
        lowered = text.lower()
        if lowered.rstrip(".") and lowered.rstrip(".") in answer_lowered:
            continue
        if first_sentence and lowered.rstrip(".") in first_sentence:
            continue
        semantic_key = lowered
        if "không tìm thấy dữ liệu phù hợp" in lowered or "không có dữ liệu phù hợp" in lowered:
            semantic_key = "no_data"
        if "không phát hiện điểm bất thường vượt ngưỡng" in lowered:
            if "không phát hiện điểm bất thường vượt ngưỡng" in answer_lowered:
                continue
            semantic_key = "no_anomaly"
        if semantic_key in semantic_seen:
            continue
        semantic_seen.add(semantic_key)
        if text not in cleaned:
            cleaned.append(text)
    if not cleaned:
        return answer
    return f"{answer}\n\nLưu ý: " + " ".join(cleaned)


def safe_rows_by_country(rows: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for row in rows if isinstance(rows, list) else []:
        code = row.get("country_code")
        if not code:
            continue
        grouped.setdefault(str(code), []).append(row)
    return grouped
