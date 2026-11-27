"""Extract deterministic InlineMath review data from a CLA workbook."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import openpyxl

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from inline_math_grouping import flatten_group_details, group_inline_math, groups_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--sheet", default="Data")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    workbook = openpyxl.load_workbook(args.input, read_only=True, data_only=True)
    worksheet = workbook[args.sheet]
    headers = [cell.value for cell in next(worksheet.iter_rows(min_row=1, max_row=1))]
    column = {name: index for index, name in enumerate(headers)}

    html_column = "questionhtml" if "questionhtml" in column else None
    if html_column is None:
        raise ValueError("Input must contain a questionhtml column")

    output_rows = []
    detail_rows = []
    summary = {
        "sourceRows": 0,
        "questionsWithTopLevelInlineMath": 0,
        "questionsWithoutTopLevelInlineMath": 0,
        "groups": 0,
        "topLevelInlineMath": 0,
        "nestedInlineMathExcluded": 0,
        "parseErrors": 0,
    }

    for source_row, values in enumerate(
        worksheet.iter_rows(min_row=2, values_only=True), start=2
    ):
        summary["sourceRows"] += 1
        question_id = values[column.get("questionid", -1)] if "questionid" in column else ""
        resource_code = (
            values[column.get("resourcecode", -1)] if "resourcecode" in column else ""
        )
        question_number = (
            values[column.get("questionnumber", -1)] if "questionnumber" in column else ""
        )
        try:
            result = group_inline_math(values[column[html_column]] or "", question_id)
        except Exception as error:
            summary["parseErrors"] += 1
            output_rows.append(
                {
                    "sourceRow": source_row,
                    "questionId": str(question_id or ""),
                    "resourceCode": str(resource_code or ""),
                    "questionNumber": question_number,
                    "groupCount": 0,
                    "itemCount": 0,
                    "status": f"parse error: {error}",
                    "groupsJson": "[]",
                }
            )
            continue

        group_count = len(result["groups"])
        item_count = result["topLevelCount"]
        summary["groups"] += group_count
        summary["topLevelInlineMath"] += item_count
        summary["nestedInlineMathExcluded"] += result["nestedExcludedCount"]
        if item_count:
            summary["questionsWithTopLevelInlineMath"] += 1
            status = "processed"
        else:
            summary["questionsWithoutTopLevelInlineMath"] += 1
            status = "no top-level InlineMath"

        output_rows.append(
            {
                "sourceRow": source_row,
                "questionId": result["questionId"],
                "resourceCode": str(resource_code or ""),
                "questionNumber": question_number,
                "groupCount": group_count,
                "itemCount": item_count,
                "status": status,
                "groupsJson": groups_json(result),
            }
        )
        detail_rows.extend(flatten_group_details(result, source_row, resource_code))

    payload = {
        "sourceWorkbook": str(args.input),
        "sourceSheet": args.sheet,
        "summary": summary,
        "outputRows": output_rows,
        "detailRows": detail_rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
