"""Audit semantic period boundaries and compare the legacy character rule."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import openpyxl

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import inline_math_grouping as grouping  # noqa: E402


DECIMAL_RE = re.compile(r"(?<![A-Za-z0-9])\d+\.\d+(?![A-Za-z0-9])")
MEASUREMENT_ABBREVIATION_RE = re.compile(
    r"\b(?:in|ft|yd|oz|lb|cm|mm|m|km|g|kg|mg|ml|l|sec|min|hr|hrs|sq|cu)\.(?=\s|$)",
    re.IGNORECASE,
)
ABBREVIATION_RE = re.compile(
    r"\b(?:Mr|Mrs|Ms|Dr|Prof|Sr|Jr|St|Rev|No|Fig|Eq|Approx|Misc|Dept|Vol|Vs|Etc|e\.g|i\.e)\.(?=\s|$)",
    re.IGNORECASE,
)


def normalize(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    return value.replace("\r\n", "\n").replace("\r", "\n")


def legacy_semantic_split_offset(text_between: str) -> int | None:
    if re.search(r"\bOR\b", text_between, flags=re.IGNORECASE):
        return re.search(r"\bOR\b", text_between, flags=re.IGNORECASE).start()
    if re.fullmatch(r"\s*[.!?]\s*", text_between or ""):
        return None
    punctuation = list(re.finditer(r"[.!?]", text_between))
    if punctuation:
        start = punctuation[0].end()
        while start < len(text_between) and text_between[start].isspace():
            start += 1
        return start
    stripped_start = len(text_between) - len(text_between.lstrip())
    stripped = text_between[stripped_start:]
    if stripped and not stripped.startswith(("+", "-", "−", "×", "÷", "*", "/", "=", ",", ";", "and ")):
        if re.search(r"\d", stripped) and re.search(r"[+×÷−*/=]", stripped):
            return stripped_start
        if stripped.startswith("(") and re.search(r"[+×÷−*/=]", stripped):
            return stripped_start
    return None


def legacy_question_sentence_start(raw_text: str) -> int:
    last_question = raw_text.rfind("?")
    if last_question < 0:
        return 0
    abbreviations = {"mr", "mrs", "ms", "dr", "st", "jr", "sr", "vs"}
    breaks = []
    for match in re.finditer(r"[.!?]", raw_text[:last_question]):
        index = match.start()
        if match.group() == ".":
            before = raw_text[:index]
            word_match = re.search(r"([A-Za-z]+)$", before)
            word = word_match.group(1).lower() if word_match else ""
            if word in abbreviations:
                continue
            if index > 0 and index + 1 < len(raw_text) and raw_text[index - 1].isdigit() and raw_text[index + 1].isdigit():
                continue
        breaks.append(index)
    previous_end = max(breaks, default=-1)
    start = previous_end + 1
    while start < len(raw_text) and raw_text[start].isspace():
        start += 1
    return start


def legacy_local_sentence_start(raw_text: str) -> int:
    stripped_end = len(raw_text.rstrip())
    last_end = max(raw_text.rfind("."), raw_text.rfind("?"), raw_text.rfind("!"))
    if last_end >= 0 and last_end < stripped_end and not raw_text[last_end + 1 :].strip():
        previous_end = max(
            raw_text.rfind(".", 0, last_end),
            raw_text.rfind("?", 0, last_end),
            raw_text.rfind("!", 0, last_end),
        )
    else:
        previous_end = last_end
    start = previous_end + 1
    while start < len(raw_text) and raw_text[start].isspace():
        start += 1
    return start


def legacy_is_applicable_preceding_context(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return False
    if "?" in normalized:
        return True
    instruction_words = {
        "calculate", "choose", "compare", "complete", "determine", "divide", "enter",
        "estimate", "fill", "find", "identify", "measure", "name", "order", "regroup",
        "round", "select", "solve", "use", "write",
    }
    question_words = {"how", "what", "when", "where", "which", "who", "why"}
    sentences = re.split(r"(?<=[.!?])\s+", normalized)
    for sentence in sentences:
        words = re.findall(r"[A-Za-z]+", sentence.lower())
        if words and (words[0] in instruction_words or words[0] in question_words):
            return True
    words = re.findall(r"[A-Za-z]+", normalized.lower())
    if normalized.endswith(":") and words:
        return True
    return bool(re.search(r"\d", normalized) and re.search(r"[+×÷−*/=]", normalized))


def with_legacy_boundaries(callback):
    old = (
        grouping._semantic_split_offset,
        grouping._question_sentence_start,
        grouping._local_sentence_start,
        grouping._is_applicable_preceding_context,
    )
    grouping._semantic_split_offset = legacy_semantic_split_offset
    grouping._question_sentence_start = legacy_question_sentence_start
    grouping._local_sentence_start = legacy_local_sentence_start
    grouping._is_applicable_preceding_context = legacy_is_applicable_preceding_context
    try:
        return callback()
    finally:
        (
            grouping._semantic_split_offset,
            grouping._question_sentence_start,
            grouping._local_sentence_start,
            grouping._is_applicable_preceding_context,
        ) = old


def visible_text(source_html: str) -> str:
    root = grouping.parse_html_fragment(source_html or "")
    return grouping._normalize_text("".join(root.itertext()))


def pattern_flags(text: str) -> dict[str, int]:
    return {
        "decimalPeriods": len(DECIMAL_RE.findall(text)),
        "measurementAbbreviationPeriods": len(MEASUREMENT_ABBREVIATION_RE.findall(text)),
        "abbreviationPeriods": len(ABBREVIATION_RE.findall(text)),
        "ignoredSemanticPeriods": sum(
            1
            for index, char in enumerate(text)
            if char == "." and not grouping._period_is_sentence_boundary(text, index)
        ),
    }


def audit_workbook(path: Path) -> dict[str, Any]:
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    worksheet = workbook["Data"]
    headers = [cell.value for cell in next(worksheet.iter_rows(min_row=1, max_row=1))]
    columns = {str(name).lower(): index for index, name in enumerate(headers) if name}
    html_column = columns["questionhtml"]
    qid_column = columns.get("questionid")
    rows = []
    changed_rows = []
    totals = Counter()
    source_row_count = 0
    for excel_row, values in enumerate(worksheet.iter_rows(min_row=2, values_only=True), start=2):
        source_row_count += 1
        source_html = values[html_column] or ""
        text = visible_text(source_html)
        flags = pattern_flags(text)
        new_result = grouping.convert_question_html(source_html, values[qid_column] if qid_column is not None else "")
        old_result = with_legacy_boundaries(
            lambda: grouping.convert_question_html(source_html, values[qid_column] if qid_column is not None else "")
        )
        changed = any(
            normalize(new_result.get(key)) != normalize(old_result.get(key))
            for key in ("convertedQuestionHtml", "type", "contextType", "processableInlineMath", "processedGroups")
        )
        for key, value in flags.items():
            totals[key] += value
        if any(flags.values()):
            rows.append(
                {
                    "excelRow": excel_row,
                    "questionId": grouping.normalize_question_id(values[qid_column]) if qid_column is not None else "",
                    "flags": flags,
                    "changedAfterSemanticRule": changed,
                    "old": {key: old_result.get(key) for key in ("processedGroups", "contextType", "processableInlineMath")},
                    "new": {key: new_result.get(key) for key in ("processedGroups", "contextType", "processableInlineMath")},
                    "textExcerpt": text[:500],
                }
            )
        if changed:
            changed_rows.append(
                {
                    "excelRow": excel_row,
                    "questionId": grouping.normalize_question_id(values[qid_column]) if qid_column is not None else "",
                    "flags": flags,
                    "old": {key: old_result.get(key) for key in ("processedGroups", "contextType", "processableInlineMath")},
                    "new": {key: new_result.get(key) for key in ("processedGroups", "contextType", "processableInlineMath")},
                }
            )
    return {
        "file": str(path.resolve()),
        "sourceRows": source_row_count,
        "patternTotals": dict(totals),
        "patternRows": rows,
        "changedRows": changed_rows,
        "changedRowCount": len(changed_rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    reports = [audit_workbook(path) for path in args.inputs]
    report = {
        "rule": "semantic period boundaries",
        "criteria": {
            "decimal": "period between digits is not a sentence boundary",
            "abbreviation": "abbreviation period is retained when the semantic unit continues",
            "sentence": "an abbreviation period may be a boundary when a new sentence follows",
            "signals": "token + surrounding characters + following token + semantic/DOM context",
        },
        "files": reports,
        "totals": {
            "sourceRows": sum(item["sourceRows"] for item in reports),
            "patternRows": sum(len(item["patternRows"]) for item in reports),
            "changedRows": sum(item["changedRowCount"] for item in reports),
        },
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"totals": report["totals"], "files": [{"file": r["file"], "sourceRows": r["sourceRows"], "patternRows": len(r["patternRows"]), "changedRows": r["changedRowCount"]} for r in reports]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
