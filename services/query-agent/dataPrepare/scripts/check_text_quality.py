import re
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
QUERY_AGENT_DIR = SCRIPT_DIR.parent
REPO_ROOT = QUERY_AGENT_DIR.parents[1]

SCAN_FILES = [
    QUERY_AGENT_DIR / "configs/question_templates.v1.json",
    QUERY_AGENT_DIR / "configs/indicator_catalog.v1.json",
    QUERY_AGENT_DIR / "configs/country_catalog.v1.json",
    QUERY_AGENT_DIR / "configs/alias_generation_rules.v1.json",
    REPO_ROOT / "services/ai-agent-service/app/catalog/indicator_catalog.py",
    REPO_ROOT / "services/ai-agent-service/app/resolver/country_resolver.py",
    REPO_ROOT / "services/ai-agent-service/app/composer/template_composer.py",
    REPO_ROOT / "services/ai-agent-service/app/composer/gemini_composer.py",
    REPO_ROOT / "server/src/indicators/indicators.service.ts",
    QUERY_AGENT_DIR / "datasets/parser/parser_hard_cases.v1.jsonl",
    QUERY_AGENT_DIR / "datasets/parser/parser_offtopic_unsupported.v1.jsonl",
    QUERY_AGENT_DIR / "datasets/parser/parser_full.v1.jsonl",
    QUERY_AGENT_DIR / "datasets/parser/final/parser_train.v1.jsonl",
    QUERY_AGENT_DIR / "datasets/parser/final/parser_validation.v1.jsonl",
    QUERY_AGENT_DIR / "datasets/parser/final/parser_test.v1.jsonl",
]

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
SYNTHETIC_ARTIFACT_REGEXES = [
    re.compile(r"#\d+"),
    re.compile(r"\b(request|case|sample|id)\s*#?\d+\b", re.IGNORECASE),
    re.compile(r"\b(yeu cau|yêu cầu|mau|mẫu)\s*#?\d+\b", re.IGNORECASE),
]


def has_mojibake(text):
    lowered = text.lower()
    if any(literal.lower() in lowered for literal in MOJIBAKE_LITERALS):
        return True
    if any(marker in text for marker in MOJIBAKE_MARKERS):
        return True
    return any(pattern.search(text) for pattern in MOJIBAKE_REGEXES)


def has_synthetic_artifact(text):
    return any(pattern.search(text) for pattern in SYNTHETIC_ARTIFACT_REGEXES)


def printable(text):
    return text.encode("ascii", errors="backslashreplace").decode("ascii")


def main():
    findings = []
    artifact_findings = []
    for path in SCAN_FILES:
        if not path.exists():
            findings.append((path, 0, "missing file"))
            continue
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if has_mojibake(line):
                findings.append((path, line_number, line.strip()))
            if has_synthetic_artifact(line):
                artifact_findings.append((path, line_number, line.strip()))

    print(f"scanned files: {len(SCAN_FILES)}")
    print(f"mojibake findings count: {len(findings)}")
    print(f"synthetic artifact findings count: {len(artifact_findings)}")
    if findings:
        print("mojibake examples:")
        for path, line_number, line in findings[:30]:
            relative = path.relative_to(REPO_ROOT)
            print(f"  {relative}:{line_number}: {printable(line)}")
        raise SystemExit(f"Text quality check failed: {len(findings)} mojibake findings")
    if artifact_findings:
        print("synthetic artifact examples:")
        for path, line_number, line in artifact_findings[:30]:
            relative = path.relative_to(REPO_ROOT)
            print(f"  {relative}:{line_number}: {printable(line)}")
        raise SystemExit(f"Text quality check failed: {len(artifact_findings)} synthetic artifact findings")

    print("PASS")


if __name__ == "__main__":
    main()
