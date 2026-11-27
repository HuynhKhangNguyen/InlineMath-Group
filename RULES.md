# InlineMath grouping rules

## Current goal

When an InlineMath input receives focus, its accessible context must include the input and the smallest existing source content needed to explain it. Decide by meaning. A question, instruction, declarative statement, calculation, table or row heading, or meaningful image alternative can supply that context.

### Normalize HTML class attributes

Before layout, part-boundary, protected-table or grouping decisions, convert actual HTML `className` attributes to `class`, ignoring attribute-name case. Apply this throughout each question's converted HTML. If an element already has `class`, merge its existing tokens followed by the `className` tokens, preserving token order and removing duplicates. Preserve each class token's spelling and case.

This normalization also applies to protected tables, questions without InlineMath, FIB_Numberline skip results, and retained converted content in a new incremental output. Preserve text, comments, scripts and other attribute values containing the word `className`. Keep the original source columns. Encode the same normalized HTML in `convertedQuestionXml` and verify that no `className` attribute remains in converted markup. For a targeted correction, regroup only rows explicitly selected for grouping after layout normalization. A DOM-only correction retains existing groups and classifications.

### Skip questions with FIB_Numberline

If any element in the source `questionhtml` has `ctype` or `itype` equal to `FIB_Numberline` (ignoring case and surrounding whitespace), skip grouping for the entire question. Apply this before table protection, nested control exclusion, and layout classification. An occurrence in text, a comment, or another attribute does not trigger this rule.

Keep the source HTML in `convertedQuestionHtml`, applying only the class-attribute normalization above, and use the same HTML in the encoded `convertedQuestionXml`. Preserve any source IDs and ARIA attributes. Set both `Type` and `ContextType` to `Skipped/FIB_Numberline`, leave `ErrorType` blank, and start the note with `Skip: FIB_Numberline.` Include the question in `Review_Queue` with the skip status. Count all its InlineMath controls only in the numberline skip bucket, including controls elsewhere in the question and nested controls.

Apply this rule to every FIB_Numberline question in a new output, including questions marked `Unchanged` by the data audit. Use the current source for the skip result instead of carrying over a grouped baseline result. Keep `Data_Change = Unchanged` and record these skips separately from the recompute list. Existing workbook versions are not rewritten.

### Other questions

Skip an InlineMath control when any ancestor table has the class token `verticalEquation` or `default_style`. Preserve the protected table without adding wrappers or ARIA attributes.

Every generated workbook is a numbered working version: `*_output_v1.xlsx`, `*_output_v2.xlsx`, and so on. Do not use `reviewed`, `latest`, or `final` in generated output names.

## Layout container

1. Only group InlineMath controls inside an element whose class contains the exact token `question-stem-content`.
2. The nearest `question-stem-content` ancestor is the default layout container. Content outside that container must never be pulled into the accessible group.
3. If the layout contains `.part_label`, treat the matching part section as the layout container. A part section starts at its `.part_label` marker and ends immediately before the next `.part_label`, or at the end of `question-stem-content` when there is no following marker.
4. Never pull context across a part boundary. `Part A` content cannot label an input in `Part B`.
5. An InlineMath outside `question-stem-content`, or one whose part boundary cannot be determined safely, remains unchanged and is marked for manual review.

### Grouping ID placement

Every ID created for grouping, including wrapper/local-context and shared heading/image IDs, must be on a strict descendant of the relevant `question-stem-content`. Do not assign a grouping ID to the `question-stem-content` element itself, an ancestor, an outer wrapper/table row, a sibling stem, or content outside that stem. All targets used for a newly grouped control must remain inside its nearest stem and matching part.

If the context covers the entire stem, create an appropriate inner wrapper around its content; do not place the ID on the stem or wrap the stem from outside. If valid inner grouping cannot be produced while preserving DOM and meaning, leave the affected control unchanged and report the reason. Existing source IDs unrelated to grouping remain untouched. This rule applies to future conversions/recomputed scope; it does not migrate retained results or authorize rewriting old workbooks.

## Context around an input

An image or line break between the explanatory source and an input does not end their semantic relationship. When the input asks for a count, take the nearest relevant count question or statement before the image through the input. An empty image alternative alone does not justify leaving an otherwise explainable input ungrouped.

Use the nearest source that explains this particular input. For example, `Enter the number you added.` and `Enter the number in all.` define two independent answer groups. A complete equation such as `[input] + [input] = [input]` forms one group. Repeated independent picture questions, result rows, equations and time offsets each receive their own context. Keep a source relation such as `One hour after 2 o’clock` with its answer instead of labelling the answer only `o’clock`.

1. Start with the smallest sentence or semantic row containing the InlineMath and its following unit or quantitative noun.
2. Decide whether that local sentence is understandable by itself when the input receives focus.
3. Treat the local block as complete when it identifies the input's meaning, subject/object, expected unit/attribute/value when needed, and purpose without ambiguity. Recognize declarative clauses both before and after the input, including `Dan jogged [input] miles last week.` and `[input] students chose dove.`
4. A complete statement such as `He has [input] cards left.` already supplies its subject, relationship, input, and unit. Do not prepend an earlier question.
5. A fragment such as `[input] centimeters`, `$ [input]`, or `[input] students` requires additional meaning. Identify the nearest related source content that supplies what is missing.
6. Before adding preceding content, verify that it contributes semantic information absent from the local block. If it only repeats or rephrases the same subject, action, quantity, unit, relation, or time, do not add it.
7. When preceding context is required, take the smallest continuous DOM range that contains the missing information and the input. Examples include starting at `Enter the number in all.` when it identifies the expected total, or starting at a related expression when it identifies the operands.
8. Keep the preceding context, the input, and its suffix in DOM reading order.
9. Stop searching at the current layout-container boundary, including a `.part_label` boundary.

## Sentence and punctuation boundaries

1. A period is a boundary signal, not a boundary decision. Evaluate the token containing it, the characters on both sides, the following token, and the DOM/semantic block before splitting context.
2. Never split at a decimal separator such as `1.7`, `3.14`, `0.25`, or `12.5`; the period is part of the number. Apply the same protection to compact identifiers and mathematical tokens where the period is internal.
3. Do not split at an abbreviation period when the semantic content continues, including measurement units such as `in.`, `ft.`, `yd.`, `oz.`, and `lb.`, titles such as `Mr.` or `Dr.`, and multi-period abbreviations such as `e.g.` or `i.e.`.
4. An abbreviation can also be the final punctuation of a sentence. For example, `The length is 7 in. Find the area.` has a boundary after `in.` because a new sentence follows. The rule is therefore contextual: abbreviation detection and sentence-boundary detection are separate decisions.
5. Use semantic punctuation helpers for local-sentence extraction, preceding-question lookup, semantic sentence scanning, and splitting between adjacent inputs. Do not use a character-only rule such as `"." -> End of sentence`.
6. When the punctuation evidence remains ambiguous, preserve the larger local semantic unit and classify the result for review rather than cutting context solely because a period was found.

Store the context decision separately from the structural `Type` in a `ContextType` column:

- `Self-contained Input Context`: the sentence containing the input is understandable by itself.
- `Preceding Context Required`: the local input fragment omits required meaning or calculation source, and the nearest applicable preceding content was included.
- `Mixed Context`: a source row contains both decisions.
- `Skipped/FIB_Numberline`: grouping was skipped for the entire source question.
- `Skipped/Protected Table`: all InlineMath controls are protected.
- `Manual Review`: context could not be determined safely or a control is outside `question-stem-content`.
- `No InlineMath`: the source row has no InlineMath control.

The workbook also includes a separate `ErrorType` column. Leave it blank for rows without a processing error. Set it to `Grouping Error` when one or more in-scope controls cannot be assigned a safe, non-empty, semantically sufficient accessible label. A non-empty label can still be insufficient: examples include a starting number followed by blank sequence slots without the instruction to continue, and incomplete equations that depend on an omitted multi-step strategy. Keep the structural `Type` and semantic `ContextType` values intact; do not replace them with the error status.

For a `Grouping Error`, leave only the affected control(s) and their source DOM range unchanged. Do not add or retain an empty or semantically inadequate wrapper, generated ID, or `aria-labelledby`. Other valid groups in the same question should still be processed. Include the error count and reason in `conversionNote`, and include the row in `Review_Queue`. `ContextType` remains `Manual Review` when all groups need review, or `Mixed Context` when the row also contains successfully classified groups.

Review each unresolved control against its complete source stem before classifying it. A failed first candidate, missing image alternative, table layout, imperative verb list, or existing `Manual Review` flag does not establish that the source lacks usable context. Record the specific missing relationship when a control remains unresolved. Keep explicit FIB_Numberline and protected-table skips distinct from semantic review. If a question contains both an unresolved table and a clear answer sentence after it, process the clear answer separately.

Do not treat every equation or input list as erroneous. Classify a local scaffold as `Grouping Error` only when its own text omits required task meaning and the needed continuation/strategy instruction is outside the selected label. If that instruction is already inside the label, validate the label normally.

## Semantic grouping decision

When independent answer rows need the same source heading, keep one local context ID per answer group and reference the shared source ID before that local ID in `aria-labelledby`. A matching table-column image with meaningful alt text may supply another source ID. Each referenced ID exists once, all references stay in the same stem and part, and shared targets contain no InlineMath controls. The local target contains exactly the controls of its own group. Use actual source content, preserving its wording, images and DOM order. This is a source association for independent answers that would otherwise be merged by overlapping continuous ranges. Keep a calculation and its dependent result in one continuous group as specified below.

Evaluate each input independently before considering a multi-input group.

Keep inputs in one group when they form one indivisible semantic block, for example:

- coordinates such as `A([input], [input])`;
- quotient and remainder in one division statement;
- place-value decompositions such as `[input] hundreds and [input] tens`;
- one equation where a later input depends on an earlier missing value;
- a single sentence where separating the controls would remove the relationship between them.

Split inputs when each resulting block remains understandable, including:

- separate equations joined by `OR`;
- repeated rows such as `Range`, `Median`, and `Mean`;
- separate complete sentences in the same DOM block;
- separate result statements such as `Apples = [input]` and `Oranges = [input]`;
- separate questions or answer statements sharing the same `qname`, `gid`, parent element, or visual block.

Do not group controls merely because they share a question, parent, line, `qname`, `gid`, or nearby DOM position.

## Preceding-context decision

Use local context alone when it identifies the subject and expected answer, such as `Dwayne plays [input] games of pickleball.`

Apply this decision in order:

1. select the nearest local sentence or semantic block;
2. test its semantic completeness without considering preceding DOM siblings;
3. inspect preceding content only if the local block is incomplete;
4. include preceding content only when it adds required meaning rather than repeating the local clause.

Add preceding context when the local block only supplies a value, unit, symbol, incomplete phrase, or a result label that omits its calculation source. Search backward within the current layout section for the nearest related question, instruction, statement, expression, heading or source image alternative. Choose by what it contributes. When the first generated label is empty or too short to explain the answer, inspect the source for a better range before assigning `Grouping Error`. Empty image alternatives and a count of words cannot establish whether a label is sufficient.

### Calculation-result dependency

Treat calculation provenance as part of semantic completeness. A result label can identify what kind of value the input represents without identifying how that value is obtained.

1. Check whether the local context already contains the operands and operation or formula. If it does, keep the local context only.
2. If the local context is a result label or answer scaffold and lacks its source calculation, search backward in the same `question-stem-content` and `.part_label` section for the nearest related calculation block.
3. Confirm the relationship from both sides: the local result structure and a nearby expression with operands and an operation. Do not rely only on words such as `Quotient` or `Sum`; the expression, operands, order, and nearby answer structure establish the dependency.
4. Include the calculation source and local result label in reading order. Start at the expression itself; omit earlier instructions or descriptions when they add no required meaning. Wrap the continuous DOM range from that start through the input in one group, even when unrelated nodes such as a choice widget lie between them.
5. A result label with no identifiable source, or a source with competing answer choices, is `Manual Review`.
6. Do not split one semantic context into multiple `part_x` IDs solely because the source and input were separate DOM siblings. Semantic reasoning selects the start; DOM structure determines the continuous wrapper range.

Examples:

```text
24 ÷ 6 = [input]
```

The source and result are together. Do not add an earlier `Find the quotient` instruction.

```text
Solve the problem. Use the correct operation. 24 ÷ 6
Quotient: [input]
```

The context starts at `24 ÷ 6` and includes `Quotient: [input]`. Earlier instructions do not add calculation meaning.

```text
Quotient: [input]
```

Without a related source expression in the current layout section, classify the result for manual review instead of calling the label self-contained.

Keep a local statement such as `The product of 4 and 8 is [input].` self-contained because its factors and operation are already present.

For example, when `37 + 16` is followed by an Estimate multiple-choice widget and then `Exact: [input]`, start at `37 + 16` and wrap the continuous range through `Exact: [input]` with one ID. If the nearby arithmetic source is itself a multiple-choice option set rather than a single calculation, leave the result for manual review.

Do not stop at an intermediate value such as `7 in.` when an earlier instruction is required to explain what must be calculated. Do not cross a `.part_label` boundary.

## DOM boundary preservation

When a generated wrapper would otherwise be inserted between adjacent `<br>` and `<span class="half-line-padding">` elements, move the wrapper boundary before the pair so both elements remain inside the same wrapper. Preserve the existing semantic group, wrapper ID, input membership, and `aria-labelledby`; this is a structural boundary correction, not a new context decision.

Use the smallest boundary change required. Do not recompute grouping or classification, expand the semantic context, split the group into multiple IDs, or alter unrelated questions during a targeted correction. The equivalent valid boundary may be placed after the complete pair when that preserves the existing group more closely.

Examples:

```text
How long is the ribbon? [input] centimeters
```

The question is required because `[input] centimeters` is incomplete.

```text
He has [input] cards left.
```

The local sentence is complete, so no earlier question is added.

```text
How many miles did Dan jog last week?
Dan jogged [input] miles last week.
```

The answer sentence already identifies the subject, action, value, unit, and time. The question is a rephrasing and is excluded.

```text
Find the number of 1/2 inches equal to each measure.
7 in. [input]
```

The local fragment does not state what the input represents. The instruction adds required meaning and is included.

The rules above define the current conversion behavior. The baseline below records stable input and ordering requirements recovered from the earlier implementation.

## Confirmed baseline

1. Read each source row in input order.
2. Use `questionhtml` as the conversion source. Write the converted HTML to `convertedQuestionHtml` and an encoded `<question>` fragment to `convertedQuestionXml`.
3. Detect both `[ctype="InlineMath"]` and `[itype="InlineMath"]`. Exclude only a control nested inside another detected InlineMath control.
4. Preserve the first-seen group order and DOM item order.
5. Use `questionid`, with `questionId` as a supported fallback in JSON workflows.
6. Preserve the parsed element `outerHTML` in each item.
7. Build accessible context only from existing source content. Do not invent or rewrite question wording.
8. Preserve the source `questionxml` and `questionhtml` columns. Store transformations in versioned output columns.
9. Invalid or missing question content must not stop the whole batch; report the row and continue.
10. Decode Excel OOXML string escapes once from the underlying XML before evaluating HTML. Treat encoded CR (`_x000D_`) as a line break and preserve an escaped literal (`_x005F_x000D_`) as literal text. Keep source cell values unchanged in the workbook.

The legacy review baseline contained 1,038 source rows, 1,024 questions with top-level `ctype="InlineMath"`, 1,167 selected controls, and 1 nested control excluded. Current conversion counts also include eligible `itype="InlineMath"` controls.

## Recovered schema

```json
{
  "questionId": "1954603",
  "groups": [
    {
      "gid": "a1",
      "qname": "a1",
      "items": [
        {
          "index": 1,
          "text": "8 ÷ 4 =",
          "html": "<div ctype=\"InlineMath\" ...></div>",
          "cid": "...",
          "qname": "a1",
          "sourceIndex": ""
        }
      ]
    }
  ]
}
```

## Conservative recovery assumptions

- Group key precedence is `gid`, then `qname`, then `cid`, then a generated stable key. This preserves the historical `gid` rule and matches CLA_G3, where top-level `ctype="InlineMath"` elements use a shared `qname` instead of `gid`.
- If `index` is absent, use the 1-based DOM order within the group. Keep the original value separately as `sourceIndex`.
- Prefer existing `aria-labelledby` text. Otherwise, extract visible text immediately before the InlineMath element within the nearest semantic row/container.
- The standalone review output is a baseline for human review. A future conversion step may wrap semantic rows, create stable wrapper IDs, and apply `aria-labelledby`, but it must be reviewed separately because that rewrites source XML.

## Legacy browser selector

```javascript
const $inlineMath = $labelElement
  .find("[ctype='InlineMath']")
  .filter(function () {
    return $(this).parentsUntil($labelElement, "[ctype]").length === 0;
  });
```
