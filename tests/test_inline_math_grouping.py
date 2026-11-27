import sys
import unittest
from pathlib import Path
from xml.etree import ElementTree
from lxml import html as lxml_html

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from inline_math_grouping import (
    _local_sentence_start,
    _question_sentence_start,
    _semantic_sentences,
    _semantic_split_offset,
    convert_question_html,
    group_inline_math,
    normalize_html_class_attributes,
    parse_question_xml,
)


class InlineMathGroupingTests(unittest.TestCase):
    def test_count_context_spans_an_image_with_empty_alternative(self):
        source = (
            '<div class="question-stem-content">Count the dots on the domino.<br><br>'
            '<img alt="" src="domino.png"><br><br>'
            '<div cid="answer" ctype="InlineMath"></div></div>'
        )
        result = convert_question_html(source, "q1")
        self.assertEqual(result["groupingErrorInlineMath"], 0)
        self.assertEqual(result["processedInlineMath"], 1)
        self.assertEqual(result["contextType"], "Preceding Context Required")
        self.assertIn("Count the dots on the domino.", self._accessible_label(result["convertedQuestionHtml"], "answer"))
        root = lxml_html.fragment_fromstring(result["convertedQuestionHtml"], create_parent="div")
        control = root.xpath(".//*[@cid='answer']")[0]
        target = root.xpath(".//*[@id=$id]", id=control.get("aria-labelledby"))[0]
        self.assertEqual(len(target.xpath(".//img")), 1)

    def test_two_time_offsets_keep_separate_complete_contexts(self):
        source = (
            '<div class="question-stem-content">One hour after 2 o’clock<br>'
            '<div cid="first" ctype="InlineMath"></div> o’clock<br><br>'
            'Two hours after 9 o’clock<br>'
            '<div cid="second" ctype="InlineMath"></div> o’clock</div>'
        )
        result = convert_question_html(source, "q1")
        self.assertEqual(result["processedGroups"], 2)
        first = self._accessible_label(result["convertedQuestionHtml"], "first")
        second = self._accessible_label(result["convertedQuestionHtml"], "second")
        self.assertIn("One hour after 2", first)
        self.assertNotIn("Two hours", first)
        self.assertIn("Two hours after 9", second)
        self.assertNotIn("One hour", second)

    def test_classname_layout_is_normalized_before_grouping(self):
        source = (
            '<div className="question-stem-content">He has '
            '<div cid="answer" ctype="InlineMath" className="answer-box"></div> cards left.</div>'
        )
        result = convert_question_html(source, "q1")
        root = lxml_html.fragment_fromstring(result["convertedQuestionHtml"], create_parent="div")
        self.assertEqual(result["processedInlineMath"], 1)
        self.assertEqual(result["outsideLayout"], 0)
        self.assertFalse(root.xpath(".//*[@classname]"))
        self.assertEqual(root.xpath(".//*[@cid='answer']")[0].get("class"), "answer-box")
        self.assertIn("cards left.", self._accessible_label(result["convertedQuestionHtml"], "answer"))

    def test_classname_normalization_merges_class_tokens_and_is_idempotent(self):
        source = '<p class="one shared" CLASSNAME="shared two">Text</p>'
        normalized = normalize_html_class_attributes(source)
        root = lxml_html.fragment_fromstring(normalized, create_parent="div")
        self.assertEqual(root[0].get("class"), "one shared two")
        self.assertEqual(normalize_html_class_attributes(normalized), normalized)

    def test_classname_mentions_and_other_attribute_values_are_preserved(self):
        source = (
            '<!-- className="comment" --><p data-example=\'className="value"\'>'
            'className="text"</p><script>const className = "code";</script>'
        )
        self.assertEqual(normalize_html_class_attributes(source), source)
        normalized = normalize_html_class_attributes(source + '<p className="real">Text</p>')
        self.assertIn('className="comment"', normalized)
        self.assertIn('className="text"', normalized)
        root = lxml_html.fragment_fromstring(normalized, create_parent="div")
        self.assertEqual(root.xpath(".//p[@data-example]")[0].get("data-example"), 'className="value"')
        self.assertEqual(root.xpath(".//script")[0].text, 'const className = "code";')
        self.assertFalse(root.xpath(".//*[@classname]"))

    def test_classname_on_protected_table_is_respected(self):
        source = (
            '<div className="question-stem-content"><table className="verticalEquation">'
            '<tr><td><div cid="answer" ctype="InlineMath"></div></td></tr></table></div>'
        )
        result = convert_question_html(source, "q1")
        self.assertEqual(result["protectedInlineMath"], 1)
        self.assertEqual(result["processedInlineMath"], 0)
        self.assertNotIn("aria-labelledby", result["convertedQuestionHtml"])
        self.assertNotIn("classname=", result["convertedQuestionHtml"].lower())

    def test_numberline_skip_normalizes_classname_without_grouping(self):
        source = (
            '<div className="question-stem-content"><div ctype="FIB_Numberline"></div>'
            '<div cid="answer" ctype="InlineMath" aria-label="source name"></div></div>'
        )
        result = convert_question_html(source, "q1")
        self.assertEqual(result["contextType"], "Skipped/FIB_Numberline")
        self.assertEqual(result["numberlineSkippedInlineMath"], 1)
        self.assertEqual(result["processedInlineMath"], 0)
        self.assertNotIn("aria-labelledby", result["convertedQuestionHtml"])
        self.assertEqual(result["convertedQuestionHtml"], normalize_html_class_attributes(source))
        self.assertEqual(ElementTree.fromstring(result["convertedQuestionXml"]).text, result["convertedQuestionHtml"])

    def _accessible_label(self, converted_html, cid):
        root = lxml_html.fragment_fromstring(converted_html, create_parent="div")
        control = root.xpath(".//*[@cid=$cid]", cid=cid)[0]
        targets = [root.xpath(".//*[@id=$id]", id=ref)[0] for ref in control.get("aria-labelledby", "").split()]
        return " ".join(" ".join(target.itertext()) for target in targets)

    def test_groups_by_qname_and_preserves_order(self):
        source = """
        <div class="question-stem-content">
          8 &divide; 4 = <div cid="answer-1" ctype="InlineMath" qname="a1"></div>
          <br>OR 8 &divide; 2 = <div cid="answer-2" ctype="InlineMath" qname="a1"></div>
        </div>
        """
        result = group_inline_math(source, 123.0)
        self.assertEqual(result["questionId"], "123")
        self.assertEqual(result["topLevelCount"], 2)
        self.assertEqual(len(result["groups"]), 1)
        self.assertEqual([item["index"] for item in result["groups"][0]["items"]], [1, 2])
        self.assertEqual(result["groups"][0]["items"][1]["text"], "OR 8 ÷ 2 =")

    def test_preceding_declarative_fact_supplies_missing_context(self):
        source = (
            '<div class="question-stem-content">Mai has 6 blue shells.<br>'
            '<div cid="shells" ctype="InlineMath"></div> blue shells</div>'
        )
        result = convert_question_html(source, "q1")
        self.assertEqual(result["contextType"], "Preceding Context Required")
        self.assertIn("Mai has 6 blue shells.", self._accessible_label(result["convertedQuestionHtml"], "shells"))

    def test_number_in_all_sibling_instruction_is_used(self):
        source = (
            '<div class="question-stem-content">Color the part that is joined.<br>\r\n'
            '<div>Enter the number in all.</div>\r\n<br>\r\n'
            '<div cid="total" ctype="InlineMath"></div></div>'
        )
        result = convert_question_html(source, "q1")
        self.assertEqual(result["errorType"], "")
        label = self._accessible_label(result["convertedQuestionHtml"], "total")
        self.assertIn("Enter the number in all.", label)
        self.assertNotIn("Color the part", label)

    def test_excludes_inline_math_nested_in_any_ctype(self):
        source = """
        <div>
          <div ctype="InlineMath" cid="outer" qname="a1">
            <div ctype="InlineMath" cid="inner" qname="a1"></div>
          </div>
        </div>
        """
        result = group_inline_math(source, "q1")
        self.assertEqual(result["topLevelCount"], 1)
        self.assertEqual(result["nestedExcludedCount"], 1)
        self.assertIn('cid="outer"', result["groups"][0]["items"][0]["html"])

    def test_uses_gid_and_source_index_when_present(self):
        source = """
        <div>
          First <div ctype="InlineMath" gid="g1" index="2" qname="a1"></div>
          Second <div ctype="InlineMath" gid="g1" index="4" qname="a1"></div>
        </div>
        """
        result = group_inline_math(source, "q1")
        self.assertEqual(result["groups"][0]["gid"], "g1")
        self.assertEqual([item["index"] for item in result["groups"][0]["items"]], [2, 4])

    def test_decodes_question_payload_once(self):
        xml = "<root><question>&lt;div&gt;Tom &amp;amp; Ana&lt;/div&gt;</question></root>"
        self.assertEqual(parse_question_xml(xml), "<div>Tom & Ana</div>")

    def test_skips_the_entire_question_with_a_fib_numberline(self):
        template = (
            '<div class="question-stem-content">Count &amp; fill.'
            '<div id="existing" {attribute}=" fib_NUMBERLINE ">'
            '<div ctype="InlineMath" aria-labelledby="existing">'
            '<div itype="InlineMath"></div></div></div>'
            '<div ctype="InlineMath"></div></div>\n'
        )
        for attribute in ("ctype", "itype"):
            with self.subTest(attribute=attribute):
                source = template.format(attribute=attribute)
                result = convert_question_html(source, "q1")
                self.assertEqual(result["convertedQuestionHtml"], source)
                self.assertEqual(ElementTree.fromstring(result["convertedQuestionXml"]).text, source)
                self.assertEqual(result["type"], "Skipped/FIB_Numberline")
                self.assertEqual(result["contextType"], result["type"])
                self.assertEqual(result["errorType"], "")
                self.assertTrue(result["conversionNote"].startswith("Skip: FIB_Numberline."))
                self.assertEqual(result["sourceInlineMath"], 3)
                self.assertEqual(result["numberlineSkippedInlineMath"], 3)
                for key in ("processableInlineMath", "processedInlineMath", "processedGroups",
                            "protectedInlineMath", "nestedExcluded", "groupingErrorInlineMath"):
                    self.assertEqual(result[key], 0, key)
                self.assertEqual(result["labelIds"], [])

    def test_numberline_widget_without_inlinemath_still_marks_the_row(self):
        source = '<div ctype="FIB_Numberline"></div>'
        result = convert_question_html(source, "q1")
        self.assertEqual(result["contextType"], "Skipped/FIB_Numberline")
        self.assertEqual(result["convertedQuestionHtml"], source)
        self.assertEqual(result["numberlineSkippedInlineMath"], 0)

    def test_numberline_mentions_do_not_skip_inline_math(self):
        source = (
            '<!-- <div ctype="FIB_Numberline"></div> -->'
            '<div class="question-stem-content" data-name="FIB_Numberline">'
            'FIB_Numberline<br>He has <div cid="a" ctype="InlineMath"></div> cards left.</div>'
        )
        result = convert_question_html(source, "q1")
        self.assertEqual(result["numberlineSkippedInlineMath"], 0)
        self.assertEqual(result["processedInlineMath"], 1)
        self.assertIn('aria-labelledby="a_label_1"', result["convertedQuestionHtml"])

    def test_v1_includes_question_and_unit_in_label_context(self):
        source = '<div class="question-stem-content">How long is the ribbon?<br><div cid="a" ctype="InlineMath"></div> centimeters</div>'
        result = convert_question_html(source, "q1")
        self.assertIn('id="a_label_1"', result["convertedQuestionHtml"])
        self.assertIn('aria-labelledby="a_label_1"', result["convertedQuestionHtml"])
        self.assertIn("How long is the ribbon?", result["convertedQuestionHtml"])
        self.assertIn("centimeters", result["convertedQuestionHtml"])
        self.assertEqual(result["contextType"], "Preceding Context Required")

    def test_complete_input_sentence_does_not_include_previous_question(self):
        source = '<div class="question-stem-content">How many cards remain?<br><br>He has <div cid="a" ctype="InlineMath"></div> cards left.</div>'
        result = convert_question_html(source, "q1")
        converted = result["convertedQuestionHtml"]
        label_start = converted.index('id="a_label_1"')
        self.assertNotIn("How many cards remain?", converted[label_start:])
        self.assertIn("He has", converted[label_start:])
        self.assertEqual(result["contextType"], "Self-contained Input Context")

    def test_regular_past_tense_answer_does_not_include_rephrased_question(self):
        source = '<div class="question-stem-content">How many miles did Dan jog last week?<br><br>Dan jogged <div cid="a" ctype="InlineMath"></div> miles last week.</div>'
        result = convert_question_html(source, "q1")
        converted = result["convertedQuestionHtml"]
        label_start = converted.index('id="a_label_1"')
        self.assertNotIn("How many miles did Dan jog last week?", converted[label_start:])
        self.assertIn("Dan jogged", converted[label_start:])
        self.assertEqual(result["contextType"], "Self-contained Input Context")

    def test_present_tense_answer_does_not_include_rephrased_question(self):
        source = '<div class="question-stem-content">How many flasks are ordered?<br><br>The science teacher orders <div cid="a" ctype="InlineMath"></div> flasks.</div>'
        result = convert_question_html(source, "q1")
        self.assertEqual(result["contextType"], "Self-contained Input Context")

    def test_value_led_declarative_answer_is_self_contained(self):
        source = '<div class="question-stem-content">How many students chose dove?<br><br><div cid="a" ctype="InlineMath"></div> students chose dove.</div>'
        result = convert_question_html(source, "q1")
        self.assertEqual(result["contextType"], "Self-contained Input Context")

    def test_result_label_includes_nearest_calculation_source_only(self):
        source = '<div class="question-stem-content">Solve the problem.<br>Use the correct operation.<br><span class="math-tex">24 ÷ 6</span><br><br>Quotient:<div cid="a" ctype="InlineMath"></div></div>'
        result = convert_question_html(source, "q1")
        converted = result["convertedQuestionHtml"]
        label_start = converted.index('id="a_label_1"')
        label = converted[label_start:]
        self.assertIn("24 ÷ 6", label)
        self.assertIn("Quotient:", label)
        self.assertNotIn("Solve the problem", label)
        self.assertNotIn("Use the correct operation", label)
        self.assertEqual(result["contextType"], "Preceding Context Required")

    def test_result_label_finds_calculation_in_a_sibling_dom_block(self):
        source = '<div class="question-stem-content"><div class="equation">24 ÷ 6</div><div class="answer"><span>Quotient:</span><div cid="a" ctype="InlineMath"></div></div></div>'
        result = convert_question_html(source, "q1")
        converted = result["convertedQuestionHtml"]
        label_start = converted.index('id="a_label_1"')
        self.assertIn("24 ÷ 6", converted[label_start:])
        self.assertIn("Quotient:", converted[label_start:])
        self.assertEqual(result["contextType"], "Preceding Context Required")

    def test_calculation_source_and_exact_input_use_one_contiguous_dom_range(self):
        source = '<div class="question-stem-content">37 + 16<br><br>Estimate:<div cid="estimate" ctype="MultipleChoice" subtype="MC"><div itemid="a">about 50</div><div itemid="b">about 60</div></div><br><br>Exact:<div cid="exact" ctype="InlineMath"></div></div>'
        result = convert_question_html(source, "q1")
        root = result["convertedQuestionHtml"]
        self.assertIn("37 + 16", root)
        self.assertIn("Exact:", root)
        label = self._accessible_label(root, "exact")
        self.assertIn("37 + 16", label)
        self.assertIn("about 50", label)
        self.assertIn("Exact:", label)
        self.assertNotIn("_part_", root)
        self.assertIn('aria-labelledby="exact_label_1"', root)
        self.assertEqual(result["contextType"], "Preceding Context Required")

    def test_multiple_choice_options_are_not_treated_as_calculation_source(self):
        source = '<div class="question-stem-content">There are six hundred four residents.<div cid="mc" ctype="MultipleChoice"><div itemid="a">6000 + 4</div><div itemid="b">600 + 4</div></div><br>Standard form: <div cid="answer" ctype="InlineMath"></div></div>'
        result = convert_question_html(source, "q1")
        root = result["convertedQuestionHtml"]
        label = self._accessible_label(root, "answer")
        self.assertEqual(label.strip(), "Standard form:")
        self.assertEqual(result["contextType"], "Manual Review")

    def test_local_context_stops_before_following_choice_widget(self):
        source = '<div class="question-stem-content">What is the number in standard and word form?<br><br>Standard form: <div cid="answer" ctype="InlineMath"></div><div cid="choices" ctype="MultipleChoice"><div itemid="a">seven thousand</div><div itemid="b">seventy thousand</div></div></div>'
        result = convert_question_html(source, "q1")
        label = self._accessible_label(result["convertedQuestionHtml"], "answer")
        self.assertEqual(label.strip(), "Standard form:")
        self.assertNotIn("seven thousand", label)
        self.assertEqual(result["contextType"], "Manual Review")

    def test_calculation_source_and_input_use_one_contiguous_dom_range(self):
        source = '<div class="question-stem-content">Layla has 3 dimes.<br>3 × 10¢ = 30¢; 30¢ ÷ 5¢ = 6; Layla can buy 6 cards.<br><br>The number of cards she can buy is <div cid="answer" ctype="InlineMath"></div></div>'
        result = convert_question_html(source, "q1")
        root = result["convertedQuestionHtml"]
        label = self._accessible_label(root, "answer")
        self.assertIn("3 × 10¢ = 30¢; 30¢ ÷ 5¢ = 6", label)
        self.assertIn("The number of cards she can buy is", label)
        self.assertIn("Layla can buy 6 cards", label)
        self.assertNotIn("_part_", root)
        self.assertEqual(result["contextType"], "Preceding Context Required")

    def test_result_label_with_no_calculation_source_is_manual_review(self):
        source = '<div class="question-stem-content">Quotient: <div cid="a" ctype="InlineMath"></div></div>'
        result = convert_question_html(source, "q1")
        self.assertEqual(result["contextType"], "Manual Review")

    def test_empty_label_group_is_reported_as_grouping_error_and_left_unchanged(self):
        source = '<div class="question-stem-content"><span class="part_label">Part B</span><br><br><div cid="banana" ctype="InlineMath" numberonly="true"></div></div>'
        result = convert_question_html(source, "q1")
        root = lxml_html.fragment_fromstring(result["convertedQuestionHtml"], create_parent="div")
        control = root.xpath('.//*[@cid="banana"]')[0]

        self.assertEqual(result["errorType"], "Grouping Error")
        self.assertEqual(result["groupingErrorInlineMath"], 1)
        self.assertEqual(result["processedInlineMath"], 0)
        self.assertEqual(result["processedGroups"], 0)
        self.assertNotIn("aria-labelledby", control.attrib)
        self.assertNotIn("banana_label", result["convertedQuestionHtml"])
        self.assertEqual(result["convertedQuestionHtml"], source)
        self.assertEqual(dict(control.attrib), {"cid": "banana", "ctype": "InlineMath", "numberonly": "true"})

    def test_grouping_error_does_not_cancel_valid_groups_in_same_question(self):
        source = '<div class="question-stem-content">He has <span cid="good" ctype="InlineMath"></span> cards left.<br><br><span cid="bad" ctype="InlineMath"></span><img alt="" src="pattern.svg"></div>'
        result = convert_question_html(source, "q1")
        root = lxml_html.fragment_fromstring(result["convertedQuestionHtml"], create_parent="div")
        good = root.xpath('.//*[@cid="good"]')[0]
        bad = root.xpath('.//*[@cid="bad"]')[0]

        self.assertEqual(result["errorType"], "Grouping Error")
        self.assertEqual(result["contextType"], "Mixed Context")
        self.assertEqual(result["groupingErrorInlineMath"], 1)
        self.assertEqual(result["processedInlineMath"], 1)
        self.assertTrue(good.get("aria-labelledby"))
        self.assertIn("He has", self._accessible_label(result["convertedQuestionHtml"], "good"))
        self.assertNotIn("aria-labelledby", bad.attrib)
        self.assertNotIn("bad_label", result["convertedQuestionHtml"])

    def test_sequence_scaffold_without_continuation_instruction_is_grouping_error(self):
        source = (
            '<div class="question-stem-content">'
            '<p>Start at the number shown. Write the next 3 numbers.</p>'
            '<p class="sequence">38, '
            '<span cid="n1" ctype="InlineMath"></span>, '
            '<span cid="n2" ctype="InlineMath"></span>, '
            '<span cid="n3" ctype="InlineMath"></span></p>'
            '</div>'
        )
        result = convert_question_html(source, "q1")
        root = lxml_html.fragment_fromstring(result["convertedQuestionHtml"], create_parent="div")
        controls = root.xpath('.//*[@ctype="InlineMath"]')

        self.assertEqual(result["errorType"], "Grouping Error")
        self.assertEqual(result["groupingErrorInlineMath"], 3)
        self.assertEqual(result["processedInlineMath"], 0)
        self.assertEqual(result["contextType"], "Manual Review")
        self.assertTrue(all("aria-labelledby" not in control.attrib for control in controls))
        self.assertIn("Write the next 3 numbers", result["convertedQuestionHtml"])

    def test_multistep_subtraction_scaffolds_are_grouping_errors(self):
        source = (
            '<div class="question-stem-content">'
            '<p>Use the blocks to model the subtraction. Make 10. '
            'Then find the difference. Complete the subtraction sentences.</p>'
            '<p>13 − 5 = ?</p>'
            '<p>13 − <span cid="a" ctype="InlineMath"></span> − '
            '<span cid="b" ctype="InlineMath"></span> = ?</p>'
            '<p>10 − <span cid="c" ctype="InlineMath"></span> =</p>'
            '</div>'
        )
        result = convert_question_html(source, "q1")
        root = lxml_html.fragment_fromstring(result["convertedQuestionHtml"], create_parent="div")
        controls = root.xpath('.//*[@ctype="InlineMath"]')

        self.assertEqual(result["errorType"], "Grouping Error")
        self.assertEqual(result["groupingErrorInlineMath"], 3)
        self.assertEqual(result["processedInlineMath"], 0)
        self.assertEqual(result["contextType"], "Manual Review")
        self.assertTrue(all("aria-labelledby" not in control.attrib for control in controls))

    def test_each_result_input_in_a_multi_input_segment_gets_its_source(self):
        source = '<div class="question-stem-content">21 ÷ 5<br>Quotient: <div cid="a" ctype="InlineMath"></div>. Remainder: <div cid="b" ctype="InlineMath"></div></div>'
        result = convert_question_html(source, "q1")
        converted = result["convertedQuestionHtml"]
        self.assertIn("21 ÷ 5", converted)
        self.assertEqual(result["contextType"], "Preceding Context Required")

    def test_local_formula_and_result_are_sufficient_without_expansion(self):
        source = '<div class="question-stem-content">Find the quotient.<br>24 ÷ 6 = <div cid="a" ctype="InlineMath"></div></div>'
        result = convert_question_html(source, "q1")
        converted = result["convertedQuestionHtml"]
        label_start = converted.index('id="a_label_1"')
        self.assertIn("24 ÷ 6", converted[label_start:])
        self.assertNotIn("Find the quotient", converted[label_start:])
        self.assertEqual(result["contextType"], "Self-contained Input Context")

    def test_calculation_source_search_stops_at_part_boundary(self):
        source = '<div class="question-stem-content"><span class="part_label">Part A</span><br>24 ÷ 6<br><span class="part_label">Part B</span><br>Quotient: <div cid="a" ctype="InlineMath"></div></div>'
        result = convert_question_html(source, "q1")
        converted = result["convertedQuestionHtml"]
        label_start = converted.index('id="a_label_1"')
        self.assertNotIn("24 ÷ 6", converted[label_start:])
        self.assertEqual(result["contextType"], "Manual Review")

    def test_only_nearest_question_sentence_is_added(self):
        source = '<div class="question-stem-content">Mia owns several ribbons. How long is the blue ribbon?<br><br><div cid="a" ctype="InlineMath"></div> centimeters</div>'
        result = convert_question_html(source, "q1")
        converted = result["convertedQuestionHtml"]
        label_start = converted.index('id="a_label_1"')
        labelled_fragment = converted[label_start:]
        self.assertIn("How long is the blue ribbon?", labelled_fragment)
        self.assertNotIn("Mia owns several ribbons.", labelled_fragment)
        self.assertEqual(result["contextType"], "Preceding Context Required")

    def test_person_title_does_not_split_question_sentence(self):
        source = '<div class="question-stem-content">Background text.<br>How many miles did Mr. Edson drive?<br><br><div cid="a" ctype="InlineMath"></div> miles</div>'
        result = convert_question_html(source, "q1")
        converted = result["convertedQuestionHtml"]
        label_start = converted.index('id="a_label_1"')
        self.assertIn("How many miles did Mr. Edson drive?", converted[label_start:])

    def test_instruction_is_added_when_measure_does_not_explain_expected_answer(self):
        source = '<div class="question-stem-content">Find the number of half inches equal to each measure.<br><span></span>7 in.<br><br><div cid="a" ctype="InlineMath"></div></div>'
        result = convert_question_html(source, "q1")
        converted = result["convertedQuestionHtml"]
        label_start = converted.index('id="a_label_1"')
        self.assertIn("Find the number of half inches", converted[label_start:])
        self.assertIn("7 in.", converted[label_start:])
        self.assertEqual(result["contextType"], "Preceding Context Required")

    def test_place_value_fragment_keeps_preceding_expression(self):
        source = '<div class="question-stem-content">23 tens =<br><div cid="a" ctype="InlineMath"></div> hundreds <div cid="b" ctype="InlineMath"></div> tens</div>'
        result = convert_question_html(source, "q1")
        converted = result["convertedQuestionHtml"]
        label_start = converted.index('id="a_label_1"')
        self.assertIn("23 tens =", converted[label_start:])
        self.assertEqual(result["contextType"], "Preceding Context Required")

    def test_independent_complete_rows_get_separate_groups(self):
        source = '<div class="question-stem-content">Enter the values.<br>4 sixes = <div cid="a" ctype="InlineMath"></div><br>4 × 6 = <div cid="b" ctype="InlineMath"></div></div>'
        result = convert_question_html(source, "q1")
        self.assertEqual(result["processedGroups"], 2)
        self.assertEqual(result["contextType"], "Self-contained Input Context")

    def test_or_expressions_in_one_dom_segment_get_separate_groups(self):
        source = '<div class="question-stem-content">8 ÷ 4 = <div cid="a" ctype="InlineMath"></div> OR 8 ÷ 2 = <div cid="b" ctype="InlineMath"></div></div>'
        result = convert_question_html(source, "q1")
        self.assertEqual(result["processedGroups"], 2)

    def test_dependent_inputs_in_one_equation_stay_grouped(self):
        source = '<div class="question-stem-content">4 × <div cid="a" ctype="InlineMath"></div> = <div cid="b" ctype="InlineMath"></div></div>'
        result = convert_question_html(source, "q1")
        self.assertEqual(result["processedGroups"], 1)

    def test_currency_parts_split_by_period_stay_grouped(self):
        source = '<div class="question-stem-content">$43.92 ÷ 6 = $<div cid="a" ctype="InlineMath"></div>.<div cid="b" ctype="InlineMath"></div></div>'
        result = convert_question_html(source, "q1")
        self.assertEqual(result["processedGroups"], 1)
        converted = result["convertedQuestionHtml"]
        self.assertIn('aria-labelledby="a_label_1"', converted)
        self.assertEqual(converted.count('aria-labelledby="a_label_1"'), 2)

    def test_decimal_period_is_not_a_sentence_boundary(self):
        self.assertIsNone(_semantic_split_offset(" 1.7 "))
        self.assertEqual(_local_sentence_start("The measure is 1.7 "), 0)
        self.assertEqual(
            _semantic_sentences("Use 1.7 centimeters. Find the missing value."),
            ["Use 1.7 centimeters.", " Find the missing value."],
        )

    def test_measurement_abbreviation_stays_with_continuing_context(self):
        self.assertIsNone(_semantic_split_offset(" 7 in. [input]"))
        self.assertIsNone(_semantic_split_offset(" 7 in. and "))
        self.assertGreater(_semantic_split_offset(" 7 in. Find "), 0)

    def test_abbreviation_can_still_end_a_sentence(self):
        self.assertEqual(_local_sentence_start("The length is 7 in. Find the area."), len("The length is 7 in. "))
        self.assertEqual(
            _question_sentence_start("Background 1.7 inches. How long is it?"),
            len("Background 1.7 inches. "),
        )

    def test_two_complete_sentences_in_one_dom_segment_are_split(self):
        source = '<div class="question-stem-content">She filled <div cid="a" ctype="InlineMath"></div> pages. She needs <div cid="b" ctype="InlineMath"></div> pages in total.</div>'
        result = convert_question_html(source, "q1")
        self.assertEqual(result["processedGroups"], 2)

    def test_part_label_stops_previous_context_search(self):
        source = '<div class="question-stem-content">How many cards remain?<br><span class="part_label">Part B</span><br><br><div cid="a" ctype="InlineMath"></div> cards</div>'
        result = convert_question_html(source, "q1")
        converted = result["convertedQuestionHtml"]
        label_start = converted.index('id="a_label_1"')
        self.assertNotIn("How many cards remain?", converted[label_start:])
        self.assertEqual(result["contextType"], "Manual Review")

    def test_outside_question_stem_is_not_grouped(self):
        source = '<div><div cid="a" ctype="InlineMath"></div></div>'
        result = convert_question_html(source, "q1")
        self.assertNotIn("aria-labelledby", result["convertedQuestionHtml"])
        self.assertEqual(result["contextType"], "Manual Review")

    def test_v1_skips_protected_table_classes(self):
        for table_class in ("verticalEquation", "default_style"):
            source = f'<table class="{table_class}"><tr><td><div cid="a" ctype="InlineMath"></div></td></tr></table>'
            result = convert_question_html(source, "q1")
            self.assertEqual(result["type"], "Skipped/Protected Table")
            self.assertNotIn("aria-labelledby", result["convertedQuestionHtml"])
            self.assertEqual(result["protectedInlineMath"], 1)

    def test_v1_processes_itype_inline_math(self):
        source = '<div class="question-stem-content">Enter a value <div cid="a" ctype="Fib_Array" itype="InlineMath"></div> students</div>'
        result = convert_question_html(source, "q1")
        self.assertEqual(result["processableInlineMath"], 1)
        self.assertIn("aria-labelledby", result["convertedQuestionHtml"])

    def test_wrapper_keeps_br_and_half_line_padding_together(self):
        source = '<div class="question-stem-content">Find the quotient.<br><span class="half-line-padding"></span>8 &divide; 2 = <div cid="a" ctype="InlineMath"></div></div>'
        result = convert_question_html(source, "q1")
        root = lxml_html.fragment_fromstring(result["convertedQuestionHtml"], create_parent="div")
        wrappers = root.xpath('.//div[@id="a_label_1"]')
        self.assertEqual(len(wrappers), 1)
        wrapper = wrappers[0]
        self.assertEqual(str(wrapper[0].tag).lower(), "br")
        self.assertIn("half-line-padding", (wrapper[1].get("class") or "").split())
        self.assertEqual(
            root.xpath(
                '//div[@id and preceding-sibling::*[1][self::br] and *[1][self::span and contains(concat(" ", normalize-space(@class), " "), " half-line-padding ")]]'
            ),
            [],
        )

    def test_generated_label_id_replaces_whitespace_in_cid(self):
        source = '<div class="question-stem-content">Enter <div cid="answer-\t01" ctype="InlineMath"></div> students.</div>'
        result = convert_question_html(source, "q1")
        root = lxml_html.fragment_fromstring(result["convertedQuestionHtml"], create_parent="div")
        control = root.xpath('.//*[@cid="answer-\t01"]')[0]
        label_id = control.get("aria-labelledby", "")
        self.assertEqual(len(label_id.split()), 1)
        self.assertNotIn("\t", label_id)
        self.assertIsNotNone(root.xpath('.//*[@id=$id]', id=label_id)[0])

    def test_preserves_source_aria_label_for_empty_table_row_context(self):
        source = (
            '<div class="question-stem-content"><table><tbody><tr><td>'
            '<div aria-label="Factor 1" ctype="Fib_Array" itype="InlineMath"></div>'
            '</td></tr></tbody></table></div>'
        )
        result = convert_question_html(source, "q1")
        root = lxml_html.fragment_fromstring(result["convertedQuestionHtml"], create_parent="div")
        control = root.xpath('.//*[@ctype="Fib_Array"]')[0]
        self.assertEqual(control.get("aria-label"), "Factor 1")
        self.assertNotIn("aria-labelledby", control.attrib)
        self.assertEqual(root.xpath('.//*[@id]'), [])


if __name__ == "__main__":
    unittest.main()
