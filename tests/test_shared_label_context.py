import sys
import unittest
from pathlib import Path

from lxml import html

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from validate_conversion import valid_composite_label_context


class SharedLabelContextTests(unittest.TestCase):
    def test_heading_and_column_image_can_label_separate_local_answers(self):
        root = html.fragment_fromstring(
            '<div class="question-stem-content"><span id="task">Count each group.</span>'
            '<img id="stars" alt="stars"><img id="suns" alt="suns">'
            '<div id="first"><div cid="a" ctype="InlineMath"></div></div>'
            '<div id="second"><div cid="b" ctype="InlineMath"></div></div></div>'
        )
        by_id = {element.get("id"): element for element in root.xpath(".//*[@id]")}
        controls = root.xpath(".//*[@ctype='InlineMath']")
        self.assertTrue(valid_composite_label_context(controls[0], [by_id["task"], by_id["stars"], by_id["first"]]))
        self.assertTrue(valid_composite_label_context(controls[1], [by_id["task"], by_id["suns"], by_id["second"]]))
        self.assertFalse(valid_composite_label_context(controls[1], [by_id["task"], by_id["first"]]))

    def test_shared_context_cannot_cross_a_part_boundary(self):
        root = html.fragment_fromstring(
            '<div class="question-stem-content"><span class="part_label">A</span>'
            '<span id="task">Count each group.</span><span class="part_label">B</span>'
            '<div id="local"><div ctype="InlineMath"></div></div></div>'
        )
        control = root.xpath(".//*[@ctype='InlineMath']")[0]
        targets = [root.xpath(".//*[@id=$id]", id=name)[0] for name in ("task", "local")]
        self.assertFalse(valid_composite_label_context(control, targets))

    def test_shared_context_cannot_contain_another_answer(self):
        root = html.fragment_fromstring(
            '<div class="question-stem-content"><div id="shared">Count '
            '<div ctype="InlineMath"></div></div>'
            '<div id="local"><div cid="answer" ctype="InlineMath"></div></div></div>'
        )
        control = root.xpath(".//*[@cid='answer']")[0]
        targets = [root.xpath(".//*[@id=$id]", id=name)[0] for name in ("shared", "local")]
        self.assertFalse(valid_composite_label_context(control, targets))
