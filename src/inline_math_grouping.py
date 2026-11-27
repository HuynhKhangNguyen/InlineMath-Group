"""Recovered InlineMath grouping rules for Excel/XML review workflows."""

from __future__ import annotations

import copy
import html
import json
import re
from collections import OrderedDict
from dataclasses import asdict, dataclass
from typing import Any, Iterable

from lxml import etree
from lxml import html as lxml_html


BLOCK_TAGS = {
    "address",
    "article",
    "aside",
    "blockquote",
    "div",
    "footer",
    "header",
    "li",
    "ol",
    "p",
    "section",
    "table",
    "tbody",
    "td",
    "th",
    "tr",
    "ul",
}

NUMBERLINE_SKIP_CONTEXT = "Skipped/FIB_Numberline"
NUMBERLINE_SKIP_NOTE = "Skip: FIB_Numberline."


@dataclass
class InlineMathItem:
    index: int
    text: str
    html: str
    cid: str
    qname: str
    sourceIndex: str


@dataclass
class InlineMathGroup:
    gid: str
    qname: str
    items: list[InlineMathItem]


def normalize_question_id(value: Any) -> str:
    """Keep identifiers stable when Excel exposes integer IDs as floats."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def parse_question_xml(xml_string: str | None) -> str:
    """Extract and decode the HTML payload inside the XML <question> node once."""
    if not xml_string:
        return ""
    parser = etree.XMLParser(recover=False, resolve_entities=False, no_network=True)
    root = etree.fromstring(xml_string.encode("utf-8"), parser=parser)
    question = root.find(".//question")
    if question is None:
        return ""
    encoded = "".join(question.itertext())
    return html.unescape(encoded)


def parse_html_fragment(html_string: str) -> etree._Element:
    return lxml_html.fragment_fromstring(html_string or "", create_parent="div")


def inner_html(element: etree._Element) -> str:
    """Serialize the children of a synthetic fragment root."""
    parts = [element.text or ""]
    parts.extend(
        etree.tostring(child, encoding="unicode", method="html", with_tail=True)
        for child in element
    )
    return "".join(parts)


def normalize_html_class_attributes(html_string: str) -> str:
    """Convert HTML className attributes to class without replacing text values."""
    if "classname" not in html_string.casefold():
        return html_string
    root = parse_html_fragment(html_string)
    changed = False
    for element in root.iter():
        aliases = [name for name in element.attrib if name.casefold() == "classname"]
        if not aliases:
            continue
        values = [element.attrib.pop(name) for name in aliases]
        if "class" in element.attrib:
            tokens = (element.get("class", "") + " " + " ".join(values)).split()
            element.set("class", " ".join(dict.fromkeys(tokens)))
        else:
            element.set("class", " ".join(values))
        changed = True
    return inner_html(root) if changed else html_string


def is_inline_math(element: etree._Element) -> bool:
    return element.get("ctype") == "InlineMath" or element.get("itype") == "InlineMath"


def has_fib_numberline(root: etree._Element) -> bool:
    """Detect a typed widget anywhere in a source question."""
    return any(
        (element.get(attribute) or "").strip().casefold() == "fib_numberline"
        for element in root.iter()
        for attribute in ("ctype", "itype")
    )


def select_inline_math(root: etree._Element) -> tuple[list[etree._Element], list[etree._Element]]:
    """Return top-level InlineMath controls and accidentally nested controls."""
    candidates = root.xpath('.//*[@ctype="InlineMath" or @itype="InlineMath"]')
    selected: list[etree._Element] = []
    nested: list[etree._Element] = []
    candidate_ids = {id(element) for element in candidates}
    for element in candidates:
        if any(id(ancestor) in candidate_ids for ancestor in element.iterancestors()):
            nested.append(element)
        else:
            selected.append(element)
    return selected, nested


def _class_tokens(element: etree._Element) -> set[str]:
    return set((element.get("class") or "").split())


def protected_table(element: etree._Element) -> tuple[etree._Element | None, list[str]]:
    """Find an ancestor table protected from automatic grouping."""
    for ancestor in (element, *element.iterancestors()):
        if str(ancestor.tag).lower() != "table":
            continue
        tokens = _class_tokens(ancestor)
        reasons = [name for name in ("verticalEquation", "default_style") if name in tokens]
        if reasons:
            return ancestor, reasons
    return None, []


def _nearest_ancestor(element: etree._Element, tags: set[str]) -> etree._Element | None:
    for ancestor in element.iterancestors():
        if str(ancestor.tag).lower() in tags:
            return ancestor
    return None


def _question_stem(element: etree._Element) -> etree._Element | None:
    for ancestor in element.iterancestors():
        if "question-stem-content" in _class_tokens(ancestor):
            return ancestor
    return None


def _context_for_structured_control(
    stem: etree._Element, element: etree._Element
) -> etree._Element | None:
    """Return a real semantic container, or None for a control directly in the stem."""
    table = _nearest_ancestor(element, {"table"})
    if table is not None and _question_stem(table) is stem:
        # A layout table outside the stem is not an eligible context target.
        for candidate in (_nearest_ancestor(element, {"tr"}),
                          _nearest_ancestor(element, {"tbody"}), table):
            if candidate is not None and _question_stem(candidate) is stem:
                return candidate

    structural = _nearest_ancestor(element, {"li", "p"})
    if structural is not None and _question_stem(structural) is stem:
        return structural

    for ancestor in element.iterancestors():
        if ancestor is stem:
            break
        if str(ancestor.tag).lower() == "div" and not is_inline_math(ancestor):
            return ancestor
    return None


def _direct_child(stem: etree._Element, element: etree._Element) -> etree._Element:
    current = element
    while current.getparent() is not stem:
        parent = current.getparent()
        if parent is None:
            return element
        current = parent
    return current


def _replace_controls_with_placeholders(element: etree._Element) -> None:
    for component in element.xpath('.//*[@ctype="InlineMath" or @itype="InlineMath"]'):
        component.clear(keep_tail=True)
        component.text = "[input]"


def _text_with_placeholders(element: etree._Element, *, include_image_alt: bool = False) -> str:
    clone = copy.deepcopy(element)
    _replace_controls_with_placeholders(clone)
    if include_image_alt:
        for image in clone.iter("img"):
            alt = (image.get("alt") or "").strip()
            if alt:
                image.text = f" {alt} "
    return _normalize_text("".join(clone.itertext()))


def _segment_text(stem: etree._Element, children: list[etree._Element], start: int, end: int) -> str:
    holder = etree.Element("div")
    holder.text = stem.text if start == 0 else (children[start - 1].tail or "")
    for child in children[start:end]:
        holder.append(copy.deepcopy(child))
    _replace_controls_with_placeholders(holder)
    return _normalize_text("".join(holder.itertext()))


def _range_text(
    container: etree._Element,
    children: list[etree._Element],
    start: int,
    end: int,
    start_offset: int = 0,
) -> str:
    holder = etree.Element("div")
    raw_prefix = container.text if start == 0 else (children[start - 1].tail or "")
    holder.text = (raw_prefix or "")[start_offset:]
    for child in children[start:end]:
        holder.append(copy.deepcopy(child))
    _replace_controls_with_placeholders(holder)
    return _normalize_text("".join(holder.itertext()))


TITLE_ABBREVIATIONS = {
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "rev",
}
UNIT_ABBREVIATIONS = {
    "in", "ft", "yd", "oz", "lb", "cm", "mm", "m", "km", "g", "kg",
    "mg", "ml", "l", "sec", "min", "hr", "hrs", "sq", "cu",
}
OTHER_ABBREVIATIONS = {
    "no", "fig", "eq", "approx", "misc", "dept", "vol", "vs", "etc",
    "e.g", "i.e",
}


def _period_token(text: str, index: int) -> str:
    """Return the word/abbreviation immediately before ``text[index]``."""
    match = re.search(r"([A-Za-z](?:[A-Za-z.]*)?)$", text[:index])
    return match.group(1).lower() if match else ""


def _next_nonspace(text: str, index: int) -> str:
    match = re.search(r"\S+", text[index + 1 :])
    return match.group(0) if match else ""


def _period_is_sentence_boundary(
    text: str, index: int, *, terminal_abbreviation_is_continuation: bool = False
) -> bool:
    """Decide whether one period ends a semantic unit.

    A period is only a boundary when its token and surrounding content support
    that interpretation.  Decimal points, identifier separators, and
    abbreviations that continue into the next token are kept inside the same
    semantic unit.  ``terminal_abbreviation_is_continuation`` is used while
    splitting text between adjacent inputs: a trailing ``in.`` or ``ft.`` is
    followed by the next input, so it is conservatively kept with that input.
    """
    if index < 0 or index >= len(text) or text[index] != ".":
        return False

    previous = text[index - 1] if index else ""
    following = text[index + 1] if index + 1 < len(text) else ""

    # Decimal numbers and compact identifiers such as ``v1.2`` are not
    # sentence boundaries.  A period followed immediately by a non-space
    # character is likewise part of a token (URL, identifier, or expression).
    if previous.isdigit() and following.isdigit():
        return False
    if following and not following.isspace() and following != ".":
        return False

    token = _period_token(text, index)
    next_token = _next_nonspace(text, index)
    normalized_next = next_token.lstrip("([{\"")

    # Initials, titles, and multi-period abbreviations do not end the name or
    # phrase that follows them.  ``e.g.`` and ``i.e.`` remain one token even
    # when the next word is capitalized.
    if "." in token or token in TITLE_ABBREVIATIONS or len(token) == 1:
        if next_token:
            return False
        return not terminal_abbreviation_is_continuation

    if token in UNIT_ABBREVIATIONS or token in OTHER_ABBREVIATIONS:
        if not next_token:
            return not terminal_abbreviation_is_continuation
        # ``7 in. [input]``, ``No. 3``, and ``etc. and ...`` continue the same
        # semantic unit.  A new capitalized sentence after an abbreviation is
        # allowed to form a real boundary (``The length is 7 in. Find ...``).
        if next_token.startswith("[input]") or normalized_next[:1].isdigit():
            return False
        if normalized_next[:1].islower() or normalized_next[:1] in "+-=×÷*/,:;":
            return False
        return True

    # A regular period must be followed by whitespace/end-of-text to be a
    # candidate boundary.  Unlike the old character-only rule, decimals and
    # abbreviation continuations have already been removed above.
    return True


def _sentence_boundary_positions(
    text: str, *, terminal_abbreviation_is_continuation: bool = False
) -> list[int]:
    return [
        match.start()
        for match in re.finditer(r"[.!?]", text)
        if match.group() != "."
        or _period_is_sentence_boundary(
            text,
            match.start(),
            terminal_abbreviation_is_continuation=terminal_abbreviation_is_continuation,
        )
    ]


def _semantic_sentences(text: str) -> list[str]:
    """Split text at semantic sentence boundaries, not every period."""
    boundaries = _sentence_boundary_positions(text)
    sentences = []
    start = 0
    for boundary in boundaries:
        sentences.append(text[start : boundary + 1])
        start = boundary + 1
    if text[start:]:
        sentences.append(text[start:])
    return sentences


def _semantic_split_offset(text_between: str) -> int | None:
    """Find where an independent statement starts between adjacent inputs."""
    or_match = re.search(r"\bOR\b", text_between, flags=re.IGNORECASE)
    if or_match:
        return or_match.start()

    # A lone period/question mark between adjacent controls can be the
    # punctuation between parts of one answer (for example dollars and cents),
    # rather than the start of an independent semantic statement.
    if re.fullmatch(r"\s*[.!?]\s*", text_between or ""):
        return None

    punctuation = _sentence_boundary_positions(
        text_between, terminal_abbreviation_is_continuation=True
    )
    if punctuation:
        start = punctuation[0] + 1
        while start < len(text_between) and text_between[start].isspace():
            start += 1
        return start

    stripped_start = len(text_between) - len(text_between.lstrip())
    stripped = text_between[stripped_start:]
    if stripped and not stripped.startswith(("+", "-", "−", "×", "÷", "*", "/", "=", ",", ";", "and ")):
        if re.search(r"\d", stripped) and re.search(r"[+×÷−*/=]", stripped):
            return stripped_start
        if stripped.startswith("(") and re.search(r"[+×÷−*/=]", stripped):
            return stripped_start
    return None


def _segments(stem: etree._Element) -> list[tuple[int, int]]:
    children = list(stem)
    segments: list[tuple[int, int]] = []
    start = 0
    for index, child in enumerate(children):
        if str(child.tag).lower() == "br":
            segments.append((start, index))
            start = index + 1
    segments.append((start, len(children)))
    return segments


def _segment_index_for_child(segments: list[tuple[int, int]], child_index: int) -> int:
    for segment_index, (start, end) in enumerate(segments):
        if start <= child_index < end:
            return segment_index
    return max(0, len(segments) - 1)


RESULT_HEADS = {
    "amount", "answer", "area", "cost", "difference", "distance", "elapsed",
    "height", "length", "mean", "median", "mode", "number", "perimeter",
    "product", "quotient", "range", "remainder", "result", "solution", "sum",
    "total", "value", "width",
}
HIGH_CONFIDENCE_RESULT_HEADS = {
    "answer", "difference", "product", "quotient", "remainder", "result",
    "solution", "sum", "total", "value",
}
RESULT_PHRASES = {"standard form", "correct answer", "final answer", "exact answer"}
HIGH_CONFIDENCE_RESULT_PHRASES = {"standard form", "correct answer", "final answer"}
INTERACTIVE_CHOICE_CTYPES = {
    "multiplechoice", "drop_down", "dropdown", "drop-down", "select", "choice",
}


def _is_calculation_source(text: str) -> bool:
    """Return whether a block expresses a calculation and its operands."""
    normalized = text.replace("\xa0", " ").lower()
    numbers = re.findall(r"(?<![a-z])\d+(?:,\d{3})*(?:\.\d+)?", normalized)
    if len(numbers) < 2:
        return False
    has_operator = bool(
        re.search(r"[+−–×÷*/=]", normalized)
        or re.search(r"\\(?:times|div|cdot|frac|over)|longdiv|begin\{array\}", normalized)
        or re.search(
            r"\b(?:plus|minus|times|divided by|multiplied by|added to|subtracted from|"
            r"sum of|difference between|product of|quotient of|groups? of)\b",
            normalized,
        )
    )
    return has_operator


def _looks_like_calculation_result(text: str) -> bool:
    """Recognize result-label/scaffold blocks without depending on one label word.

    Short colon labels are treated as result scaffolds by structure. Common
    mathematical result nouns also cover sentence-shaped labels such as
    ``The quotient is [input]`` or ``The answer equals [input]``.
    """
    if "[input]" not in text:
        return False
    prefix = text.split("[input]", 1)[0].strip()
    prefix_words = re.findall(r"[A-Za-z]+", prefix.lower())
    suffix = text.split("[input]", 1)[1].strip()
    if prefix.endswith(":") and len(prefix_words) <= 5 and not suffix.startswith(("because", "when", "if")):
        return True
    tokens = set(re.findall(r"[A-Za-z]+", text.lower()))
    lowered = " ".join(text.lower().split())
    return bool(tokens.intersection(RESULT_HEADS) or any(phrase in lowered for phrase in RESULT_PHRASES))


def _has_high_confidence_result_head(text: str) -> bool:
    tokens = set(re.findall(r"[A-Za-z]+", text.lower()))
    lowered = " ".join(text.lower().split())
    return bool(
        tokens.intersection(HIGH_CONFIDENCE_RESULT_HEADS)
        or any(phrase in lowered for phrase in HIGH_CONFIDENCE_RESULT_PHRASES)
    )


def _calculation_start_offset(text: str) -> int:
    """Best-effort start of the source expression within a plain text slot."""
    special = re.search(r"\\(?:begin\{array\}|frac|dfrac|tfrac|sqrt)", text, re.IGNORECASE)
    if special:
        return special.start()
    expression = re.search(
        r"\d+(?:,\d{3})*(?:\.\d+)?\s*(?:[+−–×÷*/=]|"
        r"plus\b|minus\b|times\b|divided\s+by\b|multiplied\s+by\b)",
        text,
        re.IGNORECASE,
    )
    if expression:
        return expression.start()
    return 0


def _calculation_end_offset(text: str, start: int) -> int:
    """Trim semicolon-separated prose that restates an already shown result."""
    remainder = text[start:]
    last_calculation_end = 0
    for match in re.finditer(r"[^;]+(?:;|$)", remainder):
        clause = match.group().strip().rstrip(";").strip()
        if not clause or not _is_calculation_source(clause):
            break
        last_calculation_end = match.end()
        if match.end() >= len(remainder):
            break
    if not last_calculation_end:
        return len(text)
    end = start + last_calculation_end
    if text[end:].strip() and text[max(start, end - 1):end] == ";":
        end -= 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return end


def _is_interactive_choice_block(element: etree._Element) -> bool:
    candidate_types = {
        (node.get("ctype") or "").lower()
        for node in [element, *element.iterdescendants()]
    }
    return bool(candidate_types.intersection(INTERACTIVE_CHOICE_CTYPES))


def _is_part_marker(element: etree._Element) -> bool:
    return "part_label" in _class_tokens(element) or bool(
        element.xpath('.//*[contains(concat(" ", normalize-space(@class), " "), " part_label ")]')
    )


def _contains_protected_table(element: etree._Element) -> bool:
    for table in ([element] if str(element.tag).lower() == "table" else []) + element.xpath(".//table"):
        if _class_tokens(table).intersection({"verticalEquation", "default_style"}):
            return True
    return False


def _raw_prefix_before_child(stem: etree._Element, children: list[etree._Element], index: int) -> str:
    return stem.text or "" if index == 0 else children[index - 1].tail or ""


def _nearest_preceding_calculation_source(
    stem: etree._Element, control: etree._Element
) -> dict[str, Any] | None:
    """Find the nearest earlier calculation block in the current part section.

    The result points to either a text slot before a direct child or a direct
    child block, allowing a formula and its answer label to be separate DOM
    siblings without pulling in earlier instructions.
    """
    children = list(stem)
    anchor = _direct_child(stem, control)
    child_indexes = {id(child): index for index, child in enumerate(children)}
    if id(anchor) not in child_indexes:
        return None
    target_child = child_indexes[id(anchor)]
    segments = _segments(stem)
    target_segment = _segment_index_for_child(segments, target_child)
    target_start, _ = segments[target_segment]

    markers = [
        index for index, child in enumerate(children)
        if _is_part_marker(child)
    ]
    section_floor = 0
    same_segment_floor = target_start
    for marker in markers:
        marker_segment = _segment_index_for_child(segments, marker)
        if marker_segment < target_segment:
            section_floor = max(section_floor, marker_segment + 1)
        elif marker_segment == target_segment and marker < target_child:
            same_segment_floor = max(same_segment_floor, marker + 1)

    def raw_source(index: int, segment_index: int) -> dict[str, Any] | None:
        raw = _raw_prefix_before_child(stem, children, index)
        if _is_calculation_source(raw):
            offset = _calculation_start_offset(raw)
            end_offset = _calculation_end_offset(raw, offset)
            return {
                "segment": segment_index,
                "child": index,
                "offset": offset,
                "endOffset": end_offset,
                "sourceKind": "raw",
                "rawText": raw,
                "text": raw[offset:end_offset],
            }
        return None

    def child_source(index: int, segment_index: int) -> dict[str, Any] | None:
        child = children[index]
        if _is_part_marker(child) or _contains_protected_table(child):
            return None
        raw_prefix = _raw_prefix_before_child(stem, children, index)
        candidate = _text_with_placeholders(child)
        if _is_calculation_source(candidate):
            return {
                "segment": segment_index,
                "child": index,
                "offset": len(raw_prefix),
                "sourceKind": "element",
                "text": candidate,
                "ambiguous": bool(
                    child.xpath('.//*[@subid="options" or @idx]')
                    or _is_interactive_choice_block(child)
                    or child.xpath('.//*[@ctype="InlineMath" or @itype="InlineMath"]')
                ),
            }
        return None

    # Inspect the current visual segment first so sibling math blocks directly
    # before a result label are preserved precisely.
    for index in range(target_child, same_segment_floor - 1, -1):
        found = raw_source(index, target_segment)
        if found:
            return found
        previous_child = index - 1
        if previous_child >= same_segment_floor:
            found = child_source(previous_child, target_segment)
            if found:
                return found

    # Continue across <br>-separated blocks, stopping at the part boundary.
    for segment_index in range(target_segment - 1, section_floor - 1, -1):
        start, end = segments[segment_index]
        for index in range(end, start - 1, -1):
            found = raw_source(index, segment_index)
            if found:
                return found
            previous_child = index - 1
            if previous_child >= start:
                found = child_source(previous_child, segment_index)
                if found:
                    return found
    return None


FINITE_VERBS = {
    "am", "are", "be", "been", "being", "build", "builds", "built",
    "brush", "brushes", "buy", "buys", "bought", "can", "choose", "chose",
    "collect", "collects", "cost", "costs", "did", "do", "does", "drink",
    "drank", "drive", "drives", "drove", "eat", "eats", "equal", "equals",
    "fill", "fills", "finish", "finishes", "fit", "fits", "get", "gets",
    "got", "give", "gives", "gave", "had", "has", "have", "hike", "hikes",
    "hold", "holds", "is", "jog", "jogs", "jogged", "last", "lasted",
    "like", "likes", "made", "make", "makes", "measure", "measures", "need",
    "needs", "order", "orders", "paid", "pay", "pays", "plant", "plants",
    "planted", "play", "plays", "played", "read", "reads", "receive",
    "receives", "received", "remain", "remains", "repair", "repairs",
    "repaired", "ride", "rides", "rode", "score", "scored", "scores", "set",
    "sets", "show", "shows", "sold", "spend", "spends", "spent", "start",
    "starts", "started", "swam", "take", "takes", "took", "travel", "travels",
    "use", "used", "uses", "was", "weigh", "weighs", "went", "were", "will",
    "win", "wins", "won", "work", "works", "worked", "should",
}


def _has_explicit_subject_predicate(text: str) -> bool:
    """Recognize a declarative clause around an input without using DOM proximity.

    This deliberately requires an explicit subject. Imperative fragments such as
    ``Enter [input]`` still need their local object/units or preceding instruction.
    Regular past-tense verbs are accepted so the decision is not limited to a
    closed list of workbook vocabulary.
    """
    tokens = re.findall(r"\[input\]|[A-Za-z]+(?:[’'][A-Za-z]+)?", text.lower())
    try:
        input_index = tokens.index("[input]")
    except ValueError:
        return False

    determiners = {"a", "an", "the"}
    prepositions = {"about", "at", "by", "for", "from", "in", "of", "on", "per", "to", "with"}

    def is_finite_verb(word: str) -> bool:
        return word in FINITE_VERBS or (len(word) > 3 and word.endswith("ed"))

    for verb_index, word in enumerate(tokens):
        if not is_finite_verb(word):
            continue
        if verb_index < input_index:
            subject_words = [
                token
                for token in tokens[:verb_index]
                if token not in determiners and token not in prepositions
            ]
            if subject_words:
                return True
        elif verb_index > input_index:
            # The answer value can begin the subject noun phrase:
            # "[input] students chose dove."
            subject_words = [
                token
                for token in tokens[input_index + 1 : verb_index]
                if token not in determiners and token not in prepositions
            ]
            if subject_words:
                return True
    return False


def _local_statement_is_complete(text: str) -> bool:
    if "[input]" not in text:
        return False
    prefix = text.split("[input]", 1)[0].strip()
    suffix = text.split("[input]", 1)[1].strip()
    if re.search(r"\d|[+×÷−*/=]", prefix):
        return True
    words = re.findall(r"[A-Za-z]+", prefix.lower())
    if prefix.rstrip().endswith((":", "=", "(")) and words:
        return True
    if _has_explicit_subject_predicate(text):
        return True
    return False


def _incomplete_numeric_scaffold_reason(context_text: str, source_text: str = "") -> str:
    """Identify numeric scaffolds whose local label omits required task meaning.

    A starting value followed only by blank comma slots does not explain that
    the user must continue a sequence. Likewise, a blank arithmetic equation
    inside a multi-step strategy is not self-contained when its local context
    omits the strategy instruction that relates its equations.
    """
    normalized = _normalize_text(context_text)
    input_count = normalized.count("[input]")
    if not input_count:
        return ""

    scaffold = normalized.replace("[input]", "INPUT")
    if input_count >= 2 and re.fullmatch(
        r"\d+(?:\s*,\s*(?:INPUT|\d+)?){2,}\s*,?",
        scaffold,
    ):
        return "numeric sequence slots are missing their preceding continuation instruction"

    source = _normalize_text(source_text)
    if re.fullmatch(r"\[input\]\s*o['’]clock\.?", normalized, re.IGNORECASE) and re.search(
        r"\bhours?\s+(?:before|after)\b", source, re.IGNORECASE
    ):
        return "time answer omits its preceding before/after relation"
    strategy_cue_pattern = re.compile(
        r"\b(?:make\s+10|count\s+on|model(?:\s+the)?\s+subtraction|"
        r"find\s+the\s+difference|complete\s+(?:the\s+)?"
        r"(?:subtraction|addition|equation|number\s+sentence)s?)\b",
        re.IGNORECASE,
    )
    if not strategy_cue_pattern.search(source) or strategy_cue_pattern.search(normalized):
        return ""
    if source.count("[input]") < 2 or source.count("=") < 2:
        return ""

    equals_at = normalized.rfind("=")
    if equals_at < 0:
        return ""
    left = normalized[:equals_at]
    right = normalized[equals_at + 1 :].strip().rstrip(".,;:")
    if (
        "[input]" in left
        and re.search(r"[+\-−–×÷*/]", left)
        and right in {"", "?"}
    ):
        return "incomplete arithmetic scaffold omits its multi-step strategy context"
    return ""


def _is_applicable_preceding_context(text: str, local_text: str = "") -> bool:
    normalized = text.strip()
    if not normalized:
        return False
    # A question can begin with setup wording (for example, ``In the number
    # 4.488, which digit ...?``), so the opening word is not a reliable
    # question marker.
    if "?" in normalized:
        return True
    instruction_words = {
        "add", "calculate", "choose", "compare", "complete", "count", "determine", "divide", "enter",
        "estimate", "fill", "find", "give", "identify", "measure", "name", "order", "regroup",
        "round", "select", "solve", "subtract", "use", "write",
    }
    # A preceding block may begin with setup prose and end with the actual
    # question/instruction (for example, ``Susie buys ... Estimate ...``).
    # Evaluate sentence starts rather than requiring the first word of the
    # whole block to be an instruction.
    question_words = {"how", "what", "when", "where", "which", "who", "why"}
    sentences = _semantic_sentences(normalized)
    for sentence in sentences:
        words = re.findall(r"[A-Za-z]+", sentence.lower())
        if words and words[0] in instruction_words:
            return True
        if words and words[0] in question_words:
            return True
    # A short result scaffold such as "Next number:" is useful context for
    # an otherwise standalone input, while its incomplete meaning remains
    # eligible for Manual Review.
    words = re.findall(r"[A-Za-z]+", normalized.lower())
    if normalized.endswith(":") and words:
        return True
    if re.search(r"\d", normalized) and re.search(r"[+×÷−*/=]", normalized):
        return True
    if re.search(r"\bhours?\s+(?:before|after)\s+\d", normalized, re.IGNORECASE):
        return True
    if "[input]" in normalized or not re.search(r"\d", normalized):
        return False
    # A declarative statement can supply missing facts when it explicitly
    # names the same quantity as the answer fragment.
    stop_words = {"a", "an", "and", "at", "by", "for", "has", "in", "is", "it", "of",
                  "on", "or", "the", "to", "with"}
    local_words = set(re.findall(r"[A-Za-z]+", local_text.lower().replace("[input]", ""))) - stop_words
    nouns = set(words) - stop_words - FINITE_VERBS
    return bool(local_words & nouns and set(words) & FINITE_VERBS)


def _question_sentence_start(raw_text: str) -> int:
    """Return the start of the last question sentence in one text slot."""
    last_question = raw_text.rfind("?")
    if last_question < 0:
        return 0
    breaks = [
        index
        for index in _sentence_boundary_positions(raw_text[:last_question])
        if index < last_question
    ]
    previous_end = max(breaks, default=-1)
    start = previous_end + 1
    while start < len(raw_text) and raw_text[start].isspace():
        start += 1
    return start


def _local_sentence_start(raw_text: str) -> int:
    stripped_end = len(raw_text.rstrip())
    boundaries = _sentence_boundary_positions(raw_text)
    last_end = boundaries[-1] if boundaries else -1
    if last_end >= 0 and last_end < stripped_end and not raw_text[last_end + 1 :].strip():
        previous_boundaries = [boundary for boundary in boundaries if boundary < last_end]
        previous_end = previous_boundaries[-1] if previous_boundaries else -1
    else:
        previous_end = last_end
    start = previous_end + 1
    while start < len(raw_text) and raw_text[start].isspace():
        start += 1
    return start


def _is_half_line_padding(element: etree._Element | None) -> bool:
    """Return whether an element is the spacer paired with a line break."""
    return bool(
        element is not None
        and str(element.tag).lower() == "span"
        and "half-line-padding" in _class_tokens(element)
    )


def _wrap_stem_intervals(
    stem: etree._Element, controls: list[etree._Element]
) -> list[dict[str, Any]]:
    """Wrap sentence-sized ranges for controls that are direct children of a stem."""
    children = list(stem)
    segments = _segments(stem)
    segment_texts = [_segment_text(stem, children, start, end) for start, end in segments]
    control_segments: dict[int, list[etree._Element]] = OrderedDict()
    child_indexes = {id(child): index for index, child in enumerate(children)}
    for control in controls:
        anchor = _direct_child(stem, control)
        child_index = child_indexes[id(anchor)]
        segment_index = _segment_index_for_child(segments, child_index)
        control_segments.setdefault(segment_index, []).append(control)

    part_segment_indexes = []
    for index, child in enumerate(children):
        has_part_label = "part_label" in _class_tokens(child) or bool(
            child.xpath('.//*[contains(concat(" ", normalize-space(@class), " "), " part_label ")]')
        )
        if has_part_label:
            part_segment_indexes.append(_segment_index_for_child(segments, index))

    intervals = []
    for segment_index, members in control_segments.items():
        section_floor = 0
        previous_markers = [value for value in part_segment_indexes if value < segment_index]
        if previous_markers:
            section_floor = max(previous_markers) + 1

        segment_start, segment_end = segments[segment_index]
        ordered_members = sorted(
            members, key=lambda member: child_indexes[id(_direct_child(stem, member))]
        )
        partitions = [{"start": segment_start, "startOffset": 0, "members": [ordered_members[0]]}]
        for previous, current in zip(ordered_members, ordered_members[1:]):
            previous_anchor = _direct_child(stem, previous)
            current_anchor = _direct_child(stem, current)
            previous_index = child_indexes[id(previous_anchor)]
            current_index = child_indexes[id(current_anchor)]
            split_offset = None
            split_start = current_index
            if current_index > previous_index:
                between = previous_anchor.tail or ""
                if current_index > previous_index + 1:
                    between += "".join(
                        etree.tostring(child, encoding="unicode", method="text", with_tail=True)
                        for child in children[previous_index + 1 : current_index]
                    )
                split_offset = _semantic_split_offset(between)
                if split_offset is not None and current_index > previous_index + 1:
                    split_start = previous_index + 1
            if split_offset is None:
                partitions[-1]["members"].append(current)
            else:
                partitions.append(
                    {
                        "start": split_start,
                        "startOffset": split_offset,
                        "members": [current],
                    }
                )

        for partition_index, partition in enumerate(partitions):
            start_child = partition["start"]
            end_child = (
                partitions[partition_index + 1]["start"]
                if partition_index + 1 < len(partitions)
                else segment_end
            )
            first_member_index = child_indexes[id(_direct_child(stem, partition["members"][0]))]
            for candidate_index in range(first_member_index + 1, end_child):
                if _is_interactive_choice_block(children[candidate_index]):
                    end_child = candidate_index
                    break
            local_text = _range_text(
                stem, children, start_child, end_child, partition["startOffset"]
            )
            first_member = partition["members"][0]
            semantic_container = _context_for_structured_control(stem, first_member)
            semantic_local_text = (
                _text_with_placeholders(semantic_container)
                if semantic_container is not None
                else local_text
            )
            local_complete = _local_statement_is_complete(semantic_local_text)
            context_type = "Self-contained Input Context" if local_complete else "Manual Review"
            start_segment = segment_index
            explicit_calculation_start = False

            if _looks_like_calculation_result(semantic_local_text):
                if _is_calculation_source(semantic_local_text):
                    context_type = "Self-contained Input Context"
                else:
                    calculation_source = _nearest_preceding_calculation_source(stem, first_member)
                    if calculation_source is not None and not calculation_source.get("ambiguous"):
                        context_type = "Preceding Context Required"
                        explicit_calculation_start = True
                        start_segment = calculation_source["segment"]
                        start_child = calculation_source["child"]
                        partition["startOffset"] = calculation_source["offset"]
                    elif _has_high_confidence_result_head(semantic_local_text):
                        context_type = "Manual Review"
                    else:
                        context_type = (
                            "Self-contained Input Context" if local_complete else "Manual Review"
                        )
            elif not local_complete and partition_index == 0:
                question_segment = None
                for candidate in range(segment_index - 1, section_floor - 1, -1):
                    if _is_applicable_preceding_context(segment_texts[candidate], semantic_local_text):
                        question_segment = candidate
                        break
                if question_segment is not None:
                    start_segment = question_segment
                    start_child = segments[start_segment][0]
                    partition["startOffset"] = 0
                    context_type = "Preceding Context Required"

            raw_start_text = (stem.text if start_child == 0 else children[start_child - 1].tail) or ""
            start_offset = partition["startOffset"]
            if explicit_calculation_start:
                pass
            elif start_segment < segment_index:
                start_offset = _question_sentence_start(raw_start_text)
            elif partition_index == 0:
                start_offset = _local_sentence_start(raw_start_text)

            intervals.append(
                {
                    "start": start_child,
                    "end": end_child,
                    "startOffset": start_offset,
                    "members": list(partition["members"]),
                    "contextTypes": {context_type},
                }
            )

    merged = []
    for interval in sorted(intervals, key=lambda item: (item["start"], item["end"])):
        if merged and interval["start"] < merged[-1]["end"]:
            merged[-1]["end"] = max(merged[-1]["end"], interval["end"])
            merged[-1]["members"].extend(interval["members"])
            merged[-1]["startOffset"] = min(merged[-1]["startOffset"], interval["startOffset"])
            merged[-1]["contextTypes"].update(interval["contextTypes"])
        else:
            merged.append(interval)

    results = []
    for interval in sorted(merged, key=lambda item: item["start"], reverse=True):
        start = interval["start"]
        end = interval["end"]
        moved_before_line_break = (
            start > 0
            and str(children[start - 1].tag).lower() == "br"
            and start < len(children)
            and _is_half_line_padding(children[start])
        )
        if moved_before_line_break:
            # Keep an adjacent <br> and half-line-padding span in the same
            # wrapper without pulling preceding text into that group.
            start -= 1
        nodes = children[start:end]
        owner = stem if start == 0 else children[start - 1]
        raw_prefix = owner.text if start == 0 else owner.tail
        raw_prefix = raw_prefix or ""
        offset = len(raw_prefix) if moved_before_line_break else min(interval["startOffset"], len(raw_prefix))
        before, selected = raw_prefix[:offset], raw_prefix[offset:]
        if start == 0:
            stem.text = before
        else:
            owner.tail = before
        wrapper = etree.Element("div")
        wrapper.text = selected
        stem.insert(start, wrapper)
        for node in nodes:
            wrapper.append(node)
        modes = interval["contextTypes"]
        results.append(
            {
                "context": wrapper,
                "members": interval["members"],
                "contextType": next(iter(modes)) if len(modes) == 1 else "Mixed Context",
                "generatedWrapper": True,
            }
        )
    return list(reversed(results))


def _unwrap_generated_context(wrapper: etree._Element) -> None:
    """Restore the original DOM range when a generated label would be empty."""
    parent = wrapper.getparent()
    if parent is None:
        return

    index = parent.index(wrapper)
    previous = parent[index - 1] if index else None
    prefix = wrapper.text or ""
    suffix = wrapper.tail or ""
    children = list(wrapper)

    if prefix:
        if previous is None:
            parent.text = (parent.text or "") + prefix
        else:
            previous.tail = (previous.tail or "") + prefix

    parent.remove(wrapper)
    for offset, child in enumerate(children):
        wrapper.remove(child)
        parent.insert(index + offset, child)

    if suffix:
        if children:
            children[-1].tail = (children[-1].tail or "") + suffix
        elif previous is None:
            parent.text = (parent.text or "") + suffix
        else:
            previous.tail = (previous.tail or "") + suffix


def _unique_label_id(root: etree._Element, base: str) -> str:
    candidate = base
    suffix = 2
    while root.xpath('.//*[@id=$value]', value=candidate):
        candidate = f"{base}_{suffix}"
        suffix += 1
    return candidate


def _label_id_base(value: Any) -> str:
    """Create an ARIA-token-safe base for generated context IDs."""
    text = str(value or "").strip()
    text = re.sub(r"\s+", "_", text)
    return text or "question"


def _question_xml_fragment(converted_html: str) -> str:
    return f"<question>{html.escape(converted_html, quote=True)}</question>"


def numberline_skip_result(html_string: str, question_id: Any, source_count: int) -> dict[str, Any]:
    """Build the output for a confirmed numberline without grouping its controls."""
    html_string = normalize_html_class_attributes(html_string)
    return {
        "questionId": normalize_question_id(question_id),
        "convertedQuestionHtml": html_string,
        "convertedQuestionXml": _question_xml_fragment(html_string),
        "type": NUMBERLINE_SKIP_CONTEXT,
        "errorType": "",
        "contextType": NUMBERLINE_SKIP_CONTEXT,
        "contextTypeCounts": {NUMBERLINE_SKIP_CONTEXT: source_count},
        "conversionNote": f"{NUMBERLINE_SKIP_NOTE} Grouping skipped for the entire question.",
        "sourceInlineMath": source_count,
        "numberlineSkippedInlineMath": source_count,
        "processableInlineMath": 0,
        "processedInlineMath": 0,
        "groupingErrorInlineMath": 0,
        "groupingErrorGroups": 0,
        "processedGroups": 0,
        "protectedInlineMath": 0,
        "nestedExcluded": 0,
        "outsideLayout": 0,
        "labelIds": [],
    }


def convert_question_html(html_string: str, question_id: Any = "") -> dict[str, Any]:
    """Create a sentence-sized accessibility grouping for one question."""
    html_string = normalize_html_class_attributes(html_string)
    root = parse_html_fragment(html_string)
    controls, nested = select_inline_math(root)
    source_count = len(controls) + len(nested)
    if has_fib_numberline(root):
        return numberline_skip_result(html_string, question_id, source_count)

    protected: list[etree._Element] = []
    protected_reasons: set[str] = set()
    eligible: list[etree._Element] = []
    outside_layout: list[etree._Element] = []

    for control in controls:
        _, reasons = protected_table(control)
        if reasons:
            protected.append(control)
            protected_reasons.update(reasons)
        elif _question_stem(control) is None:
            outside_layout.append(control)
        else:
            eligible.append(control)

    contexts: list[dict[str, Any]] = []
    structured: OrderedDict[int, dict[str, Any]] = OrderedDict()
    direct_by_stem: OrderedDict[int, dict[str, Any]] = OrderedDict()
    for control in eligible:
        stem = _question_stem(control)
        assert stem is not None
        context = _context_for_structured_control(stem, control)
        context_text = _text_with_placeholders(context) if context is not None else ""
        context_complete = context is not None and _local_statement_is_complete(context_text)
        is_calculation_result = context is not None and _looks_like_calculation_result(context_text)
        context_tag = str(context.tag).lower() if context is not None else ""
        table = _nearest_ancestor(control, {"table"})
        empty_table_result = bool(
            context_tag == "tr"
            and not re.sub(r"\[input\]", "", context_text).strip()
            and table is not None
            and _is_calculation_source(_text_with_placeholders(table))
        )
        if context is None or is_calculation_result or empty_table_result or (
            not context_complete and context_tag not in {"tr", "tbody", "table"}
        ):
            direct_by_stem.setdefault(id(stem), {"stem": stem, "members": []})["members"].append(control)
        else:
            entry = structured.setdefault(
                id(context),
                {
                    "context": context,
                    "members": [],
                    "contextType": (
                        "Self-contained Input Context" if context_complete else "Manual Review"
                    ),
                },
            )
            entry["members"].append(control)
    for entry in structured.values():
        context = entry["context"]
        context_controls, _ = select_inline_math(context)
        member_ids = {id(member) for member in entry["members"]}
        contains_other_controls = any(id(control) not in member_ids for control in context_controls)
        should_split = str(context.tag).lower() == "div" and (
            contains_other_controls or (len(entry["members"]) > 1 and bool(context.xpath(".//br")))
        )
        if should_split:
            contexts.extend(_wrap_stem_intervals(context, entry["members"]))
        else:
            contexts.append(entry)
    for entry in direct_by_stem.values():
        contexts.extend(_wrap_stem_intervals(entry["stem"], entry["members"]))

    used_label_ids: list[str] = []
    context_tags: list[str] = []
    context_type_counts: dict[str, int] = OrderedDict()
    grouping_error_inline_math = 0
    grouping_error_groups = 0
    grouping_error_reasons: dict[str, int] = OrderedDict()
    source_semantic_text = _text_with_placeholders(root)
    for group_number, entry in enumerate(contexts, 1):
        context = entry["context"]
        members = entry["members"]
        context_tags.append(str(context.tag).lower())
        context_type = entry.get("contextType", "Manual Review")
        context_type_counts[context_type] = context_type_counts.get(context_type, 0) + len(members)

        # Some structured table rows intentionally carry only a source
        # ``aria-label`` (for example, ``Factor 1``) and no visible text of
        # their own.  Do not replace that valid accessible name with a
        # generated ``aria-labelledby`` reference to an empty row ID.
        context_text = _text_with_placeholders(context, include_image_alt=True)
        visible_context_text = _normalize_text(context_text.replace("[input]", ""))
        has_source_accessible_name = all(
            bool((member.get("aria-label") or "").strip())
            or bool((member.get("aria-labelledby") or "").strip())
            for member in members
        )
        has_semantic_text = any(character.isalnum() for character in visible_context_text)
        if not has_semantic_text and has_source_accessible_name:
            continue
        context_stem = _question_stem(context)
        context_inside_stem = (
            "question-stem-content" not in _class_tokens(context)
            and context_stem is not None
            and all(_question_stem(member) is context_stem for member in members)
        )
        semantic_error_reason = (
            "the context target is not strictly inside the input's question-stem-content"
            if not context_inside_stem
            else "the available context is empty or contains only symbols"
            if not has_semantic_text
            else _incomplete_numeric_scaffold_reason(context_text, source_semantic_text)
        )
        if semantic_error_reason:
            grouping_error_groups += 1
            grouping_error_inline_math += len(members)
            grouping_error_reasons[semantic_error_reason] = (
                grouping_error_reasons.get(semantic_error_reason, 0) + len(members)
            )
            context_type_counts[context_type] -= len(members)
            if context_type_counts[context_type] <= 0:
                del context_type_counts[context_type]
            context_type_counts["Manual Review"] = (
                context_type_counts.get("Manual Review", 0) + len(members)
            )
            if entry.get("generatedWrapper"):
                _unwrap_generated_context(context)
            continue

        existing_id = context.get("id")
        if existing_id:
            label_id = existing_id
        else:
            first_cid = _label_id_base(
                members[0].get("cid") or f"question_{normalize_question_id(question_id)}"
            )
            label_id = _unique_label_id(root, f"{first_cid}_label_{group_number}")
            context.set("id", label_id)
        used_label_ids.append(label_id)
        for member in members:
            member.set("aria-labelledby", label_id)

    if controls and not eligible and protected:
        output_type = "Skipped/Protected Table"
    elif "tr" in context_tags or "tbody" in context_tags or any(
        _nearest_ancestor(control, {"table"}) is not None for control in eligible
    ):
        output_type = "Table/Rows"
    elif "li" in context_tags:
        output_type = "List Item"
    elif "p" in context_tags:
        output_type = "Paragraph Context"
    elif len(contexts) > 1:
        output_type = "Repeated Context Rows"
    else:
        output_type = "Sentence Context"

    context_modes = set(context_type_counts)
    if not controls:
        output_context_type = "No InlineMath"
    elif not eligible and protected and not outside_layout:
        output_context_type = "Skipped/Protected Table"
    elif outside_layout or "Manual Review" in context_modes:
        output_context_type = "Manual Review" if len(context_modes) <= 1 else "Mixed Context"
    elif len(context_modes) == 1:
        output_context_type = next(iter(context_modes))
    elif len(context_modes) > 1:
        output_context_type = "Mixed Context"
    else:
        output_context_type = "Manual Review"

    processed_inline_math = len(eligible) - grouping_error_inline_math
    converted_html = inner_html(root)
    notes = [
        f"Successfully grouped {processed_inline_math} of {len(eligible)} in-scope InlineMath control(s) across {len(contexts) - grouping_error_groups} group(s)."
    ]
    if protected:
        reason_text = ", ".join(f"table.{name}" for name in sorted(protected_reasons))
        notes.append(f"Skipped {len(protected)} InlineMath control(s) inside {reason_text}.")
    if nested:
        notes.append(f"Excluded {len(nested)} nested InlineMath control(s).")
    if outside_layout:
        notes.append(
            f"Left {len(outside_layout)} InlineMath control(s) unchanged outside question-stem-content for manual review."
        )
    if not controls:
        notes = ["no InlineMath control found."]
    elif context_type_counts:
        breakdown = ", ".join(f"{key}: {value}" for key, value in context_type_counts.items())
        notes.append(f"Context types: {breakdown}.")
    if grouping_error_inline_math:
        error_reasons = "; ".join(
            f"{reason} ({count} control(s))" for reason, count in grouping_error_reasons.items()
        )
        notes.append(
            f"Grouping Error: left {grouping_error_inline_math} InlineMath control(s) unchanged because no safe, semantically sufficient non-empty accessible label could be created. Reasons: {error_reasons}."
        )

    return {
        "questionId": normalize_question_id(question_id),
        "convertedQuestionHtml": converted_html,
        "convertedQuestionXml": _question_xml_fragment(converted_html),
        "type": output_type,
        "errorType": "Grouping Error" if grouping_error_inline_math else "",
        "contextType": output_context_type,
        "contextTypeCounts": context_type_counts,
        "conversionNote": " ".join(notes),
        "sourceInlineMath": source_count,
        "numberlineSkippedInlineMath": 0,
        "processableInlineMath": len(eligible),
        "processedInlineMath": processed_inline_math,
        "groupingErrorInlineMath": grouping_error_inline_math,
        "groupingErrorGroups": grouping_error_groups,
        "processedGroups": len(contexts) - grouping_error_groups,
        "protectedInlineMath": len(protected),
        "nestedExcluded": len(nested),
        "outsideLayout": len(outside_layout),
        "labelIds": used_label_ids,
    }


def select_top_level_inline_math(root: etree._Element) -> list[etree._Element]:
    """Select ctype=InlineMath elements that have no ctype ancestor in this root."""
    selected = []
    for element in root.xpath('.//*[@ctype="InlineMath"]'):
        if not element.xpath("ancestor::*[@ctype]"):
            selected.append(element)
    return selected


def select_nested_inline_math(root: etree._Element) -> list[etree._Element]:
    return [
        element
        for element in root.xpath('.//*[@ctype="InlineMath"]')
        if element.xpath("ancestor::*[@ctype]")
    ]


def _normalize_text(value: str) -> str:
    value = value.replace("\xa0", " ")
    value = re.sub(r"[ \t\r\f\v]+", " ", value)
    value = re.sub(r" *\n+ *", "\n", value)
    return value.strip(" \n")


def _visible_text_without_components(element: etree._Element) -> str:
    clone = copy.deepcopy(element)
    for component in clone.xpath('.//*[@ctype]'):
        component.drop_tree()
    for br in clone.xpath(".//br"):
        br.tail = "\n" + (br.tail or "")
    return _normalize_text("".join(clone.itertext()))


def _labelled_text(root: etree._Element, element: etree._Element) -> str:
    labelled_by = element.get("aria-labelledby")
    if not labelled_by:
        return ""
    parts = []
    for label_id in labelled_by.split():
        matches = root.xpath('.//*[@id=$value]', value=label_id)
        if matches:
            parts.append(_visible_text_without_components(matches[0]))
    return _normalize_text(" ".join(filter(None, parts)))


def _semantic_container(element: etree._Element) -> etree._Element:
    for ancestor in element.iterancestors():
        tag = str(ancestor.tag).lower()
        if tag in {"tr", "li", "p", "td", "th"}:
            return ancestor
        if tag == "div" and "question-stem-content" not in (ancestor.get("class") or ""):
            return ancestor
    return element.getparent()


def _text_before_target(container: etree._Element, target: etree._Element) -> str:
    tokens: list[str] = []
    reached_target = False

    def walk(node: etree._Element) -> None:
        nonlocal reached_target
        if reached_target:
            return
        if node is target:
            reached_target = True
            return
        tag = str(node.tag).lower()
        if tag == "br":
            tokens.append("\n")
            return
        if node.text:
            tokens.append(node.text)
        for child in node:
            if reached_target:
                return
            if is_inline_math(child) and child is not target:
                pass
            else:
                walk(child)
            if reached_target:
                return
            if child.tail:
                tokens.append(child.tail)
            if str(child.tag).lower() in BLOCK_TAGS:
                tokens.append("\n")

    walk(container)
    normalized = _normalize_text("".join(tokens))
    if not normalized:
        return ""
    non_empty_lines = [line.strip() for line in normalized.split("\n") if line.strip()]
    return non_empty_lines[-1] if non_empty_lines else ""


def text_for_inline_math(root: etree._Element, element: etree._Element) -> str:
    """Return the existing semantic label or visible text immediately before input."""
    labelled = _labelled_text(root, element)
    if labelled:
        return labelled
    container = _semantic_container(element)
    return _text_before_target(container, element) if container is not None else ""


def outer_html(element: etree._Element) -> str:
    """Return the parsed DOM's outerHTML equivalent."""
    return etree.tostring(element, encoding="unicode", method="html", with_tail=False)


def group_inline_math(html_string: str, question_id: Any = "") -> dict[str, Any]:
    root = parse_html_fragment(html_string)
    inline_math = select_top_level_inline_math(root)
    nested = select_nested_inline_math(root)
    groups: OrderedDict[str, InlineMathGroup] = OrderedDict()

    for element in inline_math:
        group_key = (
            element.get("gid")
            or element.get("qname")
            or element.get("cid")
            or f"inline-math-group-{len(groups) + 1}"
        )
        if group_key not in groups:
            groups[group_key] = InlineMathGroup(
                gid=group_key,
                qname=element.get("qname") or "",
                items=[],
            )
        group = groups[group_key]
        raw_index = element.get("index") or ""
        try:
            item_index = int(raw_index)
        except (TypeError, ValueError):
            item_index = len(group.items) + 1
        group.items.append(
            InlineMathItem(
                index=item_index,
                text=text_for_inline_math(root, element),
                html=outer_html(element),
                cid=element.get("cid") or "",
                qname=element.get("qname") or "",
                sourceIndex=raw_index,
            )
        )

    return {
        "questionId": normalize_question_id(question_id),
        "groups": [asdict(group) for group in groups.values()],
        "topLevelCount": len(inline_math),
        "nestedExcludedCount": len(nested),
    }


def groups_json(result: dict[str, Any]) -> str:
    return json.dumps(result["groups"], ensure_ascii=False, separators=(",", ":"))


def flatten_group_details(
    result: dict[str, Any], source_row: int, resource_code: Any = ""
) -> Iterable[dict[str, Any]]:
    for group_order, group in enumerate(result["groups"], 1):
        for item in group["items"]:
            yield {
                "sourceRow": source_row,
                "questionId": result["questionId"],
                "resourceCode": normalize_question_id(resource_code),
                "groupOrder": group_order,
                "gid": group["gid"],
                "qname": group["qname"],
                "itemIndex": item["index"],
                "sourceIndex": item["sourceIndex"],
                "cid": item["cid"],
                "text": item["text"],
                "html": item["html"],
            }
