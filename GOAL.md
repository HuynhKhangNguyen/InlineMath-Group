# Goal

## Minimum Sufficient Semantic Context

For every eligible InlineMath input, generate the smallest accessible context that still lets a screen-reader user understand:

1. what the input represents;
2. which subject or object it belongs to;
3. what kind of answer, unit, attribute, or value is expected; and
4. the purpose of the input without ambiguity.

If the transformation cannot safely create a non-empty, semantically sufficient accessible label for an in-scope control, do not create or retain an inadequate wrapper or `aria-labelledby` target. Preserve that control unchanged, mark its row with `ErrorType = Grouping Error`, include it in the review queue, and report it separately from successfully grouped controls. This includes local numeric sequences that omit the continuation task and incomplete equations whose meaning depends on an omitted multi-step strategy. This classification exposes a processing failure; it does not count as a completed grouping.

The selected context must be complete, minimal, unambiguous, and semantically relevant. DOM proximity and visual layout are supporting signals only. The decision order is:

```text
Semantic meaning -> User comprehension -> Minimum sufficient context -> DOM/visual structure
```

Prefer an independent local context for each input. Group multiple inputs only when they share source information required for interpretation, form one mathematical expression, or depend on one another for meaning.

Independent answers that share a heading may reference that real heading together with one local context ID per group. A matching source image may also supply context. Keep these references within the same stem and part, and preserve each group's independent input membership.

Evaluate the local sentence or semantic block before reading preceding content. Preceding content is eligible only when it adds information required for comprehension. A question that merely repeats or rephrases a complete local answer sentence must stay outside the accessible context.

For an input that represents a calculation result, also preserve its source expression when the local context only names the result. `Quotient: [input]` does not identify the operands; `24 ÷ 6` plus the label does. If the operands and operation already appear with the input, do not expand the context.

When unrelated content separates a needed formula from the local result label, identify the smallest semantic start, then use one continuous DOM range from that start through the input. Intervening nodes may remain inside the wrapper when continuity is required; they are not treated as separate label fragments.

Generated wrappers must keep an adjacent `<br>` and `<span class="half-line-padding">` pair together. If a boundary falls between them, correct only that DOM boundary while preserving the existing grouping, IDs, and `aria-labelledby`.

Sentence and context boundaries are semantic decisions. Do not treat every `.` as an end of sentence: first inspect the token and its neighbors so decimal numbers (`1.7`), measurements (`7 in.`), abbreviations (`Mr.`, `e.g.`), identifiers, and mathematical expressions remain intact when the content continues. An abbreviation may still terminate a sentence when the following semantic content starts a new unit.

Do not rewrite source wording. Preserve question behavior, answer metadata, control order, table/list structure, and the original `questionhtml` and `questionxml` columns.

Normalize HTML `className` attributes to `class` in converted output before class-based layout and grouping decisions. Apply the same normalization to skipped and retained converted output, preserving all class tokens and the original source columns.

Grouping IDs must be assigned only to strict descendants inside the relevant `question-stem-content`, including shared source targets. Never assign a new grouping ID to the stem itself or an outside ancestor/wrapper. Use an inner wrapper when the whole stem supplies context. Apply this to future processing only; preserve old outputs and unrelated source IDs.
