"""Merge the authored result into the baseline package without reserializing retained cells."""

import copy
import json
import re
import sys
import zipfile
from pathlib import Path

from lxml import etree
from openpyxl.utils.cell import get_column_letter

from restore_source_cells import _cell_value, _column_index, _shared_strings, _sheet_part, _write_inline_text
from workbook_contract import CONVERSION_COLUMNS, data_rows, sha256

X = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REPORTS = ("Conversion_Summary", "Review_Queue")


def read_sheet(archive, name):
    return etree.fromstring(archive.read(_sheet_part(archive, name)))


def row_map(sheet):
    return {int(row.get("r")): row for row in sheet.find(X + "sheetData")}


def cell_map(row):
    return {_column_index(cell.get("r")): cell for cell in row} if row is not None else {}


def letters(number):
    return get_column_letter(number)


def write_cell(row, column, value, style=None):
    if value is None and not style:
        return
    address = f"{letters(column)}{row.get('r')}"
    cell = etree.SubElement(row, X + "c", r=address)
    if style is not None:
        cell.set("s", style)
    if isinstance(value, str):
        _write_inline_text(cell, value)
    elif value is not None:
        if isinstance(value, bool):
            cell.set("t", "b")
        etree.SubElement(cell, X + "v").text = str(int(value) if isinstance(value, bool) else value)


def transplant_cell(row, col, cell, style, shared=None):
    output = copy.deepcopy(cell)
    output.set("r", f"{letters(col)}{row.get('r')}")
    output.attrib.pop("s", None)
    if style is not None:
        output.set("s", style)
    if output.get("t") == "s" and shared is not None:
        _write_inline_text(output, _cell_value(cell, shared)[1])
    row.append(output)


def style_at(cells, column):
    return cells[column].get("s") if column in cells else None


def clean_new_row(row, number, width, clear_old_filter=False):
    element = etree.Element(X + "row", attrib=dict(row.attrib) if row is not None else {})
    element.set("r", str(number))
    element.set("spans", f"1:{width}")
    if clear_old_filter:
        element.attrib.pop("hidden", None)
    return element


def set_range(sheet, width, height, auto_filter=False):
    area = f"A1:{letters(width)}{height}"
    dimension = sheet.find(X + "dimension")
    if dimension is not None:
        dimension.set("ref", area)
    filter_node = sheet.find(X + "autoFilter")
    if auto_filter and filter_node is None:
        data = sheet.find(X + "sheetData")
        filter_node = etree.Element(X + "autoFilter")
        data.addnext(filter_node)
    if filter_node is not None:
        filter_node.set("ref", area)
        for condition in list(filter_node):
            filter_node.remove(condition)
    if auto_filter:
        settings = sheet.find(X + "sheetPr")
        if settings is not None:
            settings.attrib.pop("filterMode", None)
    return area


def merge_data(base, new, payload, baseline_header):
    sheet = read_sheet(base, "Data")
    source = read_sheet(new, payload["sourceSheet"])
    state, old_rows, new_rows = payload["incremental"], row_map(sheet), row_map(source)
    new_header = payload["sourceValues"][0]
    generated = [*CONVERSION_COLUMNS, *state["extraHeaders"]]
    old_columns = {name.strip().lower(): i for i, name in enumerate(baseline_header, 1)}
    old_width = len(baseline_header)
    headings = [*new_header, *generated]
    indices = [old_columns.get(name.strip().lower()) for name in headings]
    width = len(headings)
    old_filter = sheet.find(X + "autoFilter")
    clear_hidden = old_filter is not None and bool(len(old_filter))
    existing = sheet.find(X + "sheetData")
    old_shape = (len(old_rows), old_width)
    new_shape = (len(payload["rows"]) + 1, width)
    moves_rows = any(r.get("baselineRow") != r["excelRow"] for r in payload["rows"])
    moves_columns = any(old is not None and old != i for i, old in enumerate(indices, 1))
    if moves_rows or moves_columns or old_shape != new_shape:
        if any(sheet.find(X + name) is not None for name in (
            "tableParts", "mergeCells", "dataValidations", "conditionalFormatting", "hyperlinks"
        )):
            raise ValueError("Data contains range-dependent Excel features that need explicit remapping.")
    for row in list(existing):
        existing.remove(row)
    template = old_rows.get(2)
    old_header_cells = cell_map(old_rows[1])
    header_style = style_at(old_header_cells, old_columns["conversionnote"])
    header = clean_new_row(old_rows[1], 1, width)
    for column, name, old_index in zip(range(1, width + 1), headings, indices):
        write_cell(header, column, name, style_at(old_header_cells, old_index) if old_index else header_style)
    existing.append(header)
    old_style_widths = {}
    cols = sheet.find(X + "cols")
    if cols is not None:
        for definition in cols:
            for index in range(int(definition.get("min")), min(int(definition.get("max")), old_width) + 1):
                old_style_widths[index] = definition
    if moves_columns or width != old_width:
        if cols is None:
            cols = etree.Element(X + "cols")
            existing.addprevious(cols)
        for item in list(cols):
            cols.remove(item)
        for i, prior in enumerate(indices, 1):
            if prior in old_style_widths:
                col = copy.deepcopy(old_style_widths[prior])
                col.set("min", str(i))
                col.set("max", str(i))
                cols.append(col)
            elif headings[i - 1].strip().lower() == "data_change":
                etree.SubElement(cols, X + "col", min=str(i), max=str(i), width="18", customWidth="1")
    source_shared = _shared_strings(new)
    status_columns = {
        i: label.strip().lower() for i, label in enumerate(headings, 1)
        if label.strip().lower() in {"data_change", "review_status", "review_note"}
    }
    for record in payload["rows"]:
        n = record["excelRow"]
        prior = old_rows.get(record["baselineRow"])
        row = clean_new_row(prior if prior is not None else template, n, width, clear_hidden)
        styles = cell_map(prior if prior is not None else template)
        base_cells, source_cells = cell_map(prior), cell_map(new_rows[n])
        output_values = [*(record[name] for name in CONVERSION_COLUMNS), *record["extraValues"]]
        unchanged = record["dataChange"] == "Unchanged"
        skip = record.get("enforceNumberlineSkip") or record.get("forceRecompute")
        for column, old_index in enumerate(indices, 1):
            style = style_at(styles, old_index)
            field = status_columns.get(column)
            preserve_baseline = unchanged and field != "data_change" and (
                not skip or (column > len(new_header) + len(CONVERSION_COLUMNS)
                             and field not in {"review_status", "review_note"})
            )
            if preserve_baseline:
                if old_index in base_cells:
                    cell = base_cells[old_index]
                    if cell.find(X + "f") is not None and (n != record["baselineRow"] or column != old_index):
                        raise ValueError(f"Moving retained formula {cell.get('r')} would change its references.")
                    transplant_cell(row, column, cell, style)
            elif column <= len(new_header):
                if column in source_cells:
                    transplant_cell(row, column, source_cells[column], style, source_shared)
            else:
                write_cell(row, column, output_values[column - len(new_header) - 1], style)
        existing.append(row)
    set_range(sheet, width, len(payload["rows"]) + 1, auto_filter=True)
    return sheet, width


def merge_report(base, draft, name, payload):
    sheet, authored = read_sheet(base, name), read_sheet(draft, name)
    past, current = row_map(sheet), row_map(authored)
    generated_width = 3 if name == "Conversion_Summary" else 6
    base_shared = _shared_strings(base)
    custom_columns = {}
    review_rows_by_source = {}
    if name == "Review_Queue":
        for column, cell in cell_map(past[1]).items():
            value = _cell_value(cell, base_shared)
            if column > generated_width and value and value[0] == "string":
                custom_columns[column] = value[1].strip().lower()
        for n, row in past.items():
            value = _cell_value(cell_map(row).get(1), base_shared)
            if n != 1 and value and value[0] == "number":
                review_rows_by_source[int(value[1])] = row
    width = max(generated_width, *custom_columns) if custom_columns else generated_width
    data = sheet.find(X + "sheetData")
    for row in list(data):
        data.remove(row)
    shared = _shared_strings(draft)
    conversion_rows = {row["excelRow"]: row for row in payload["rows"]}
    for n, row in current.items():
        template = past.get(n, past.get(3 if name == "Conversion_Summary" else 2, past[1]))
        output = clean_new_row(template, n, width)
        styles = cell_map(template)
        for column, cell in cell_map(row).items():
            if column <= generated_width:
                transplant_cell(output, column, cell, style_at(styles, column), shared)
        if custom_columns:
            record = conversion_rows[int(_cell_value(cell_map(row)[1], shared)[1])] if n != 1 else None
            original = past[1] if record is None else review_rows_by_source.get(record["baselineRow"])
            original_cells = cell_map(original)
            for column, label in custom_columns.items():
                if record is not None and (record["dataChange"] != "Unchanged" or record.get("enforceNumberlineSkip") or record.get("forceRecompute")) and label in {
                    "review_status", "review_note",
                }:
                    value = None
                    if record["ContextType"] == "Skipped/FIB_Numberline":
                        value = "Skip" if label == "review_status" else record["conversionNote"]
                    write_cell(output, column, value, style_at(styles, column))
                elif column in original_cells:
                    cell = original_cells[column]
                    transplant_cell(output, column, cell, cell.get("s"))
        data.append(output)
    set_range(sheet, width, max(current))
    return sheet


def restore(input_path, draft_path, output_path, payload_path):
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    state = payload["incremental"]
    baseline = Path(state["files"]["baseline"])
    for key, file in state["files"].items():
        if sha256(file) != state["hashes"][key]:
            raise ValueError(f"{key} changed after preparing the payload.")
    if sha256(input_path) != state["hashes"]["newInput"]:
        raise ValueError("The builder input does not match the audited input.")
    baseline_header, _ = data_rows(baseline)
    with zipfile.ZipFile(baseline) as base, zipfile.ZipFile(input_path) as new, zipfile.ZipFile(draft_path) as draft:
        data, width = merge_data(base, new, payload, baseline_header)
        replacement = {_sheet_part(base, "Data"): data}
        for name in REPORTS:
            replacement[_sheet_part(base, name)] = merge_report(base, draft, name, payload)
        workbook = etree.fromstring(base.read("xl/workbook.xml"))
        for defined in workbook.findall(f"{X}definedNames/{X}definedName"):
            if defined.get("name") == "_xlnm._FilterDatabase" and re.match(r"^'?Data'?!", defined.text or ""):
                defined.text = f"Data!$A$1:${letters(width)}${len(payload['rows']) + 1}"
        replacement["xl/workbook.xml"] = workbook
        with zipfile.ZipFile(output_path, "x") as out:
            for part in base.infolist():
                tree = replacement.get(part.filename)
                content = base.read(part.filename) if tree is None else etree.tostring(
                    tree, encoding="UTF-8", xml_declaration=True, standalone=True
                )
                out.writestr(part, content)


if __name__ == "__main__":
    restore(*map(Path, sys.argv[1:]))
