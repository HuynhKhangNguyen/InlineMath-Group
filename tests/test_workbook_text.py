import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from workbook_text import decode_xstring, encode_xstring, saved_text_cells


class ExcelTextTests(unittest.TestCase):
    def test_encoded_newline_and_literal_survive_round_trip(self):
        self.assertEqual(decode_xstring("_x000D_\n_x005F_x000D_"), "\r\n_x000D_")
        for text in ("line 1\r\nline 2", "_x000D_", "_x005F_", "a\x01b"):
            self.assertEqual(decode_xstring(encode_xstring(text)), text)

    def test_reads_shared_and_inline_cells_from_raw_xml(self):
        ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        with TemporaryDirectory() as folder:
            path = Path(folder) / "fixture.xlsx"
            with ZipFile(path, "w") as book:
                book.writestr("[Content_Types].xml",
                              '<Types><Override PartName="/xl/sharedStrings.xml" '
                              'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
                              '</Types>')
                book.writestr("xl/sharedStrings.xml",
                              f'<sst xmlns="{ns}"><si><t>First_x000D_Second</t></si></sst>')
                book.writestr("xl/worksheets/sheet1.xml",
                              f'<worksheet xmlns="{ns}"><sheetData><row r="1">'
                              '<c r="A1" t="s"><v>0</v></c>'
                              '<c r="B1" t="inlineStr"><is><t>Literal _x005F_x000D_</t></is></c>'
                              '</row></sheetData></worksheet>')
            self.assertEqual(saved_text_cells(path, "xl/worksheets/sheet1.xml"),
                             {"A1": "First\rSecond", "B1": "Literal _x000D_"})


if __name__ == "__main__":
    unittest.main()
