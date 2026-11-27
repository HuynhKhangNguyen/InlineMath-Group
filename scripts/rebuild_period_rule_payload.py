"""Recompute period-boundary-sensitive rows while reusing a prior payload."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from inline_math_grouping import convert_question_html, normalize_question_id  # noqa: E402
from audit_period_boundaries import with_legacy_boundaries  # noqa: E402


def normalize(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    return value.replace("\r\n", "\n").replace("\r", "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_payload", type=Path)
    parser.add_argument("output_payload", type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--dataset-title", required=True)
    parser.add_argument(
        "--only-rows",
        required=True,
        help="Comma-separated Excel rows identified by the semantic-period audit.",
    )
    args = parser.parse_args()

    base = json.loads(args.base_payload.read_text(encoding="utf-8"))
    source_values = base["sourceValues"]
    headers = source_values[0]
    columns = {str(name).lower(): index for index, name in enumerate(headers) if name}
    html_column = columns["questionhtml"]
    qid_column = columns.get("questionid")
    base_rows = {int(row["excelRow"]): row for row in base["rows"]}
    target_rows = {int(value) for value in args.only_rows.split(",") if value.strip()}

    rows = []
    summary = Counter(base.get("summary", {}))
    type_counts: Counter[str] = Counter(base.get("typeCounts", {}))
    context_type_counts: Counter[str] = Counter(base.get("contextTypeCounts", {}))
    errors = list(base.get("errors", []))
    changed_rows = []
    changed_qids = []

    for excel_row, values in enumerate(source_values[1:], start=2):
        question_id = normalize_question_id(values[qid_column]) if qid_column is not None else ""
        source_html = values[html_column] or ""
        previous = base_rows[excel_row]
        if excel_row not in target_rows:
            rows.append(previous)
            continue

        try:
            old_result = with_legacy_boundaries(
                lambda: convert_question_html(source_html, question_id)
            )
            result = convert_question_html(source_html, question_id)
            current_row = {
                "excelRow": excel_row,
                "questionId": result.get("questionId", question_id),
                "convertedQuestionHtml": result["convertedQuestionHtml"],
                "convertedQuestionXml": result["convertedQuestionXml"],
                "Type": result["type"],
                "ContextType": result["contextType"],
                "conversionNote": f"{args.version}: {result['conversionNote']}",
            }
        except Exception as error:  # pragma: no cover - defensive batch guard
            errors.append({"row": excel_row, "questionId": question_id, "error": str(error)})
            old_result = {
                "sourceInlineMath": 0,
                "processableInlineMath": 0,
                "processedGroups": 0,
                "protectedInlineMath": 0,
                "nestedExcluded": 0,
                "outsideLayout": 0,
            }
            result = {
                "sourceInlineMath": 0,
                "processableInlineMath": 0,
                "processedGroups": 0,
                "protectedInlineMath": 0,
                "nestedExcluded": 0,
                "outsideLayout": 0,
            }
            current_row = {
                "excelRow": excel_row,
                "questionId": question_id,
                "convertedQuestionHtml": source_html,
                "convertedQuestionXml": "",
                "Type": "Manual Review",
                "ContextType": "Manual Review",
                "conversionNote": f"{args.version} parse error: {error}",
            }

        # Only the audited rows contribute a summary delta. All other row
        # metrics and classifications stay exactly as recorded in the base
        # payload, even if an older payload used a different non-period rule.
        for key in (
            "sourceInlineMath",
            "processableInlineMath",
            "processedGroups",
            "protectedInlineMath",
            "nestedExcluded",
            "outsideLayout",
        ):
            summary[key] += result.get(key, 0) - old_result.get(key, 0)
        if current_row["Type"] != previous.get("Type"):
            type_counts[previous.get("Type", "")] -= 1
            type_counts[current_row["Type"]] += 1
        if current_row["ContextType"] != previous.get("ContextType"):
            context_type_counts[previous.get("ContextType", "")] -= 1
            context_type_counts[current_row["ContextType"]] += 1

        comparable = ("convertedQuestionHtml", "convertedQuestionXml", "Type", "ContextType")
        changed = any(normalize(current_row[key]) != normalize(previous.get(key)) for key in comparable)
        if changed:
            changed_rows.append(excel_row)
            changed_qids.append(current_row["questionId"])
            rows.append(current_row)
        else:
            # Preserve the prior row verbatim when the semantic-period rule did
            # not change its result. This keeps targeted output diffs reviewable.
            rows.append(previous)

    payload = {
        "version": args.version,
        "datasetTitle": args.dataset_title,
        "sourceWorkbook": base.get("sourceWorkbook", ""),
        "sourceSheet": base.get("sourceSheet", "Data"),
        "sourceValues": source_values,
        "summary": dict(summary),
        "typeCounts": dict(type_counts),
        "contextTypeCounts": dict(context_type_counts),
        "errors": errors,
        "rows": rows,
        "incremental": {
            "baseVersion": base.get("version", ""),
            "changedQuestionCount": len(changed_rows),
            "reusedQuestionCount": len(rows) - len(changed_rows),
            "changedRows": changed_rows,
            "changedQuestionIds": changed_qids,
            "auditedRows": sorted(target_rows),
            "rule": "semantic period boundaries; only audited rows rewritten",
        },
    }
    args.output_payload.parent.mkdir(parents=True, exist_ok=True)
    args.output_payload.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"version": args.version, "changedRows": changed_rows, "summary": dict(summary), "contextTypeCounts": dict(context_type_counts)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
