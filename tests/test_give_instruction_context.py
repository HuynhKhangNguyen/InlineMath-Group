import sys
import unittest
from pathlib import Path
from lxml import html

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from inline_math_grouping import convert_question_html

class GiveInstructionContextTests(unittest.TestCase):
    def context(self, source):
        result = convert_question_html(source, 'give_instruction')
        root = html.fragment_fromstring(result['convertedQuestionHtml'], create_parent='div')
        control = root.xpath('.//*[@cid="answer"]')[0]
        labels = control.get('aria-labelledby').split()
        self.assertEqual(len(labels), 1)
        group = root.xpath('.//*[@id=$value]', value=labels[0])[0]
        return result['contextType'], ''.join(group.itertext())

    def test_give_instruction_explains_bare_input(self):
        kind, text = self.context('<div class="question-stem-content">Give a multiple of 5 and 6.<br><br><div ctype="InlineMath" cid="answer"></div></div>')
        self.assertEqual(kind, 'Preceding Context Required')
        self.assertIn('Give a multiple of 5 and 6.', text)

    def test_complete_local_statement_stays_local(self):
        kind, text = self.context('<div class="question-stem-content">Give the number of cards.<br>He has <div ctype="InlineMath" cid="answer"></div> cards left.</div>')
        self.assertEqual(kind, 'Self-contained Input Context')
        self.assertNotIn('Give the', text)
