"""Build v1 InlineMath conversion data for an input workbook."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import openpyxl

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from inline_math_grouping import convert_question_html


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--sheet", default="Data")
    args = parser.parse_args()

    workbook = openpyxl.load_workbook(args.input, read_only=True, data_only=True)
    worksheet = workbook[args.sheet]
    headers = [cell.value for cell in next(worksheet.iter_rows(min_row=1, max_row=1))]
    columns = {name: index for index, name in enumerate(headers) if name}
    if "questionhtml" not in columns:
        raise ValueError("Input must contain a questionhtml column")

    rows = []
    summary = Counter()
    type_counts = Counter()
    errors = []
    for excel_row, values in enumerate(worksheet.iter_rows(min_row=2, values_only=True), start=2):
        summary["sourceRows"] += 1
        question_id = values[columns["questionid"]] if "questionid" in columns else ""
        source_html = values[columns["questionhtml"]] or ""
        try:
            result = convert_question_html(source_html, question_id)
        except Exception as error:
            summary["parseErrors"] += 1
            errors.append({"row": excel_row, "questionId": str(question_id or ""), "error": str(error)})
            result = {
                "convertedQuestionHtml": source_html,
                "convertedQuestionXml": "",
                "type": "Manual Review",
                "conversionNote": f"v1 parse error: {error}",
                "sourceInlineMath": 0,
                "processableInlineMath": 0,
                "processedGroups": 0,
                "protectedInlineMath": 0,
                "nestedExcluded": 0,
                "labelIds": [],
            }

        type_counts[result["type"]] += 1
        for key in (
            "sourceInlineMath",
            "processableInlineMath",
            "processedGroups",
            "protectedInlineMath",
            "nestedExcluded",
        ):
            summary[key] += result[key]
        rows.append(
            {
                "excelRow": excel_row,
                "convertedQuestionHtml": result["convertedQuestionHtml"],
                "convertedQuestionXml": result["convertedQuestionXml"],
                "Type": result["type"],
                "conversionNote": result["conversionNote"],
            }
        )

    payload = {
        "version": "v1",
        "sourceWorkbook": str(args.input.resolve()),
        "sourceSheet": args.sheet,
        "summary": dict(summary),
        "typeCounts": dict(type_counts),
        "errors": errors,
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"summary": payload["summary"], "typeCounts": payload["typeCounts"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
