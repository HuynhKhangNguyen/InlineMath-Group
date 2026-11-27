"""Prepare a versioned conversion from an all-source audit and a saved baseline."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

from workbook_contract import CONVERSION_COLUMNS, data_rows, index_rows, key_value, sha256

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from inline_math_grouping import (
    NUMBERLINE_SKIP_CONTEXT, _question_stem, convert_question_html, has_fib_numberline, numberline_skip_result,
    _question_xml_fragment, normalize_html_class_attributes, parse_html_fragment, protected_table, select_inline_math,
)

METRICS = (
    "sourceInlineMath", "numberlineSkippedInlineMath", "processableInlineMath",
    "processedInlineMath", "groupingErrorInlineMath", "processedGroups",
    "protectedInlineMath", "nestedExcluded", "outsideLayout",
)
STATES = ("updated", "added", "deleted", "unchanged")


def verify_audit(audit, old_index, new_index):
    expected = {
        "updated": old_index.keys() & new_index.keys(),
        "unchanged": old_index.keys() & new_index.keys(),
        "added": new_index.keys() - old_index.keys(),
        "deleted": old_index.keys() - new_index.keys(),
    }
    classes = {}
    for state in STATES:
        if len(audit[state]) != audit["counts"][state]:
            raise ValueError(f"Audit count does not match its {state} list.")
        for record in audit[state]:
            key = record["key"]
            if key in classes or key not in expected[state]:
                raise ValueError(f"Invalid or duplicate audit key {key} in {state}.")
            for field, index in (("oldRow", old_index), ("newRow", new_index)):
                if key in index and record.get(field) != index[key][0]:
                    raise ValueError(f"Audit {field} does not match {key}.")
            classes[key] = state
    if classes.keys() != old_index.keys() | new_index.keys():
        raise ValueError("Audit classifications do not cover both inputs.")
    return classes


def retained_metrics(source_html, row):
    """Count the baseline as saved, without regrouping it."""
    root = parse_html_fragment(source_html or "")
    controls, nested = select_inline_math(root)
    count = len(controls) + len(nested)
    metrics = dict.fromkeys(METRICS, 0)
    metrics["sourceInlineMath"] = count
    if row["ContextType"] == NUMBERLINE_SKIP_CONTEXT:
        metrics["numberlineSkippedInlineMath"] = count
        row["numberlineSkippedInlineMath"] = count
        return metrics

    eligible = []
    for index, control in enumerate(controls):
        if protected_table(control)[1]:
            metrics["protectedInlineMath"] += 1
        elif _question_stem(control) is None:
            metrics["outsideLayout"] += 1
        else:
            eligible.append(index)
    metrics["nestedExcluded"] = len(nested)
    metrics["processableInlineMath"] = len(eligible)
    converted, _ = select_inline_math(parse_html_fragment(row["convertedQuestionHtml"] or ""))
    if len(controls) != len(converted):
        raise ValueError(f"Retained question {row['questionId']} has a baseline control-count mismatch.")
    labelled = [
        converted[index] for index in eligible
        if (converted[index].get("aria-labelledby") or converted[index].get("aria-label") or "").strip()
    ]
    metrics["processedInlineMath"] = len(labelled)
    pending = len(eligible) - len(labelled)
    if pending and row.get("ErrorType") != "Grouping Error":
        raise ValueError(f"Cannot account for {pending} unlabelled controls in baseline question {row['questionId']}.")
    metrics["groupingErrorInlineMath"] = pending
    groups_in_note = re.search(r"across (\d+) group\(s\)", row["conversionNote"] or "")
    labels = {c.get("aria-labelledby") for c in labelled if c.get("aria-labelledby")}
    metrics["processedGroups"] = int(groups_in_note[1]) if groups_in_note else len(labels)
    row["groupingErrorInlineMath"] = pending
    return metrics


def prepare(input_path, baseline, audit_path, version, repair_keys=()):
    audit = json.loads(audit_path.read_text(encoding="utf-8-sig"))
    key = audit["matching"]["primaryKey"]
    evidence = audit["validation"]
    if (
        evidence["status"] != "PASS" or not evidence["keysCompleteAndUnique"]
        or not evidence["countsReconcile"] or key not in {"questionuid", "questionid"}
        or audit["comparison"]["scope"] != "all-source-fields"
        or audit["newFile"]["kind"] != "input" or audit["oldFile"]["kind"] != "input"
    ):
        raise ValueError("Provide a PASS all-source-fields audit of two input workbooks.")
    old_path = Path(audit["oldFile"]["path"]).resolve()
    if len({old_path, input_path, baseline}) != 3:
        raise ValueError("Old input, new input and baseline output must be distinct files.")
    source_sheet = audit["newFile"]["sheet"]
    paths = {"oldInput": old_path, "newInput": input_path, "baseline": baseline, "audit": audit_path}
    hashes = {name: sha256(path) for name, path in paths.items()}
    for name, field in (("oldInput", "oldFile"), ("newInput", "newFile")):
        if hashes[name] != audit[field]["sha256"].lower():
            raise ValueError(f"The {name} workbook changed since the audit.")

    header, new_rows = data_rows(input_path, source_sheet)
    old_header, old_rows = data_rows(old_path, audit["oldFile"]["sheet"])
    base_header, base_rows = data_rows(baseline)
    source_fields = [name.strip().lower() for name in header]
    old_fields = [name.strip().lower() for name in old_header]
    base_fields = [name.strip().lower() for name in base_header]
    if set(source_fields) | set(old_fields) != set(audit["comparison"]["fields"]):
        raise ValueError("The audit does not cover the complete source schema.")
    conversion_fields = {name.lower() for name in CONVERSION_COLUMNS}
    if not (set(old_fields) | conversion_fields) <= set(base_fields):
        raise ValueError("The baseline workbook lacks old source or conversion columns.")
    extra = [name for name in base_header if name.strip().lower() not in set(old_fields) | conversion_fields]
    if not any(name.lower() == "data_change" for name in extra):
        extra.insert(0, "Data_Change")
    if any(name.strip().lower() in source_fields for name in extra + list(CONVERSION_COLUMNS)):
        raise ValueError("A source column conflicts with an output-only column.")

    old_index = index_rows(old_rows, key, old_path)
    new_index = index_rows(new_rows, key, input_path)
    base_index = index_rows(base_rows, key, baseline)
    if len(old_index) != audit["counts"]["old"] or len(new_index) != audit["counts"]["new"]:
        raise ValueError("The audit totals do not match the source workbooks.")
    if base_index.keys() != old_index.keys():
        raise ValueError("The baseline output does not cover exactly the old input questions.")
    classes = verify_audit(audit, old_index, new_index)
    repair_keys = list(repair_keys)
    if len(set(repair_keys)) != len(repair_keys) or any(classes.get(k) != "unchanged" for k in repair_keys):
        raise ValueError("Repair keys must be unique exact keys of Unchanged questions.")
    repairs = set(repair_keys)
    rows, recomputed, numberline_skips = [], [], []
    merged = [header]
    drift_fields = Counter()
    counts = Counter(sourceRows=len(new_rows), parseErrors=0)
    for uid, (number, new) in new_index.items():
        state = classes[uid]
        base_number, base = base_index.get(uid, (None, {}))
        row = {
            "excelRow": number, "questionId": key_value(new.get("questionid")),
            "auditKey": uid, "baselineRow": base_number, "dataChange": state.title(),
        }
        markup = new["questionhtml"] or ""
        root = parse_html_fragment(markup) if state == "unchanged" else None
        enforce_skip = root is not None and has_fib_numberline(root)
        if enforce_skip:
            row["enforceNumberlineSkip"] = True
            numberline_skips.append(uid)
        if uid in repairs and not enforce_skip:
            row["forceRecompute"] = True
        values = new
        if state == "unchanged" and not enforce_skip and not row.get("forceRecompute"):
            values = base
            row.update({name: base[name.lower()] for name in CONVERSION_COLUMNS})
            original_html = row["convertedQuestionHtml"] or ""
            normalized_html = normalize_html_class_attributes(original_html)
            if normalized_html != original_html:
                row["convertedQuestionHtml"] = normalized_html
                row["convertedQuestionXml"] = _question_xml_fragment(normalized_html)
            metrics = retained_metrics(base["questionhtml"], row)
            for field in source_fields:
                if base.get(field) != new[field]:
                    drift_fields[field] += 1
        else:
            if enforce_skip:
                controls, nested = select_inline_math(root)
                result = numberline_skip_result(markup, new.get("questionid"), len(controls) + len(nested))
            else:
                result = convert_question_html(markup, new.get("questionid"))
                recomputed.append(uid)
            row.update({name: result[name] for name in (
                "convertedQuestionHtml", "convertedQuestionXml", "groupingErrorInlineMath",
                "numberlineSkippedInlineMath",
            )})
            row.update(Type=result["type"], ContextType=result["contextType"],
                       ErrorType=result["errorType"] or None,
                       conversionNote=f"{version}: {result['conversionNote']}")
            metrics = {name: result[name] for name in METRICS}
        extra_values = [base.get(name.strip().lower()) for name in extra]
        for offset, name in enumerate(extra):
            normalized = name.strip().lower()
            if normalized == "data_change":
                extra_values[offset] = state.title()
            elif (state != "unchanged" or enforce_skip or row.get("forceRecompute")) and normalized in {"review_status", "review_note"}:
                extra_values[offset] = None
                if row["ContextType"] == NUMBERLINE_SKIP_CONTEXT:
                    extra_values[offset] = "Skip" if normalized == "review_status" else row["conversionNote"]
        row["extraValues"] = extra_values
        merged.append([values.get(field) for field in source_fields])
        counts.update(metrics)
        rows.append(row)

    for name, path in paths.items():
        if sha256(path) != hashes[name]:
            raise ValueError(f"{name} changed during conversion.")
    return {
        "version": version, "sourceWorkbook": str(input_path), "sourceSheet": source_sheet,
        "sourceValues": merged, "summary": dict(counts), "rows": rows,
        "typeCounts": dict(Counter(r["Type"] for r in rows)),
        "contextTypeCounts": dict(Counter(r["ContextType"] for r in rows)),
        "errorTypeCounts": dict(Counter(r["ErrorType"] for r in rows if r["ErrorType"])),
        "incremental": {
            "key": key, "files": {name: str(path) for name, path in paths.items()}, "hashes": hashes,
            "counts": audit["counts"], "recomputedKeys": recomputed,
            "repairKeys": [r["auditKey"] for r in rows if r.get("forceRecompute")],
            "requestedRepairKeys": repair_keys,
            "deletedKeys": [r["key"] for r in audit["deleted"]],
            "extraHeaders": extra, "numberlineSkipUnchangedKeys": numberline_skips,
            "sourceDifferencesInRetainedRows": dict(drift_fields),
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("baseline_output", type=Path)
    parser.add_argument("audit", type=Path)
    parser.add_argument("payload", type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--repair-key", action="append", default=[],
                        help="Explicit audited Unchanged UID/ID to repair; repeat for multiple questions.")
    args = parser.parse_args()
    if not re.fullmatch(r"v[1-9]\d*", args.version):
        parser.error("--version must be a numbered version such as v4")
    if args.payload.exists():
        raise FileExistsError(args.payload)
    payload = prepare(args.input.resolve(), args.baseline_output.resolve(), args.audit.resolve(), args.version, args.repair_key)
    with args.payload.open("x", encoding="utf-8") as output:
        json.dump(payload, output, ensure_ascii=False)
    print(json.dumps({
        "counts": payload["incremental"]["counts"],
        "recomputed": len(payload["incremental"]["recomputedKeys"]),
        "numberlineSkipUnchanged": len(payload["incremental"]["numberlineSkipUnchangedKeys"]),
        "payload": str(args.payload),
    }))


if __name__ == "__main__":
    main()
