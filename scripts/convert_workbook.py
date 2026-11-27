"""Build versioned InlineMath conversion data for an input workbook."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from workbook_contract import worksheet_values

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from inline_math_grouping import convert_question_html


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--sheet", default="Data")
    args = parser.parse_args()

    header_row, *source_rows = worksheet_values(args.input, args.sheet, data_only=True)
    headers = list(header_row)
    columns = {name: index for index, name in enumerate(headers) if name}
    if "questionhtml" not in columns:
        raise ValueError("Input must contain a questionhtml column")

    rows = []
    source_values = [headers]
    summary = Counter()
    type_counts = Counter()
    context_type_counts = Counter()
    error_type_counts = Counter()
    errors = []
    for excel_row, values in enumerate(source_rows, start=2):
        source_values.append(list(values))
        summary["sourceRows"] += 1
        question_id = values[columns["questionid"]] if "questionid" in columns else ""
        source_html = values[columns["questionhtml"]] or ""
        try:
            result = convert_question_html(source_html, question_id)
            result["conversionNote"] = f"{args.version}: {result['conversionNote']}"
        except Exception as error:
            summary["parseErrors"] += 1
            errors.append({"row": excel_row, "questionId": str(question_id or ""), "error": str(error)})
            result = {
                "convertedQuestionHtml": source_html,
                "convertedQuestionXml": "",
                "type": "Manual Review",
                "errorType": "",
                "contextType": "Manual Review",
                "conversionNote": f"{args.version} parse error: {error}",
                "sourceInlineMath": 0,
                "processableInlineMath": 0,
                "processedInlineMath": 0,
                "groupingErrorInlineMath": 0,
                "groupingErrorGroups": 0,
                "processedGroups": 0,
                "protectedInlineMath": 0,
                "nestedExcluded": 0,
                "outsideLayout": 0,
                "labelIds": [],
            }

        type_counts[result["type"]] += 1
        context_type_counts[result["contextType"]] += 1
        if result.get("errorType"):
            error_type_counts[result["errorType"]] += 1
        for key in (
            "sourceInlineMath",
            "numberlineSkippedInlineMath",
            "processableInlineMath",
            "processedInlineMath",
            "groupingErrorInlineMath",
            "groupingErrorGroups",
            "processedGroups",
            "protectedInlineMath",
            "nestedExcluded",
            "outsideLayout",
        ):
            summary[key] += result.get(key, 0)
        rows.append(
            {
                "excelRow": excel_row,
                "questionId": result.get("questionId", str(question_id or "")),
                "convertedQuestionHtml": result["convertedQuestionHtml"],
                "convertedQuestionXml": result["convertedQuestionXml"],
                "Type": result["type"],
                "ErrorType": result.get("errorType", ""),
                "ContextType": result["contextType"],
                "conversionNote": result["conversionNote"],
                "groupingErrorInlineMath": result.get("groupingErrorInlineMath", 0),
                "numberlineSkippedInlineMath": result.get("numberlineSkippedInlineMath", 0),
            }
        )

    payload = {
        "version": args.version,
        "sourceWorkbook": str(args.input.resolve()),
        "sourceSheet": args.sheet,
        "sourceValues": source_values,
        "summary": dict(summary),
        "typeCounts": dict(type_counts),
        "errorTypeCounts": dict(error_type_counts),
        "contextTypeCounts": dict(context_type_counts),
        "errors": errors,
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(
        json.dumps(
            {
                "summary": payload["summary"],
                "typeCounts": payload["typeCounts"],
                "errorTypeCounts": payload["errorTypeCounts"],
                "contextTypeCounts": payload["contextTypeCounts"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
