# Validation

## Structural checks

- No actual `className` attribute remains in converted HTML, ignoring attribute-name case. Verify that each class token is preserved, including when an element originally has both `class` and `className`. Text, comments, scripts and unrelated attribute values are preserved. Decode `convertedQuestionXml` and compare it with the normalized converted HTML. Raw source columns retain their original values.

- Source InlineMath count equals successfully processed, grouping-error, FIB_Numberline skipped, protected, nested-excluded, and outside-layout counts.
- `processableInlineMath` equals successfully processed plus grouping-error controls.
- For every question in a new workbook, verify that a source `FIB_Numberline` widget always produces `Skipped/FIB_Numberline`, including Unchanged questions. The converted HTML must equal the current source HTML after class-attribute normalization and the encoded question XML must represent that same HTML. The row's note starts with `Skip: FIB_Numberline.` after any version prefix, `ErrorType` is blank, and every InlineMath control is counted only in the FIB_Numberline skip count.
- Every processed control has `aria-labelledby`.
- Every generated local context uses one ID; that ID exists exactly once in the same question. Independent answer groups may prepend IDs for a real shared heading or matching source image. All targets stay in the same stem and part, shared targets contain no InlineMath, and the last target contains every input of that local group.
- No generated ID is duplicated.
- Every newly created grouping ID is on a strict descendant of `question-stem-content`, never the stem itself or outside it. Local and shared label targets must belong to the same nearest stem and part as their controls. Reject outside/stem targets even for single-ID labels. Preserve unrelated original IDs. Apply the new check to future conversion/recompute scope, not historical retained results.
- No processed label has empty accessible text.
- Every control classified as `Grouping Error` has no generated empty wrapper/ID or `aria-labelledby` and preserves its source control attributes after class-attribute normalization.
- Every generated label is checked for incomplete numeric scaffolds. A bare starting number with blank sequence slots, or an incomplete equation in a multi-step strategy that omits its instruction, must not be counted as a successful label; it must be expanded safely or classified as `Grouping Error`.
- Every row with grouping errors has `ErrorType = Grouping Error`, a matching control count and reason in `conversionNote`, and appears in `Review_Queue`.
- Rows with `ErrorType = Grouping Error` retain their structural `Type`; use `ContextType = Manual Review` or `Mixed Context` to describe the semantic decision.
- Protected controls inside `table.verticalEquation` or `table.default_style` preserve their source attributes after class-attribute normalization.
- Input order and `cid`, `gid`, `qname`, `index`, `ctype`, and `itype` are preserved.
- The source `questionhtml` and `questionxml` columns remain unchanged.

## Semantic checks

- A self-contained input context does not include an earlier question or instruction unnecessarily.
- A question/answer pattern is evaluated local-first. If the answer sentence already supplies the subject/object, predicate, expected value or unit, relation, and relevant qualifier, a rephrased question is excluded.
- A preceding-context group contains the local input block and the smallest range of related source information needed to explain the answer. Include meaning from a question, instruction, statement, expression, heading or image alternative when it contributes.
- Before recording an insufficient label as a Grouping Error, inspect the source for a sufficient range within the same stem and part. Review cases where the candidate omits related source content. Compare source cells after decoding Excel escapes once from the raw XML.
- Every included preceding block contributes meaning absent from the local block; inclusion based only on DOM order or proximity fails validation.
- For result-style inputs with a separate preceding expression, the accessible label includes the relevant operands and operation.
- When a multiple-choice widget separates a formula from an Exact/result input, one continuous wrapper spans the formula through the result input, including the intervening DOM range.
- A calculation source and its result are never represented by multiple `part_x` label IDs merely because they occupy separate DOM elements.
- Multiple-choice distractors are never treated as one calculation source; ambiguous answer structures remain in `Manual Review`.
- If the local context already contains a complete calculation, no earlier formula or instruction is added.
- Result labels without a safe source expression, and expressions with competing answer choices, appear in `Manual Review` or `Mixed Context`.
- Calculation-source selection works across sibling DOM nodes and `<br>`-separated blocks, and stays within `question-stem-content` and `.part_label` boundaries.
- Independent statements do not share a generated label ID.
- Inputs in one indivisible equation, coordinate, quotient/remainder answer, or place-value statement retain a shared label ID.
- Context does not cross `question-stem-content` or `.part_label` boundaries.
- Similar semantic structures receive the same classification.

## Punctuation-boundary validation

- Every period used as a context boundary must be explainable from its token and surrounding content; a raw `.` search is insufficient.
- Decimal points in numbers such as `1.7`, `3.14`, `0.25`, and `12.5` must remain inside one semantic unit.
- Measurement abbreviations and other abbreviations must remain joined to continuing content (`7 in. [input]`, `Mr. Edson`, `e.g. example`) while still allowing a real boundary when a new sentence follows (`7 in. Find ...`).
- Local-sentence extraction, preceding-question selection, and multi-input partitioning must use the same semantic boundary helper.
- Dataset audits must report rows containing decimal, measurement, abbreviation, identifier, or mathematical period patterns and identify any row whose grouping changed after the rule update.

## Dataset-wide anomaly scans

- Inspect both unresolved controls and existing labels. Check for bare unit labels such as `o’clock`, adjacent equations joined in one label, and separate picture questions merged under a common instruction. A populated label and a structural PASS do not by themselves establish semantic completeness.
- For image-based counts, verify that the selected source range includes the nearest relevant source question or statement before the image through the input. Empty image alternatives do not by themselves fail grouping.
- Review each remaining semantic uncertainty against its source and record a specific reason. Keep protected-table and FIB_Numberline policy skips distinct from unresolved semantic decisions.

- Review all groups containing more than one input.
- Flag unusually long label text as possible over-grouping.
- Flag `Manual Review` and `Mixed Context` rows with their source row numbers.
- Compare group counts and context classifications with the previous version.
- Audit all `Question / Instruction -> answer sentence containing [input]` patterns for redundant preceding content.
- Confirm that conversion fragments such as `7 in. [input]`, place-value answers, and elapsed-time answers retain the instruction or expression needed to define the input.
- Scan result-style contexts for a related preceding calculation and confirm that every selected source appears in the corresponding accessible label.
- Keep statements such as `The product of 4 and 8 is [input]` local without adding a redundant instruction.
- Run known-case regression checks in addition to the general scans. Known cases are tests, not row-specific transformation rules.

## Release gate

A numbered output may be produced when structural checks pass and all remaining semantic uncertainties are explicitly classified as `Manual Review` or `Mixed Context`. A processing case that cannot safely produce a non-empty label may also be released with `ErrorType = Grouping Error` when its controls remain unchanged and the error is fully represented in the summary and review queue. Such controls do not count as successfully grouped. A numbered version is a reviewable iteration and does not imply final correctness.

Before publishing, run the saved-workbook check on the staged Excel file. The versioned builder runs `scripts/verify_saved_workbook.py` after export and writes a `*.saved-validation.json` report. Verify source values and order, exact conversion strings, summary counts and review entries. An incremental output also verifies its recompute list and compares retained cells and styles with the audited baseline workbook.

Incremental validation uses `validate_conversion.py --recomputed-only` for Updated and Added questions and the Unchanged FIB_Numberline skip results. The saved-workbook check independently detects numberline widgets from current source and covers the entire merged file. Record Unchanged skips separately from recomputed questions.
