"""Restore source-cell values after Artifact Tool export without openpyxl.

Artifact Tool is used to create the workbook and generated output tabs. This
small OOXML repair step copies the original Data-sheet cell payloads back into
the exported workbook so blank strings and source line endings stay intact.
"""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

from lxml import etree

from workbook_contract import CONVERSION_COLUMNS
from workbook_text import decode_xstring, encode_xstring, visible_string


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
XML_NS = "http://www.w3.org/XML/1998/namespace"
NS = {"x": MAIN_NS, "r": REL_NS, "pr": PKG_REL_NS}


def _sheet_part(archive: zipfile.ZipFile, sheet_name: str) -> str:
    workbook = etree.fromstring(archive.read("xl/workbook.xml"))
    rels = etree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    rel_by_id = {
        rel.get("Id"): rel.get("Target")
        for rel in rels.xpath("./pr:Relationship", namespaces=NS)
    }
    sheets = workbook.xpath("./x:sheets/x:sheet[@name=$name]", namespaces=NS, name=sheet_name)
    if len(sheets) != 1:
        raise ValueError(f"Expected exactly one worksheet named {sheet_name!r}")
    relationship_id = sheets[0].get(f"{{{REL_NS}}}id")
    target = rel_by_id.get(relationship_id)
    if not target:
        raise ValueError(f"Missing worksheet relationship for {sheet_name!r}")
    if target.startswith("/"):
        return target.lstrip("/")
    return str(Path("xl") / target).replace("\\", "/")


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = etree.fromstring(archive.read("xl/sharedStrings.xml"))
    return [decode_xstring(visible_string(node)) for node in root.xpath("./x:si", namespaces=NS)]


def _cell_value(cell: etree._Element | None, shared_strings: list[str]):
    if cell is None:
        return None
    cell_type = cell.get("t")
    formula = cell.find(f"{{{MAIN_NS}}}f")
    value = cell.find(f"{{{MAIN_NS}}}v")
    inline = cell.find(f"{{{MAIN_NS}}}is")
    if formula is not None:
        return ("formula", cell_type, formula.text or "", value.text if value is not None else None)
    if cell_type == "inlineStr":
        return "string", decode_xstring(visible_string(inline)) if inline is not None else ""
    if cell_type == "s":
        if value is None:
            return "string", ""
        return "string", shared_strings[int(value.text or "0")]
    if cell_type in {"str"}:
        return "string", decode_xstring(value.text or "") if value is not None else ""
    if cell_type == "b":
        return "boolean", value.text if value is not None else ""
    if cell_type == "e":
        return "error", value.text if value is not None else ""
    if value is None:
        return None
    return "number", value.text


def _column_index(cell_reference: str) -> int:
    value = 0
    for character in cell_reference:
        if not character.isalpha():
            break
        value = value * 26 + ord(character.upper()) - ord("A") + 1
    return value


def _cell_map(sheet_root: etree._Element) -> dict[str, etree._Element]:
    return {
        cell.get("r"): cell
        for cell in sheet_root.xpath(".//x:sheetData/x:row/x:c", namespaces=NS)
        if cell.get("r")
    }


def _ensure_output_cell(sheet_root: etree._Element, reference: str) -> etree._Element:
    existing = sheet_root.xpath(
        ".//x:sheetData/x:row/x:c[@r=$ref]", namespaces=NS, ref=reference
    )
    if existing:
        return existing[0]
    row_number = "".join(character for character in reference if character.isdigit())
    rows = sheet_root.xpath(
        ".//x:sheetData/x:row[@r=$row]", namespaces=NS, row=row_number
    )
    if rows:
        row = rows[0]
    else:
        sheet_data = sheet_root.find(f"{{{MAIN_NS}}}sheetData")
        if sheet_data is None:
            raise ValueError("Output worksheet has no sheetData")
        row = etree.Element(f"{{{MAIN_NS}}}row", r=row_number)
        insert_at = next(
            (
                index
                for index, existing_row in enumerate(sheet_data)
                if int(existing_row.get("r", "0")) > int(row_number)
            ),
            len(sheet_data),
        )
        sheet_data.insert(insert_at, row)
    cell = etree.Element(f"{{{MAIN_NS}}}c", r=reference)
    column = _column_index(reference)
    insert_at = next(
        (
            index
            for index, existing_cell in enumerate(row)
            if existing_cell.tag == f"{{{MAIN_NS}}}c"
            and _column_index(existing_cell.get("r", "")) > column
        ),
        len(row),
    )
    row.insert(insert_at, cell)
    return cell


def _copy_value(source_cell: etree._Element, output_cell: etree._Element) -> None:
    for child in list(output_cell):
        output_cell.remove(child)
    for attribute in list(output_cell.attrib):
        if attribute != "r":
            del output_cell.attrib[attribute]

    source_type = source_cell.get("t")
    formula = source_cell.find(f"{{{MAIN_NS}}}f")
    value = source_cell.find(f"{{{MAIN_NS}}}v")
    inline = source_cell.find(f"{{{MAIN_NS}}}is")

    if source_type == "s":
        raise ValueError("Shared-string cells must be decoded before copying")
    if source_type == "inlineStr":
        output_cell.set("t", "inlineStr")
        copied_inline = etree.Element(f"{{{MAIN_NS}}}is")
        if inline is not None:
            for child in inline:
                copied_inline.append(etree.fromstring(etree.tostring(child)))
        output_cell.append(copied_inline)
        return
    if source_type is not None:
        output_cell.set("t", source_type)
    if formula is not None:
        output_cell.append(etree.fromstring(etree.tostring(formula)))
    if value is not None:
        output_cell.append(etree.fromstring(etree.tostring(value)))


def _write_inline_text(cell: etree._Element, text: str) -> None:
    for child in list(cell):
        cell.remove(child)
    for attribute in list(cell.attrib):
        if attribute not in {"r", "s"}:
            del cell.attrib[attribute]
    cell.set("t", "inlineStr")
    inline = etree.SubElement(cell, f"{{{MAIN_NS}}}is")
    text_node = etree.SubElement(inline, f"{{{MAIN_NS}}}t")
    text_node.set(f"{{{XML_NS}}}space", "preserve")
    text_node.text = encode_xstring(text)


def restore(
    input_path: Path, artifact_path: Path, output_path: Path,
    conversion_path: Path | None = None,
) -> dict[str, int]:
    if output_path.exists():
        raise FileExistsError(f"Refusing to overwrite existing output: {output_path}")
    conversion_rows = []
    sheet_name = "Data"
    if conversion_path:
        payload = json.loads(conversion_path.read_text(encoding="utf-8"))
        conversion_rows = payload["rows"]
        sheet_name = payload.get("sourceSheet", sheet_name)
    repaired_conversion_cells = {}
    with zipfile.ZipFile(input_path, "r") as source_zip, zipfile.ZipFile(
        artifact_path, "r"
    ) as output_zip:
        source_part = _sheet_part(source_zip, sheet_name)
        output_part = _sheet_part(output_zip, sheet_name)
        source_sheet = etree.fromstring(source_zip.read(source_part))
        output_sheet = etree.fromstring(output_zip.read(output_part))
        source_shared = _shared_strings(source_zip)
        output_shared = _shared_strings(output_zip)

        source_cells = _cell_map(source_sheet)
        output_cells = _cell_map(output_sheet)
        source_row_count = max(
            (int("".join(character for character in ref if character.isdigit())) for ref in source_cells),
            default=0,
        )
        source_column_count = max(
            (_column_index(ref) for ref in source_cells if int("".join(c for c in ref if c.isdigit())) == 1),
            default=0,
        )

        restored = 0
        for reference, source_cell in source_cells.items():
            row_number = int("".join(character for character in reference if character.isdigit()))
            if row_number > source_row_count or _column_index(reference) > source_column_count:
                continue
            source_value = _cell_value(source_cell, source_shared)
            if source_cell.get("t") == "s":
                text = source_value[1] if source_value is not None else ""
                output_cell = _ensure_output_cell(output_sheet, reference)
                _write_inline_text(output_cell, text)
                restored += 1
                continue
            output_value = _cell_value(output_cells.get(reference), output_shared)
            if source_value != output_value:
                output_cell = _ensure_output_cell(output_sheet, reference)
                _copy_value(source_cell, output_cell)
                restored += 1

        if conversion_rows:
            headers = {}
            for cell in output_sheet.xpath("./x:sheetData/x:row[@r='1']/x:c", namespaces=NS):
                value = _cell_value(cell, output_shared)
                if value and value[0] == "string":
                    headers[value[1]] = cell.get("r")[:-1]
            for row in conversion_rows:
                number = int(row["excelRow"])
                for field in CONVERSION_COLUMNS:
                    text = row.get(field)
                    if not isinstance(text, str) or not text:
                        continue
                    reference = f"{headers[field]}{number}"
                    cell = output_cells.get(reference)
                    if _cell_value(cell, output_shared) == ("string", text):
                        continue
                    repaired_conversion_cells[reference] = ("string", text)
                    if cell is None:
                        cell = _ensure_output_cell(output_sheet, reference)
                    _write_inline_text(cell, text)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output_path, "x") as rebuilt:
            for item in output_zip.infolist():
                data = (
                    etree.tostring(output_sheet, encoding="UTF-8", xml_declaration=True, standalone=True)
                    if item.filename == output_part
                    else output_zip.read(item.filename)
                )
                rebuilt.writestr(item, data)

    with zipfile.ZipFile(input_path, "r") as source_zip, zipfile.ZipFile(
        output_path, "r"
    ) as output_zip:
        source_sheet = etree.fromstring(source_zip.read(_sheet_part(source_zip, sheet_name)))
        output_sheet = etree.fromstring(output_zip.read(_sheet_part(output_zip, sheet_name)))
        source_cells = _cell_map(source_sheet)
        output_cells = _cell_map(output_sheet)
        source_shared = _shared_strings(source_zip)
        output_shared = _shared_strings(output_zip)
        mismatches = [
            reference
            for reference, cell in source_cells.items()
            if _cell_value(cell, source_shared) != _cell_value(output_cells.get(reference), output_shared)
        ]
        conversion_mismatches = [
            reference for reference, expected in repaired_conversion_cells.items()
            if _cell_value(output_cells.get(reference), output_shared) != expected
        ]
    if mismatches:
        raise ValueError(f"Source-cell restore failed at {len(mismatches)} cells: {mismatches[:20]}")
    if conversion_mismatches:
        raise ValueError(f"Conversion-cell restore failed: {conversion_mismatches[:20]}")
    return {
        "sourceRows": source_row_count,
        "sourceColumns": source_column_count,
        "sourceSharedStringCellsPreserved": restored,
        "sourceCellMismatches": 0,
        "conversionCellsRestored": len(repaired_conversion_cells),
    }


def main() -> None:
    if len(sys.argv) not in (4, 5):
        raise SystemExit("Usage: restore_source_cells.py <input.xlsx> <artifact-output.xlsx> <restored-output.xlsx> [conversion.json]")
    print(restore(*map(Path, sys.argv[1:])))


if __name__ == "__main__":
    main()
