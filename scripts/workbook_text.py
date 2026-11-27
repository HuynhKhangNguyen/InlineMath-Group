"""Read Excel text values from OOXML before a library partially decodes escapes."""

import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
ESCAPE = re.compile(r"_x([0-9a-f]{4})_", re.IGNORECASE)
ENCODE = re.compile(r"(?i:_x[0-9a-f]{4}_)|[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]")


def decode_xstring(raw):
    # Decode only once. _x005F_x000D_ is the literal text _x000D_.
    decoded = ESCAPE.sub(lambda match: chr(int(match[1], 16)), raw)
    if any(0xD800 <= ord(char) <= 0xDFFF for char in decoded):
        return decoded.encode("utf-16-le", "surrogatepass").decode("utf-16-le")
    return decoded


def encode_xstring(text):
    def escape(match):
        token = match[0]
        if token.startswith("_"):
            return "_x005F_" + token[1:]
        return f"_x{ord(token):04X}_"

    return ENCODE.sub(escape, text)


def visible_string(element):
    nodes = element.findall(NS + "t") + element.findall(NS + "r/" + NS + "t")
    return "".join(node.text or "" for node in nodes)


def saved_text_cells(path, worksheet_part):
    """Return decoded text for shared, inline and plain string cells by address."""
    with ZipFile(path) as archive:
        manifest = ET.fromstring(archive.read("[Content_Types].xml"))
        parts = [item.attrib["PartName"].lstrip("/") for item in manifest
                 if item.attrib.get("ContentType", "").endswith("sharedStrings+xml")]
        if len(parts) > 1:
            raise ValueError("Workbook has multiple shared-string tables.")
        strings = []
        if parts:
            with archive.open(parts[0]) as stream:
                for _, item in ET.iterparse(stream, events=("end",)):
                    if item.tag == NS + "si":
                        strings.append(decode_xstring(visible_string(item)))
                        item.clear()

        result = {}
        with archive.open(worksheet_part.lstrip("/")) as stream:
            for _, cell in ET.iterparse(stream, events=("end",)):
                if cell.tag != NS + "c":
                    continue
                kind, ref = cell.get("t"), cell.get("r")
                if cell.find(NS + "f") is None:
                    if kind == "s":
                        value = cell.findtext(NS + "v")
                        if value is None or not 0 <= int(value) < len(strings):
                            raise ValueError(f"Invalid shared-string reference at {ref}.")
                        result[ref] = strings[int(value)]
                    elif kind == "inlineStr":
                        inline = cell.find(NS + "is")
                        if inline is not None:
                            result[ref] = decode_xstring(visible_string(inline))
                    elif kind == "str":
                        result[ref] = decode_xstring(cell.findtext(NS + "v", ""))
                cell.clear()
        return result
