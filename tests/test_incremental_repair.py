"""Exercise a corrupt Unchanged conversion without losing audit identity or manual edits."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import openpyxl

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'scripts'),
               str(Path(__file__).resolve().parents[1] / 'src')]
from convert_incremental import prepare
from inline_math_grouping import convert_question_html
from job_context import select_rows
from restore_incremental_workbook import restore
from verify_saved_workbook import verify
from workbook_contract import CONVERSION_COLUMNS, expected_summary, expected_review, sha256


class IncrementalRepairTests(unittest.TestCase):
    def fixture(self, directory):
        header = ['questionid', 'questionuid', 'questionhtml']
        def markup(name):
            return '<div class="question-stem-content">Enter the number of ' + name + '.<div ctype="InlineMath" cid="' + name + '"></div></div>'
        source = [[1, 'repair', markup('apples')], [2, 'retained', markup('pears')], [3, 'updated', markup('plums')]]
        old, new, baseline, audit_path = [directory / name for name in ('old.xlsx','new.xlsx','baseline.xlsx','audit.json')]
        for path, rows in ((old, source), (new, [*source[:2], [3, 'updated', markup('grapes')], [4, 'added', markup('oranges')]])):
            book = openpyxl.Workbook(); sheet = book.active; sheet.title = 'Data'
            sheet.append(header)
            for row in rows: sheet.append(row)
            book.save(path)
        book = openpyxl.load_workbook(old); sheet = book['Data']
        for col, label in enumerate([*CONVERSION_COLUMNS, 'review_note'], 4): sheet.cell(1,col,label)
        for n, row in enumerate(source,2):
            result = convert_question_html(row[2], row[0])
            values = [result['convertedQuestionHtml'],result['convertedQuestionXml'],result['type'],None,result['contextType'],result['conversionNote'],'manual edit']
            for col, value in enumerate(values,4): sheet.cell(n,col,value)
        sheet.cell(2,4,'<div>corrupt conversion with no inputs</div>')
        sheet.cell(3,9,'retained manual note')
        sheet.cell(3,5,'legacy stale XML retained verbatim')
        sheet.cell(3,4).font = openpyxl.styles.Font(bold=True, color='123456')
        for name in ('Conversion_Summary','Review_Queue'): book.create_sheet(name).append(['placeholder'])
        book.save(baseline)
        record = lambda uid, oldrow=None, newrow=None: dict(key=uid, **({'oldRow':oldrow} if oldrow else {}), **({'newRow':newrow} if newrow else {}))
        audit = {'validation':{'status':'PASS','keysCompleteAndUnique':True,'countsReconcile':True},'matching':{'primaryKey':'questionuid'},
                 'comparison':{'scope':'all-source-fields','fields':header},
                 'oldFile':{'kind':'input','path':str(old),'sheet':'Data','sha256':sha256(old)},
                 'newFile':{'kind':'input','path':str(new),'sheet':'Data','sha256':sha256(new)},
                 'counts':{'old':3,'new':4,'updated':1,'added':1,'deleted':0,'unchanged':2},
                 'updated':[record('updated',4,4)],'added':[record('added',None,5)],'deleted':[],
                 'unchanged':[record('repair',2,2),record('retained',3,3)]}
        audit_path.write_text(json.dumps(audit))
        return new, baseline, audit_path

    def test_scope_and_saved_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            directory = Path(d); new, baseline, audit = self.fixture(directory)
            with patch('convert_incremental.convert_question_html', wraps=convert_question_html) as engine:
                payload = prepare(new,baseline,audit,'v5',['repair'])
                self.assertEqual(engine.call_count,3)
            self.assertEqual(payload['incremental']['counts']['unchanged'],2)
            self.assertEqual(payload['incremental']['recomputedKeys'],['repair','updated','added'])
            self.assertEqual(payload['rows'][0]['dataChange'],'Unchanged')
            self.assertTrue(payload['rows'][0]['forceRecompute'])
            self.assertEqual(len(select_rows(payload)),3)
            path = directory/'payload.json'; path.write_text(json.dumps(payload))
            draft = directory/'draft.xlsx'; book = openpyxl.load_workbook(new)
            summary = book.create_sheet('Conversion_Summary'); summary.append(['title','v5']); summary.append(['Metric','Value'])
            for label,value in expected_summary(payload).items(): summary.append([label,value])
            for name in ('updated','added','deleted','unchanged'): summary.append([name.title()+' questions',payload['incremental']['counts'][name]])
            summary.append(['FIB_Numberline skips in Unchanged',0]); summary.append(['Additional repaired questions',1])
            queue = book.create_sheet('Review_Queue'); queue.append(['sourceRow','questionId','Type','ErrorType','ContextType','conversionNote'])
            for row in expected_review(payload): queue.append(row)
            book.save(draft)
            output = directory/'output.xlsx'; restore(new,draft,output,path)
            verification = verify(output,payload)
            self.assertEqual(verification['status'],'PASS')
            self.assertEqual(verification['retainedXmlMismatchRows'],[3])
            saved = openpyxl.load_workbook(output); before = openpyxl.load_workbook(baseline)
            self.assertEqual(saved['Data'].cell(3,4).value,before['Data'].cell(3,4).value)
            self.assertEqual(saved['Data'].cell(3,4).style_id,before['Data'].cell(3,4).style_id)
            self.assertEqual(saved['Data'].cell(3,9).value,'retained manual note')
            self.assertEqual(saved['Data'].cell(2,11).value,None)  # no synthetic review metadata
            saved.close(); before.close()
            # The exception cannot hide a new mismatch on a repaired question.
            payload['rows'][0]['convertedQuestionXml'] = 'new stale XML'
            path.write_text(json.dumps(payload))
            invalid = directory/'invalid.xlsx'; restore(new,draft,invalid,path)
            with self.assertRaisesRegex(ValueError,'converted XML differs'):
                verify(invalid,payload)

    def test_reject_unknown_duplicate_or_already_changed_key(self):
        with tempfile.TemporaryDirectory() as d:
            new,baseline,audit = self.fixture(Path(d))
            for keys in (['missing'],['repair','repair'],['updated'],['added']):
                with self.subTest(keys=keys), self.assertRaises(ValueError):
                    prepare(new,baseline,audit,'v5',keys)

    def test_no_implicit_repair(self):
        with tempfile.TemporaryDirectory() as d:
            new,baseline,audit = self.fixture(Path(d))
            with self.assertRaisesRegex(ValueError,'control-count mismatch'):
                prepare(new,baseline,audit,'v5')


if __name__ == '__main__':
    unittest.main()
