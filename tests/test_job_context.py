import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from job_context import checkpoint, packet, select_rows, status


class ContextTests(unittest.TestCase):
    def payload(self):
        return {'sourceValues': [['questionid', 'questionuid', 'questionhtml'],
                                 ['a', 'ua', '<div>Count <input ctype="InlineMath"></div>'],
                                 ['b', 'ub', '<div>' + 'long ' * 200 + '</div>'],
                                 ['c', 'uc', '<div>Numberline</div>']],
                'rows': [{'excelRow': n, 'questionId': q,
                          'convertedQuestionHtml': '<div>Count <input ctype="InlineMath" aria-labelledby="x"></div>',
                          'ContextType': 'Self-contained Input Context'}
                         for n, q in [(2, 'a'), (3, 'b'), (4, 'c')]]}

    def test_target_scope_does_not_review_unrelated_rows(self):
        data = self.payload()
        data['targetRowsOrIds'] = [2, 'b']
        self.assertEqual([r['excelRow'] for r in select_rows(data)], [2, 3])

    def test_unknown_and_ambiguous_scope_fail(self):
        data = self.payload()
        with self.assertRaises(ValueError):
            select_rows(data, [99])
        data['rows'][1]['questionId'] = 'a'
        with self.assertRaises(ValueError):
            select_rows(data, ['a'])

    def test_incremental_only_recomputed_not_retained_skip(self):
        data = self.payload()
        for row, change in zip(data['rows'], ['Updated', 'Unchanged', 'Unchanged']):
            row.update(dataChange=change, auditKey=row['questionId'])
        data['rows'][2]['enforceNumberlineSkip'] = True
        data['incremental'] = {'recomputedKeys': ['a']}
        self.assertEqual([r['excelRow'] for r in select_rows(data)], [2])
        data['incremental']['recomputedKeys'] = ['b']
        with self.assertRaises(ValueError):
            select_rows(data)

    def test_packets_keep_full_source_and_do_not_grant_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = root / 'payload.json'
            data = self.payload()
            payload.write_text(json.dumps(data), encoding='utf-8')
            result = packet(payload, root / 'packets', [3], 1)
            self.assertEqual(result['semanticValidation'], 'NOT_RUN')
            details = json.loads((root / 'packets' / 'batch-001.json').read_text(encoding='utf-8'))
            self.assertEqual(details[0]['sourceHtml'], data['sourceValues'][2][2])
            self.assertTrue(details[0]['previewTruncated'])
            self.assertEqual(payload.read_text(encoding='utf-8'), json.dumps(data))
            with self.assertRaises(FileExistsError):
                packet(payload, root / 'packets')

    def test_source_identity_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = root / 'payload.json'
            data = self.payload()
            data['rows'][0]['questionId'] = 'wrong'
            payload.write_text(json.dumps(data), encoding='utf-8')
            with self.assertRaises(ValueError):
                packet(payload, root / 'packets')
            self.assertFalse((root / 'packets').exists())

    def test_integral_excel_identifier_is_not_identity_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = self.payload()
            data['sourceValues'][1][0] = 123.0
            data['rows'][0]['questionId'] = '123'
            payload = root / 'payload.json'
            payload.write_text(json.dumps(data), encoding='utf-8')
            result = packet(payload, root / 'packets', [2], 1)
            self.assertEqual(result['selectedRows'], 1)

    def test_checkpoint_detects_stale_and_missing_dependencies(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact, state = root / 'input.txt', root / 'state.json'
            artifact.write_text('original', encoding='utf-8')
            result = checkpoint(state, 'job', 'prepared', {'input': artifact})
            self.assertEqual(result['evidenceStatus'], 'HASHES_MATCH')
            self.assertEqual(result['validation'], 'NOT_INFERRED')
            artifact.write_text('changed', encoding='utf-8')
            self.assertEqual(status(state)['changed'], ['input'])
            artifact.unlink()
            self.assertEqual(status(state)['missing'], ['input'])
            with self.assertRaises(ValueError):
                checkpoint(state, 'another-job', 'prepared', {})

    def test_duplicate_rows_and_empty_scope(self):
        data = self.payload()
        self.assertEqual(select_rows(data, []), [])
        data['rows'].append(data['rows'][0])
        with self.assertRaises(ValueError):
            select_rows(data)


if __name__ == '__main__':
    unittest.main()
