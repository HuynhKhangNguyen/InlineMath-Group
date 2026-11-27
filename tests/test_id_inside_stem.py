import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from lxml import html
from openpyxl import Workbook

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'src'))
sys.path.insert(0, str(PROJECT / 'scripts'))
from inline_math_grouping import convert_question_html, _question_stem, _question_xml_fragment
from validate_conversion import label_targets_inside_stem, valid_composite_label_context


class IdInsideStemTests(unittest.TestCase):
    def test_outer_table_row_is_not_used_as_context(self):
        source = ('<table><tr id="original-row"><td><div class="question-stem-content">'
                  'There are <div cid="a" ctype="InlineMath"></div> cats.</div></td></tr></table>')
        converted = convert_question_html(source, 'test')
        self.assertEqual(converted['processedInlineMath'], 1)
        root = html.fragment_fromstring(converted['convertedQuestionHtml'], create_parent='div')
        control = root.xpath('.//*[@cid="a"]')[0]
        target = root.xpath('.//*[@id=$id]', id=control.get('aria-labelledby'))[0]
        self.assertIs(_question_stem(target), _question_stem(control))
        self.assertNotEqual(target.get('id'), 'original-row')
        self.assertEqual(root.xpath('.//tr/@id'), ['original-row'])

    def test_whole_stem_gets_inner_wrapper_not_stem_id(self):
        source = ('<div class="question-stem-content">Enter the number in all.<br>'
                  '<img alt="" src="dots.png"><div cid="a" ctype="InlineMath"></div></div>')
        converted = convert_question_html(source, 'test')
        root = html.fragment_fromstring(converted['convertedQuestionHtml'], create_parent='div')
        stem = root.xpath('.//*[@class="question-stem-content"]')[0]
        self.assertIsNone(stem.get('id'))
        control = root.xpath('.//*[@cid="a"]')[0]
        self.assertTrue(control.get('aria-labelledby'))
        target = root.xpath('.//*[@id=$id]', id=control.get('aria-labelledby'))[0]
        self.assertIn(target, list(stem.iterdescendants()))

    def test_single_and_shared_targets_reject_stem_and_other_stems(self):
        root = html.fragment_fromstring(
            '<div><div class="question-stem-content" id="stem"><span id="heading">Count</span>'
            '<span id="local">Total <i cid="a" ctype="InlineMath"></i></span></div>'
            '<span id="outside">Outer</span><div class="question-stem-content">'
            '<span id="other">Other</span></div></div>')
        control = root.xpath('.//*[@cid="a"]')[0]
        target = lambda name: root.xpath('.//*[@id=$id]', id=name)[0]
        self.assertTrue(label_targets_inside_stem(control, [target('local')]))
        self.assertTrue(valid_composite_label_context(control, [target('heading'), target('local')]))
        for name in ['stem', 'outside', 'other']:
            self.assertFalse(label_targets_inside_stem(control, [target(name)]))
            self.assertFalse(valid_composite_label_context(control, [target(name), target('local')]))

    def test_validator_blocks_stem_target_and_outside_generated_id(self):
        source = ('<div id="source-outer"><div class="question-stem-content">'
                  'There are <div cid="a" ctype="InlineMath"></div> cats.</div></div>')
        result = convert_question_html(source, 'test')
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            workbook = Workbook()
            workbook.active.title = 'Data'
            workbook.active.append(['questionid', 'questionhtml'])
            workbook.active.append(['test', source])
            source_path = folder / 'synthetic.xlsx'
            workbook.save(source_path)
            root = html.fragment_fromstring(result['convertedQuestionHtml'], create_parent='div')
            stem = root.xpath('.//*[@class="question-stem-content"]')[0]
            stem.set('id', 'invalid-stem')
            root.xpath('.//*[@cid="a"]')[0].set('aria-labelledby', 'invalid-stem')
            root[0].set('id', 'new-outside')
            markup = ''.join(html.tostring(child, encoding='unicode') for child in root)
            row = {'excelRow': 2, 'questionId': 'test', 'convertedQuestionHtml': markup,
                   'convertedQuestionXml': _question_xml_fragment(markup), 'Type': result['type'],
                   'ContextType': result['contextType'], 'ErrorType': '',
                   'conversionNote': result['conversionNote'], 'groupingErrorInlineMath': 0,
                   'numberlineSkippedInlineMath': 0}
            payload = {'version': 'v1', 'sourceWorkbook': str(source_path), 'sourceSheet': 'Data',
                       'rows': [row], 'summary': {'groupingErrorInlineMath': 0, 'numberlineSkippedInlineMath': 0},
                       'contextTypeCounts': {result['contextType']: 1}, 'errorTypeCounts': {}}
            payload_path, report_path = folder / 'payload.json', folder / 'report.json'
            payload_path.write_text(json.dumps(payload), encoding='utf-8')
            completed = subprocess.run([sys.executable, str(PROJECT / 'scripts/validate_conversion.py'),
                                        str(payload_path), str(report_path), '--skip-known-baseline'],
                                       capture_output=True, text=True)
            self.assertTrue(report_path.exists(), completed.stderr)
            report = json.loads(report_path.read_text(encoding='utf-8'))
            self.assertEqual(report['status'], 'FAIL')
            self.assertGreater(report['structural']['generatedIdsOutsideStem'], 0)
            self.assertGreater(report['structural']['labelTargetsOutsideStem'], 0)


if __name__ == '__main__':
    unittest.main()
