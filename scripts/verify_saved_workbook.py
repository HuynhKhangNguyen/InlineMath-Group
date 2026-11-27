"""Check the actual Excel file against its source, conversion payload and baseline."""

import argparse
import json
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path

import openpyxl

from workbook_contract import CONVERSION_COLUMNS, data_rows, expected_review, expected_summary, key_value, sha256, worksheet_values

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from inline_math_grouping import (
    NUMBERLINE_SKIP_CONTEXT, NUMBERLINE_SKIP_NOTE, _question_xml_fragment, has_fib_numberline,
    normalize_html_class_attributes, parse_html_fragment,
)

WORKBOOK_REPORT_HEADERS = ("sourceRow", "questionId", "Type", "ErrorType", "ContextType", "conversionNote")


def blank(value):
    return None if value == "" else value


def verify_data(book, output_path, source_path, payload, state, baseline):
    source_sheet = payload["sourceSheet"]
    output = book["Data" if state else source_sheet]
    source_header, source_rows = data_rows(source_path, source_sheet)
    source_fields = [name.strip().lower() for name in source_header]
    width = len(source_header)
    extra_headers = state["extraHeaders"] if state else []
    headings = [*source_header, *CONVERSION_COLUMNS, *extra_headers]
    actual = worksheet_values(output_path, output.title)
    if list(actual[0]) != headings or len(actual) != len(source_rows) + 1:
        raise ValueError("Saved Data headers or row count do not match the expected shape.")
    if len(source_rows) != len(payload["rows"]):
        raise ValueError("Payload rows do not cover the entire source sheet.")

    if baseline:
        base = baseline["Data"]
        base_columns = {
            cell.value.strip().lower(): cell.column
            for cell in base[1] if isinstance(cell.value, str)
        }
    seen_keys = set()
    change_counts = Counter()
    recomputed = []
    skipped_unchanged = []
    retained_xml_mismatches = []
    conversion_indices = {field: width + offset for offset, field in enumerate(CONVERSION_COLUMNS)}
    for number, (saved, source, row) in enumerate(zip(actual[1:], source_rows, payload["rows"]), 2):
        if row["excelRow"] != number:
            raise ValueError(f"Invalid payload row number: {row['excelRow']}")
        unchanged = state and row["dataChange"] == "Unchanged"
        markup = source["questionhtml"] or ""
        numberline = has_fib_numberline(parse_html_fragment(markup))
        skip = bool(unchanged and numberline)
        if skip != bool(row.get("enforceNumberlineSkip")):
            raise ValueError(f"Incorrect FIB_Numberline policy at row {number}.")
        if skip:
            skipped_unchanged.append(row["auditKey"])
        if numberline:
            normalized_markup = normalize_html_class_attributes(markup)
            expected_conversion = [normalized_markup, _question_xml_fragment(normalized_markup), NUMBERLINE_SKIP_CONTEXT,
                                   None, NUMBERLINE_SKIP_CONTEXT]
            if list(map(blank, saved[width:width + 5])) != expected_conversion or not re.sub(
                r"^v\d+:\s*", "", saved[conversion_indices["conversionNote"]] or ""
            ).startswith(NUMBERLINE_SKIP_NOTE):
                raise ValueError(f"FIB_Numberline was not saved verbatim and marked Skip at row {number}.")
        elif any(saved[conversion_indices[field]] == NUMBERLINE_SKIP_CONTEXT for field in ("Type", "ContextType")):
            raise ValueError(f"Saved FIB_Numberline Skip on a non-numberline row {number}.")
        repair = bool(row.get("forceRecompute"))
        if repair != bool(state and row["auditKey"] in state.get("repairKeys", [])) or (repair and (not unchanged or skip)):
            raise ValueError(f"Invalid explicit repair scope at row {number}.")
        if unchanged and not skip and not repair:
            for column, label in enumerate(headings, 1):
                field = label.strip().lower()
                if field == "data_change":
                    continue
                prior = base_columns.get(field)
                if prior is None:
                    raise ValueError(f"Retained field {label} missing from baseline.")
                a = output.cell(number, column)
                b = base.cell(row["baselineRow"], prior)
                expected_value = b.value
                if field in {"convertedquestionhtml", "convertedquestionxml"}:
                    original_html = base.cell(row["baselineRow"], base_columns["convertedquestionhtml"]).value or ""
                    normalized_html = normalize_html_class_attributes(original_html)
                    if normalized_html != original_html:
                        expected_value = normalized_html if field == "convertedquestionhtml" else _question_xml_fragment(normalized_html)
                if (a.value, a.data_type, a.style_id) != (expected_value, b.data_type, b.style_id):
                    raise ValueError(f"Retained baseline value, type or style changed at {a.coordinate}.")
        else:
            for column, field in enumerate(source_fields):
                if source[field] != saved[column]:
                    raise ValueError(f"Source field {field} changed at row {number}.")
            if state and (not unchanged or repair):
                recomputed.append(row["auditKey"])
        for offset, field in enumerate(CONVERSION_COLUMNS, width):
            if blank(saved[offset]) != blank(row.get(field)):
                raise ValueError(f"Saved conversion field {field} differs at row {number}.")
        converted_html = saved[conversion_indices["convertedQuestionHtml"]] or ""
        converted_root = parse_html_fragment(converted_html)
        if any(name.casefold() == "classname" for element in converted_root.iter() for name in element.attrib):
            raise ValueError(f"Saved className attribute remains at row {number}.")
        if saved[conversion_indices["convertedQuestionXml"]] != _question_xml_fragment(converted_html):
            if unchanged and not skip and not repair:
                # Exact baseline equality was checked above. Report legacy user edits;
                # do not force a migration of an unrelated retained conversion pair.
                retained_xml_mismatches.append(number)
            else:
                raise ValueError(f"Saved converted XML differs from converted HTML at row {number}.")
        if state:
            change_counts[row["dataChange"].lower()] += 1
            key = state["key"]
            actual_key = key_value(saved[source_fields.index(key)])
            if actual_key != row["auditKey"] or actual_key != key_value(source[key]) or actual_key in seen_keys:
                raise ValueError(f"Saved question key or order differs at row {number}.")
            seen_keys.add(actual_key)
            extras = saved[width + len(CONVERSION_COLUMNS):]
            if tuple(map(blank, extras)) != tuple(map(blank, row["extraValues"])):
                raise ValueError(f"Saved review or change metadata differs at row {number}.")
    if state:
        if (
            recomputed != state["recomputedKeys"] or seen_keys.intersection(state["deletedKeys"])
            or skipped_unchanged != state["numberlineSkipUnchangedKeys"]
            or len(recomputed) != state["counts"]["updated"] + state["counts"]["added"] + len(state.get("repairKeys", []))
            or len(seen_keys) != state["counts"]["new"]
            or len(set(state["deletedKeys"])) != state["counts"]["deleted"]
            or any(change_counts[name] != state["counts"][name] for name in ("updated", "added", "unchanged"))
        ):
            raise ValueError("Saved keys or recompute scope do not match the source audit.")
        if output.auto_filter.ref != output.calculate_dimension():
            raise ValueError("Data AutoFilter must include the entire saved range.")
        if output.freeze_panes != base.freeze_panes:
            raise ValueError("Data freeze panes changed from the baseline.")
    return retained_xml_mismatches


def verify_report_sheets(book, payload, state):
    summary_rows = list(book["Conversion_Summary"].values)
    expected = expected_summary(payload)
    if state:
        expected.update({f"{name.title()} questions": state["counts"][name] for name in (
            "updated", "added", "deleted", "unchanged"
        )})
        expected["FIB_Numberline skips in Unchanged"] = len(state["numberlineSkipUnchangedKeys"])
        if state.get("requestedRepairKeys"):
            expected["Additional repaired questions"] = len(state.get("repairKeys", []))
    metrics = {}
    for row in summary_rows[2:]:
        label = row[0]
        if label in metrics:
            raise ValueError(f"Duplicate summary metric {label}.")
        metrics[label] = row[1]
    if metrics != expected:
        bad = [label for label in metrics.keys() | expected.keys() if metrics.get(label) != expected.get(label)]
        raise ValueError(f"Saved summary differs: {bad}")
    if summary_rows[0][1] != payload["version"]:
        raise ValueError("Saved summary has the wrong version.")
    count = expected["Source InlineMath"]
    if "processedInlineMath" in payload["summary"] and count != sum(expected[name] for name in (
        "Processed InlineMath", "Grouping Error InlineMath", "Protected InlineMath",
        "FIB_Numberline skipped InlineMath", "Nested excluded", "Outside layout"
    )):
        raise ValueError("Summary control counts do not reconcile.")
    review = list(book["Review_Queue"].values)
    if tuple(review[0][:6]) != WORKBOOK_REPORT_HEADERS:
        raise ValueError("Review queue columns differ.")
    rows = [tuple(map(blank, r[:6])) for r in review[1:]]
    if rows != [tuple(map(blank, r)) for r in expected_review(payload)]:
        raise ValueError("Saved review queue does not match the conversion rows.")
    return len(rows)


def verify(path, payload):
    state = payload.get("incremental", {})
    state = state if state.get("files", {}).get("baseline") else None
    source_path = Path(payload["sourceWorkbook"])
    with zipfile.ZipFile(path) as archive:
        if archive.testzip():
            raise ValueError("Saved workbook has a corrupt component.")
    book = openpyxl.load_workbook(path)
    baseline = None
    try:
        if state:
            for name, file in state["files"].items():
                if sha256(file) != state["hashes"][name]:
                    raise ValueError(f"{name} changed before saved workbook verification.")
            baseline = openpyxl.load_workbook(state["files"]["baseline"])
            if book.sheetnames != baseline.sheetnames:
                raise ValueError("Saved workbook changed the baseline sheet list.")
        retained_xml_mismatches = verify_data(book, path, source_path, payload, state, baseline)
        review_rows = verify_report_sheets(book, payload, state)
    finally:
        book.close()
        if baseline:
            baseline.close()
    return {
        "status": "PASS", "workbook": str(path.resolve()), "sha256": sha256(path),
        "sourceRows": len(payload["rows"]), "reviewRows": review_rows,
        "retainedXmlMismatchRows": retained_xml_mismatches,
        **({"incremental": state["counts"], "recomputedKeys": state["recomputedKeys"],
            "repairKeys": state.get("repairKeys", []),
            "numberlineSkipUnchangedKeys": state["numberlineSkipUnchangedKeys"],
            "sourceDifferencesInRetainedRows": state["sourceDifferencesInRetainedRows"]}
           if state else {}),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path)
    parser.add_argument("payload", type=Path)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.payload.read_text(encoding="utf-8"))
    report = verify(args.workbook, payload)
    with args.report.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({key: report[key] for key in ("status", "workbook", "sourceRows", "reviewRows")}))


if __name__ == "__main__":
    main()
