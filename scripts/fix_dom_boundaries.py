"""Targeted DOM boundary fix: keep <br> and half-line-padding inside one wrapper boundary."""
from __future__ import annotations

import argparse
import copy
import html as html_lib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import openpyxl
from lxml import html as lxml_html

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from inline_math_grouping import inner_html, parse_html_fragment  # noqa: E402


def qid_key(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def source_ids_by_qid(path: Path, sheet: str) -> dict[str, set[str]]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[sheet]
    it = ws.iter_rows(values_only=True)
    headers = list(next(it))
    cols = {str(v).lower(): i for i, v in enumerate(headers) if v}
    result: dict[str, set[str]] = {}
    for row in it:
        qid = qid_key(row[cols["questionid"]])
        root = parse_html_fragment(row[cols["questionhtml"]] or "")
        result[qid] = set(root.xpath("//*[@id]/@id"))
    return result


def is_half_line(element) -> bool:
    return (
        element is not None
        and str(element.tag).lower() == "span"
        and "half-line-padding" in (element.get("class") or "").split()
    )


def boundary_hits(root, source_ids: set[str]) -> list[tuple[Any, Any, Any]]:
    hits = []
    for wrapper in list(root.xpath("//div[@id]")):
        wrapper_id = wrapper.get("id") or ""
        if wrapper_id in source_ids:
            continue
        previous = wrapper.getprevious()
        first = wrapper[0] if len(wrapper) else None
        if (
            previous is not None
            and str(previous.tag).lower() == "br"
            and is_half_line(first)
        ):
            hits.append((wrapper, previous, first))
    return hits


def move_wrapper_before_pair(wrapper, br) -> None:
    parent = wrapper.getparent()
    if parent is None or br.getparent() is not parent:
        raise ValueError("wrapper/br are not siblings")
    wrapper_index = parent.index(wrapper)
    parent.remove(wrapper)
    parent.remove(br)
    parent.insert(wrapper_index - 1, wrapper)
    wrapper.insert(0, br)


def question_xml(converted_html: str) -> str:
    return f"<question>{html_lib.escape(converted_html, quote=True)}</question>"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("previous_json", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--sheet", default="Data")
    args = parser.parse_args()

    payload = json.loads(args.previous_json.read_text(encoding="utf-8"))
    source_ids = source_ids_by_qid(args.input, args.sheet)
    output_rows = []
    affected_rows = []
    affected_wrappers = 0
    for row in payload["rows"]:
        updated = dict(row)
        qid = qid_key(row.get("questionId"))
        root = parse_html_fragment(row.get("convertedQuestionHtml") or "")
        row_hits = []
        while True:
            hits = boundary_hits(root, source_ids.get(qid, set()))
            if not hits:
                break
            # Process from the last hit so sibling indices remain stable.
            wrapper, br, _ = hits[-1]
            move_wrapper_before_pair(wrapper, br)
            row_hits.append(wrapper.get("id") or "")
        if row_hits:
            affected_rows.append({"excelRow": row["excelRow"], "questionId": qid, "wrapperIds": list(reversed(row_hits))})
            affected_wrappers += len(row_hits)
            converted_html = inner_html(root)
            updated["convertedQuestionHtml"] = converted_html
            updated["convertedQuestionXml"] = question_xml(converted_html)
            updated["conversionNote"] = (
                f"{args.version}: targeted DOM boundary fix moved {len(row_hits)} wrapper boundary(ies); "
                "grouping, IDs, and aria-labelledby unchanged."
            )
        output_rows.append(updated)

    result = dict(payload)
    result["version"] = args.version
    result["rows"] = output_rows
    result["targetedDomFix"] = {
        "baseVersion": payload.get("version", ""),
        "rule": "Move generated wrapper boundary before <br> + span.half-line-padding pair",
        "affectedRowCount": len(affected_rows),
        "movedWrapperCount": affected_wrappers,
        "affectedRows": affected_rows,
        "groupingRecomputed": False,
        "classificationRecomputed": False,
        "idsOrAriaChanged": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result["targetedDomFix"], ensure_ascii=False))


if __name__ == "__main__":
    main()

