# InlineMath agent rules

## Ownership

- Control center uses `$inline-math-control-center`; file workers use `$inline-math-grouping-worker`.
- Keep one worker chat per exact primary input file. Reuse that chat for subsequent jobs on the file. Baselines belong to its manifest. Workers never dispatch other agents/chats.
- Control center resolves paths, scope, locks and completion. Only the worker interprets question HTML, converts, validates and publishes. Do not duplicate its semantic review or helper implementation in control center.
- Read `WORKFLOW.md` once for execution and model policy. Default writer: `gpt-6-luna` / `medium`; compare audit: `gpt-6-luna` / `low`. User overrides win. `xhigh` is opt-in, not the default.

## Scope and locks

- One active reader/writer job per dataset. Different datasets may run concurrently when requested. Different input versions of one dataset run sequentially.
- Shared engine/rules/scripts/tests/skills maintenance is global-exclusive; no file worker runs during installation/validation.
- File workers never modify shared files. Report reusable defects with minimal evidence as `BLOCKED_SHARED_RULE_CHANGE`.
- Configuration maintenance does not authorize dataset recompute or changing existing output.

## Data invariants

- Never overwrite input or previous output. Resolve exact numeric versions, never modified time; publish to a new numbered destination.
- Match by `questionuid`, falling back to complete unique `questionid` only with evidence. Preserve source fields, control order, behavior and answer metadata.
- Every question with `FIB_Numberline` always skips grouping. Keep protected-table and other exclusions distinct from unresolved eligible controls.
- Targeted/incremental work preserves unrelated conversion data and user edits; declare required numberline skip exceptions separately.
- All grouping IDs must be on descendants inside the matching `question-stem-content`, never on the stem itself or outside it. This is a future-processing rule; do not migrate old outputs.
- No administrator privileges.

## Completion

- Use existing deterministic tools and hash-bound checkpoints. Reuse valid completed stages; do not rerun for reassurance.
- Structural PASS does not prove semantic correctness. Review meaning once for recomputed questions; list remaining uncertainty honestly.
- Required semantic/structural/saved-file checks and publication must pass before completion. Control center checks the compact final contract and receipt, not a second full conversion audit.
