"""Shared payload fields and workbook checks for versioned outputs."""

import hashlib
from pathlib import Path

import openpyxl

from workbook_text import saved_text_cells

CONVERSION_COLUMNS = (
    "convertedQuestionHtml", "convertedQuestionXml", "Type", "ErrorType",
    "ContextType", "conversionNote",
)
REVIEW_CONTEXTS = {"Manual Review", "Mixed Context", "Skipped/FIB_Numberline"}
SUMMARY_METRICS = {
    "Source rows": "sourceRows",
    "Source InlineMath": "sourceInlineMath",
    "In-scope InlineMath": "processableInlineMath",
    "Processed InlineMath": "processedInlineMath",
    "Grouping Error InlineMath": "groupingErrorInlineMath",
    "Semantic groups": "processedGroups",
    "Protected InlineMath": "protectedInlineMath",
    "FIB_Numberline skipped InlineMath": "numberlineSkippedInlineMath",
    "Nested excluded": "nestedExcluded",
    "Outside layout": "outsideLayout",
    "Parse errors": "parseErrors",
}


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest() if hasattr(hashlib, "file_digest") else (
            hashlib.sha256(stream.read()).hexdigest()
        )


def worksheet_values(path, sheet, *, data_only=False):
    book = openpyxl.load_workbook(path, read_only=True, data_only=data_only)
    try:
        worksheet = book[sheet]
        text = saved_text_cells(path, worksheet._worksheet_path)
        return [tuple(text.get(getattr(cell, "coordinate", None), cell.value) for cell in row)
                for row in worksheet.iter_rows()]
    finally:
        book.close()


def data_rows(path, sheet="Data"):
    header, *rows = worksheet_values(path, sheet)
    header = list(header)
    while header and header[-1] is None:
        header.pop()
    normalized = [column.strip().lower() if isinstance(column, str) else "" for column in header]
    if "" in normalized or len(set(normalized)) != len(normalized):
        raise ValueError(f"Missing or duplicate headers in {path}:{sheet}")
    return header, [dict(zip(normalized, row)) for row in rows]


def key_value(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def index_rows(rows, key, source):
    index = {}
    for row_number, row in enumerate(rows, 2):
        value = key_value(row.get(key))
        if not value or value in index:
            raise ValueError(f"Missing or duplicate {key} at {source} row {row_number}")
        index[value] = row_number, row
    return index


def expected_summary(payload):
    return {
        **{label: payload["summary"].get(key, 0) for label, key in SUMMARY_METRICS.items()},
        "Grouping Error Questions": payload.get("errorTypeCounts", {}).get("Grouping Error", 0),
        **{f"ContextType: {key}": count for key, count in payload["contextTypeCounts"].items()},
    }


def expected_review(payload):
    return [
        (row["excelRow"], row["questionId"], row["Type"], row.get("ErrorType"),
         row["ContextType"], row["conversionNote"])
        for row in payload["rows"]
        if row.get("ErrorType") == "Grouping Error" or row["ContextType"] in REVIEW_CONTEXTS
    ]
