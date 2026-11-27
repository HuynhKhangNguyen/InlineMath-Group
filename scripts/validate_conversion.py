"""Validate structural integrity, semantic classifications, and known regressions."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

from workbook_contract import worksheet_values
from lxml import html as lxml_html

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from inline_math_grouping import (
    NUMBERLINE_SKIP_CONTEXT,
    NUMBERLINE_SKIP_NOTE,
    _context_for_structured_control,
    _direct_child,
    _has_high_confidence_result_head,
    _incomplete_numeric_scaffold_reason,
    _is_calculation_source,
    _looks_like_calculation_result,
    _nearest_preceding_calculation_source,
    _period_is_sentence_boundary,
    _question_xml_fragment,
    _question_stem,
    _segment_index_for_child,
    _segment_text,
    _segments,
    _text_with_placeholders,
    has_fib_numberline,
    normalize_html_class_attributes,
    protected_table,
    select_inline_math,
)


KNOWN_EXPECTATIONS = {
    **{row: (2, "Self-contained Input Context") for row in range(99, 105)},
    145: (1, "Self-contained Input Context"),
    151: (2, "Mixed Context"),
    152: (3, "Self-contained Input Context"),
    199: (1, "Preceding Context Required"),
    354: (2, "Self-contained Input Context"),
    355: (2, "Self-contained Input Context"),
    162: (1, "Preceding Context Required"),
    270: (1, "Preceding Context Required"),
    335: (1, "Manual Review"),
    336: (1, "Manual Review"),
    **{row: (1, "Self-contained Input Context") for row in range(385, 389)},
    682: (2, "Mixed Context"),
    986: (1, "Preceding Context Required"),
    991: (2, "Self-contained Input Context"),
    1032: (2, "Self-contained Input Context"),
}


KNOWN_EXPECTATION_QIDS = {99: '1954490', 100: '1954491', 101: '1954492', 102: '1954493', 103: '1954494', 104: '1954495', 145: '1954539', 151: '1954545', 152: '1954546', 199: '1954942', 354: '1953983', 355: '1953984', 162: '1966204', 270: '1955824', 335: '1953893', 336: '1953898', 385: '1954016', 386: '1954017', 387: '1954018', 388: '1954019', 682: '1955335', 986: '1955518', 991: '1962302', 1032: '1955591', 431: '1966664', 432: '1966665', 433: '1966666', 434: '1966667', 436: '1966669', 439: '1953751', 440: '1953752', 444: '1953756', 445: '1953757', 901: '1954828'}


def normalize_text(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def label_targets_inside_stem(control, targets):
    """Targets are strict descendants of the control's nearest stem."""
    stem = _question_stem(control)
    return bool(stem is not None and targets) and all(
        "question-stem-content" not in (target.get("class") or "").split()
        and _question_stem(target) is stem
        for target in targets
    )


def valid_composite_label_context(control, targets):
    """Keep independent rows separate while referring to real shared source."""
    stem = _question_stem(control)
    if not label_targets_inside_stem(control, targets):
        return False
    local = targets[-1]
    if control not in local.iter():
        return False
    for shared in targets[:-1]:
        controls, nested = select_inline_math(shared)
        if controls or nested or shared in local.iter():
            return False
    sections = {}
    section = 0
    for element in stem.iter():
        if element is not stem and _question_stem(element) is not stem:
            continue
        if "part_label" in (element.get("class") or "").split():
            section += 1
        sections[element] = section
    return all(
        target in sections and sections[target] == sections[control]
        for target in targets
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("conversion_json", type=Path)
    parser.add_argument("report_json", type=Path)
    parser.add_argument("--previous", type=Path)
    parser.add_argument(
        "--recomputed-only", action="store_true",
        help="Validate Updated/Added rows and required numberline skips in an audited incremental payload.",
    )
    parser.add_argument(
        "--skip-known-baseline",
        action="store_true",
        help="Skip CLA_G3-specific known-case expectations for another dataset.",
    )
    args = parser.parse_args()

    payload = json.loads(args.conversion_json.read_text(encoding="utf-8"))
    if args.recomputed_only:
        state = payload.get("incremental", {})
        if not state.get("files", {}).get("baseline"):
            parser.error("--recomputed-only requires an audited incremental payload")
        rows = [row for row in payload["rows"] if row["dataChange"] in {"Updated", "Added"} or row.get("forceRecompute")]
        repair_keys = [r["auditKey"] for r in rows if r.get("forceRecompute")]
        if repair_keys != state.get("repairKeys", []) or any(r["dataChange"] != "Unchanged" for r in rows if r.get("forceRecompute")):
            parser.error("Repair flags do not match the explicit Unchanged repair scope")
        keys = [r["auditKey"] for r in rows]
        if keys != state["recomputedKeys"] or len(keys) != len(set(keys)):
            parser.error("Recomputed rows do not match the audit call log")
        skip_keys = [r["auditKey"] for r in payload["rows"] if r.get("enforceNumberlineSkip")
                     and r["dataChange"] == "Unchanged"]
        if skip_keys != state.get("numberlineSkipUnchangedKeys", []):
            parser.error("Unchanged numberline skips do not match the recorded scope")
        validation_keys = set(keys) | set(skip_keys)
        rows = [row for row in payload["rows"] if row["auditKey"] in validation_keys]
        payload["rows"] = rows
        payload["summary"] = {
            metric: sum(row.get(metric, 0) for row in rows)
            for metric in ("groupingErrorInlineMath", "numberlineSkippedInlineMath")
        }
        payload["contextTypeCounts"] = dict(Counter(row["ContextType"] for row in rows))
        payload["errorTypeCounts"] = dict(Counter(row["ErrorType"] for row in rows if row["ErrorType"]))
    previous_payload = None
    if args.previous and args.previous.exists():
        previous_payload = json.loads(args.previous.read_text(encoding="utf-8"))
    headers, *source_rows = worksheet_values(
        payload["sourceWorkbook"], payload["sourceSheet"], data_only=True
    )
    html_column = headers.index("questionhtml")
    source_html = {
        row_number: (row[html_column] or "")
        for row_number, row in enumerate(source_rows, start=2)
    }

    structural = Counter()
    group_sizes = Counter()
    multi_groups = []
    overlong_groups = []
    manual_rows = []
    mixed_rows = []
    grouping_error_rows = []
    numberline_skip_rows = []
    row_group_counts = {}
    calculation_checks = Counter()
    calculation_source_included = []
    calculation_source_missing = []
    calculation_source_review = []
    accessible_label_texts = {}
    period_boundary_checks = Counter()
    period_boundary_failures = []

    # These cases exercise the shared boundary helper used by all context
    # selection paths. They guard against regressing to ``'.' -> boundary``.
    period_rule_cases = [
        ("1.7", 1, False, "decimal"),
        ("3.14", 1, False, "decimal"),
        ("7 in. [input]", 4, False, "measurement continuation"),
        ("7 in. Find", 4, True, "measurement sentence boundary"),
        ("Mr. Edson", 2, False, "title abbreviation"),
        ("e.g. example", 3, False, "multi-period abbreviation"),
    ]
    for sample, index, expected, kind in period_rule_cases:
        actual = _period_is_sentence_boundary(
            sample, index, terminal_abbreviation_is_continuation=kind == "measurement continuation"
        )
        period_boundary_checks["casesChecked"] += 1
        if actual != expected:
            period_boundary_failures.append(
                {"sample": sample, "index": index, "expected": expected, "actual": actual, "kind": kind}
            )

    for row in payload["rows"]:
        row_number = row["excelRow"]
        raw_html = source_html[row_number]
        normalized_source = normalize_html_class_attributes(raw_html)
        source_root = lxml_html.fragment_fromstring(normalized_source, create_parent="div")
        output_root = lxml_html.fragment_fromstring(row["convertedQuestionHtml"], create_parent="div")
        structural["outputClassNameAttributes"] += sum(
            name.casefold() == "classname"
            for element in output_root.iter() for name in element.attrib
        )
        if row.get("convertedQuestionXml") != _question_xml_fragment(row["convertedQuestionHtml"]):
            structural["convertedXmlMismatchRows"] += 1
        source_controls, source_nested = select_inline_math(source_root)
        output_controls, output_nested = select_inline_math(output_root)
        structural["sourceRows"] += 1
        structural["sourceControls"] += len(source_controls) + len(source_nested)
        structural["outputControls"] += len(output_controls) + len(output_nested)
        source_text = normalize_text(_text_with_placeholders(source_root))
        period_boundary_checks["decimalPeriods"] += len(
            re.findall(r"(?<![A-Za-z0-9])\d+\.\d+(?![A-Za-z0-9])", source_text)
        )
        period_boundary_checks["ignoredPeriods"] += sum(
            1
            for index, char in enumerate(source_text)
            if char == "." and not _period_is_sentence_boundary(source_text, index)
        )
        if len(source_controls) + len(source_nested) != len(output_controls) + len(output_nested):
            structural["controlCountMismatchRows"] += 1

        # Earlier payloads may contain carried-over results from before this
        # rule. New conversions declare the metric even on ordinary rows.
        declared_skip = row.get("numberlineSkippedInlineMath")
        marked_skip = NUMBERLINE_SKIP_CONTEXT in (row.get("Type"), row.get("ContextType"))
        source_has_numberline = has_fib_numberline(source_root)
        if marked_skip or (source_has_numberline and declared_skip is not None):
            count = len(source_controls) + len(source_nested)
            note = row.get("conversionNote") or ""
            if not (
                source_has_numberline
                and row.get("Type") == row.get("ContextType") == NUMBERLINE_SKIP_CONTEXT
                and not row.get("ErrorType")
                and not row.get("groupingErrorInlineMath")
                and (declared_skip is None or declared_skip == count)
                and re.sub(r"^v\d+:\s*", "", note).startswith(NUMBERLINE_SKIP_NOTE)
                and row["convertedQuestionHtml"] == normalized_source
                and row.get("convertedQuestionXml") == _question_xml_fragment(normalized_source)
            ):
                structural["numberlineSkipFailures"] += 1
            numberline_skip_rows.append(row_number)
            structural["numberlineSkippedControls"] += count
            row_group_counts[row_number] = 0
            accessible_label_texts[row_number] = []
            continue
        if declared_skip:
            structural["numberlineSkipFailures"] += 1

        ids = {}
        source_ids = set(source_root.xpath(".//*[@id]/@id"))
        for element in output_root.xpath(".//*[@id]"):
            ids.setdefault(element.get("id"), []).append(element)
            if element.get("id") not in source_ids and (
                "question-stem-content" in (element.get("class") or "").split()
                or _question_stem(element) is None
            ):
                structural["generatedIdsOutsideStem"] += 1
        structural["duplicateIds"] += sum(1 for matches in ids.values() if len(matches) > 1)

        accessible_label_texts[row_number] = []
        for output_control in output_controls:
            label_tokens = (output_control.get("aria-labelledby") or "").split()
            if len(label_tokens) > 1:
                structural["multiTokenAriaLabelledby"] += 1
            target_groups = [ids.get(token, []) for token in label_tokens]
            if label_tokens and all(len(targets) == 1 for targets in target_groups):
                label_text = normalize_text(
                    " ".join(
                        _text_with_placeholders(targets[0], include_image_alt=True) for targets in target_groups
                    )
                )
                accessible_label_texts[row_number].append(label_text)
                if _incomplete_numeric_scaffold_reason(label_text, source_text):
                    structural["incompleteScaffoldLabels"] += 1
            elif not label_tokens and (output_control.get("aria-label") or "").strip():
                # A source-provided aria-label is already a valid accessible
                # name.  It is especially common for table cells whose row
                # has no visible text to use as a generated label target.
                accessible_label_texts[row_number].append(
                    normalize_text(output_control.get("aria-label") or "")
                )

        labels = {}
        row_grouping_error_controls = 0
        for control_index, control in enumerate(output_controls):
            _, reasons = protected_table(control)
            label_id = control.get("aria-labelledby")
            if reasons:
                structural["protectedControls"] += 1
                if label_id:
                    structural["protectedControlsWithAria"] += 1
                continue
            if label_id:
                structural["labelledControls"] += 1
                labels.setdefault(label_id, []).append(control)
            elif (control.get("aria-label") or "").strip():
                structural["labelledControls"] += 1
            elif _question_stem(control) is None:
                structural["outsideLayoutControlsWithoutAria"] += 1
            else:
                if row.get("ErrorType") == "Grouping Error":
                    row_grouping_error_controls += 1
                    structural["groupingErrorControls"] += 1
                    source_control = (
                        source_controls[control_index]
                        if control_index < len(source_controls)
                        else None
                    )
                    if source_control is None or dict(source_control.attrib) != dict(control.attrib):
                        structural["groupingErrorControlChanges"] += 1
                else:
                    structural["processedControlsWithoutAria"] += 1

        error_type = row.get("ErrorType") or ""
        declared_error_controls = int(row.get("groupingErrorInlineMath", 0) or 0)
        if error_type == "Grouping Error":
            grouping_error_rows.append(row_number)
            if (
                declared_error_controls != row_grouping_error_controls
                or declared_error_controls == 0
                or row.get("ContextType") not in {"Manual Review", "Mixed Context"}
                or "Grouping Error" not in (row.get("conversionNote") or "")
            ):
                structural["groupingErrorAnnotationFailures"] += 1
        elif error_type or declared_error_controls or row_grouping_error_controls:
            structural["groupingErrorTypeMismatches"] += 1

        row_group_counts[row_number] = len(labels)
        for label_id, members in labels.items():
            group_sizes[len(members)] += 1
            label_tokens = label_id.split()
            target_groups = [ids.get(token, []) for token in label_tokens]
            if not label_tokens or any(len(targets) != 1 for targets in target_groups):
                structural["invalidLabelTargetCount"] += 1
                continue
            targets = [targets[0] for targets in target_groups]
            if any(not label_targets_inside_stem(member, targets) for member in members):
                structural["labelTargetsOutsideStem"] += 1
            if len(targets) > 1 and not valid_composite_label_context(members[0], targets):
                structural["invalidCompositeLabelContext"] += 1
            if len(targets) > 1 and any(member not in targets[-1].iter() for member in members):
                structural["invalidCompositeLabelContext"] += 1
            text = normalize_text(" ".join(
                _text_with_placeholders(target, include_image_alt=True).replace("[input]", "")
                for target in targets
            ))
            if not any(character.isalnum() for character in text):
                structural["emptyLabelText"] += 1
            if len(text) > 500:
                overlong_groups.append({"row": row_number, "labelId": label_id, "characters": len(text)})
            if len(members) > 1:
                multi_groups.append(
                    {"row": row_number, "labelId": label_id, "size": len(members), "text": text[:600]}
                )

        # For result-style contexts, confirm that a separate earlier formula
        # remains inside the same accessible label. Ambiguous or narrative-only
        # sources are reported for human review instead of guessed.
        for source_control, output_control in zip(source_controls, output_controls):
            if protected_table(source_control)[1]:
                continue
            stem = _question_stem(source_control)
            if stem is None:
                continue
            semantic_container = _context_for_structured_control(stem, source_control)
            if semantic_container is not None:
                local_text = _text_with_placeholders(semantic_container)
            else:
                stem_children = list(stem)
                anchor = _direct_child(stem, source_control)
                child_index = next(
                    (index for index, child in enumerate(stem_children) if child is anchor),
                    None,
                )
                if child_index is None:
                    continue
                segments = _segments(stem)
                segment_index = _segment_index_for_child(segments, child_index)
                local_text = _segment_text(stem, stem_children, *segments[segment_index])

            if not _looks_like_calculation_result(local_text):
                continue
            if _is_calculation_source(local_text):
                calculation_checks["localSourceControls"] += 1
                continue

            source = _nearest_preceding_calculation_source(stem, source_control)
            if source is None or source.get("ambiguous"):
                if _has_high_confidence_result_head(local_text):
                    calculation_source_review.append(row_number)
                continue

            calculation_checks["precedingSourceCandidates"] += 1
            label_id = output_control.get("aria-labelledby")
            label_tokens = label_id.split() if label_id else []
            target_groups = [ids.get(token, []) for token in label_tokens]
            targets = [targets[0] for targets in target_groups if len(targets) == 1]
            label_text = (
                normalize_text(" ".join(" ".join(target.itertext()) for target in targets))
                if label_tokens and len(targets) == len(label_tokens)
                else ""
            )
            source_text = normalize_text(source["text"])
            if source_text and source_text in label_text:
                calculation_checks["precedingSourceIncludedControls"] += 1
                calculation_source_included.append(
                    {
                        "row": row_number,
                        "questionId": row["questionId"],
                        "labelId": label_id,
                        "source": source_text[:240],
                        "context": label_text[:500],
                    }
                )
            else:
                calculation_checks["precedingSourceMissingControls"] += 1
                calculation_source_missing.append(
                    {"row": row_number, "labelId": label_id, "source": source_text[:300]}
                )

        if row["ContextType"] == "Manual Review":
            manual_rows.append(row_number)
        elif row["ContextType"] == "Mixed Context":
            mixed_rows.append(row_number)

    payload_by_row = {row["excelRow"]: row for row in payload["rows"]}
    payload_by_qid = {str(row.get("questionId", "")): row for row in payload["rows"]}
    previous_by_row = (
        {row["excelRow"]: row for row in previous_payload.get("rows", [])}
        if previous_payload
        else {}
    )
    previous_by_qid = (
        {str(row.get("questionId", "")): row for row in previous_payload.get("rows", [])}
        if previous_payload
        else {}
    )

    def resolve_known_row(row_number: int) -> dict | None:
        # Known cases are anchored to stable baseline questionids so that
        # deleted/inserted source rows do not shift the regression case.
        baseline_qid = KNOWN_EXPECTATION_QIDS.get(row_number)
        if baseline_qid and baseline_qid in payload_by_qid:
            return payload_by_qid[baseline_qid]
        previous_row = previous_by_row.get(row_number)
        if previous_row is not None:
            return payload_by_qid.get(str(previous_row.get("questionId", "")))
        return payload_by_row.get(row_number)

    def known_label(row_number: int) -> tuple[dict | None, str]:
        row = resolve_known_row(row_number)
        if row is None:
            return None, ""
        return row, " ".join(accessible_label_texts.get(row["excelRow"], []))

    known_failures = []
    if not (args.skip_known_baseline or args.recomputed_only):
        for row_number, (expected_groups, expected_context_type) in KNOWN_EXPECTATIONS.items():
            row = resolve_known_row(row_number)
            actual = (
                (row_group_counts.get(row["excelRow"]), row["ContextType"])
                if row is not None
                else (None, None)
            )
            expected = (expected_groups, expected_context_type)
            if actual != expected:
                known_failures.append({"row": row_number, "expected": expected, "actual": actual})

        for row_number in (431, 432, 433, 434, 436, 439, 440, 444, 445):
            _, label = known_label(row_number)
            if (
                not label
                or "exact" not in label.lower()
                or not re.search(r"[+−–×÷*/]", label)
            ):
                known_failures.append(
                    {"row": row_number, "expected": "one contiguous formula-to-Exact DOM range", "actual": label}
                )

        for row_number in (335, 336):
            row, label = known_label(row_number)
            distractor_leaked = row_number == 335 and any(
                phrase in label.lower() for phrase in ("seven thousand", "seventy thousand")
            )
            distractor_leaked = distractor_leaked or (
                row_number == 336 and any(phrase in label for phrase in ("6000 + 4", "600 + 4", "60 + 4", "6 + 400"))
            )
            if row["ContextType"] != "Manual Review" or distractor_leaked:
                known_failures.append(
                    {"row": row_number, "expected": "Manual Review without multiple-choice distractors", "actual": label}
                )

        _, row_901_label = known_label(901)
        if (
            "3 × 10¢ = 30¢" not in row_901_label
            or "30¢ ÷ 5¢ = 6" not in row_901_label
            or "The number of cards she can buy is" not in row_901_label
        ):
            known_failures.append(
                {"row": 901, "expected": "one contiguous calculation-to-input DOM range", "actual": row_901_label}
            )

    previous_changes = None
    if previous_payload is not None:
        changed_rows = []
        changed_question_ids = []
        for row in payload["rows"]:
            previous_row = previous_by_qid.get(str(row.get("questionId", "")))
            if (
                previous_row is None
                or previous_row.get("convertedQuestionHtml") != row["convertedQuestionHtml"]
                or previous_row.get("ContextType") != row["ContextType"]
            ):
                changed_rows.append(row["excelRow"])
                changed_question_ids.append(str(row.get("questionId", "")))
        removed_question_ids = sorted(set(previous_by_qid) - set(payload_by_qid))
        previous_changes = {
            "changedRowCount": len(changed_rows),
            "changedRows": changed_rows,
            "changedQuestionIds": changed_question_ids,
            "removedQuestionIds": removed_question_ids,
        }

    blocking_keys = [
        "outputClassNameAttributes",
        "convertedXmlMismatchRows",
        "controlCountMismatchRows",
        "duplicateIds",
        "protectedControlsWithAria",
        "processedControlsWithoutAria",
        "groupingErrorControlChanges",
        "groupingErrorAnnotationFailures",
        "groupingErrorTypeMismatches",
        "groupingErrorCountMismatches",
        "invalidLabelTargetCount",
        "generatedIdsOutsideStem",
        "labelTargetsOutsideStem",
        "emptyLabelText",
        "invalidCompositeLabelContext",
        "calculationSourceMissingControls",
        "incompleteScaffoldLabels",
        "periodBoundaryRuleFailures",
        "numberlineSkipFailures",
    ]
    structural["calculationSourceMissingControls"] = calculation_checks[
        "precedingSourceMissingControls"
    ]
    structural["periodBoundaryRuleFailures"] = len(period_boundary_failures)
    reported_grouping_errors = sum(
        int(row.get("groupingErrorInlineMath", 0) or 0) for row in payload["rows"]
    )
    if (
        structural["groupingErrorControls"] != reported_grouping_errors
        or reported_grouping_errors != payload.get("summary", {}).get("groupingErrorInlineMath", 0)
    ):
        structural["groupingErrorCountMismatches"] += 1
    declared_numberline_total = payload.get("summary", {}).get("numberlineSkippedInlineMath")
    if declared_numberline_total is not None and declared_numberline_total != structural["numberlineSkippedControls"]:
        structural["numberlineSkipFailures"] += 1
    blocking_issue_count = sum(structural[key] for key in blocking_keys) + len(known_failures)
    report = {
        "version": payload["version"],
        "status": "PASS" if blocking_issue_count == 0 else "FAIL",
        "scope": "recomputed-and-numberline-skips" if args.recomputed_only else "all",
        "structural": dict(structural),
        "groupSizeDistribution": {str(key): value for key, value in sorted(group_sizes.items())},
        "contextTypeCounts": payload["contextTypeCounts"],
        "manualReviewRows": manual_rows,
        "mixedContextRows": mixed_rows,
        "groupingErrorRows": grouping_error_rows,
        "numberlineSkipRows": numberline_skip_rows,
        "groupingErrorInlineMath": structural["groupingErrorControls"],
        "errorTypeCounts": payload.get("errorTypeCounts", {}),
        "overlongGroups": overlong_groups,
        "multiInputGroupCount": len(multi_groups),
        "multiInputGroups": multi_groups,
        "calculationSourceChecks": dict(calculation_checks),
        "calculationSourceIncluded": calculation_source_included,
        "calculationSourceMissing": calculation_source_missing,
        "incompleteScaffoldLabelControls": structural["incompleteScaffoldLabels"],
        "calculationSourceReviewRows": sorted(set(calculation_source_review)),
        "periodBoundaryChecks": dict(period_boundary_checks),
        "periodBoundaryFailures": period_boundary_failures,
        "knownCaseFailures": known_failures,
        "previousVersionComparison": previous_changes,
    }
    args.report_json.parent.mkdir(parents=True, exist_ok=True)
    args.report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("status", "structural", "contextTypeCounts", "manualReviewRows", "mixedContextRows", "groupingErrorRows", "groupingErrorInlineMath", "errorTypeCounts", "overlongGroups", "multiInputGroupCount", "calculationSourceChecks", "calculationSourceMissing", "calculationSourceReviewRows", "knownCaseFailures", "previousVersionComparison")}, ensure_ascii=False))
    if blocking_issue_count:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
