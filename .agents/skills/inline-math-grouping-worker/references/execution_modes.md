# Execution modes

Read only the matching section. Shared execution/checkpoint/model policy is in project `WORKFLOW.md`.

## `full-compute`

1. `python scripts/convert_workbook.py <input.xlsx> <payload.json> --version vN`.
2. Run `scripts/validate_conversion.py <payload.json> <validation.json>`. Review recomputed questions once using packets. Inspect complete source for uncertain contexts and correct only affected results. Do not rerun the project regression suite unless shared code/rules/dependencies changed.
3. With Spreadsheets skill/runtime, use `scripts/build_versioned_workbook.mjs <input.xlsx> <payload.json> <staged.xlsx> <preview-dir>`. Configure its existing artifact runtime, Python and source-restoration env vars once. Preserve actual source-column count; append conversion columns after source.
4. Check preview and builder's saved-validation report; verify source/baseline unchanged and publish new numbered output. Save final contract/receipt.

## `compare-audit`

1. Use `$inline-math-data-compare` in read-only mode; run existing `compare_question_data.py` with report path.
2. Match verified UID/ID, compare all source fields unless explicitly limited. Return Updated/Added/Deleted/Unchanged, row moves, schema and line-ending differences.
3. No grouping, export or semantic model review. Do not read full HTML differences unless a semantic explanation is requested or necessary to explain an actual change.

## `incremental-update`

1. Use compare skill: full-field audit PASS and exact source/baseline hashes, including user-edited baseline output.
2. `python scripts/convert_incremental.py <new-input.xlsx> <baseline-output.xlsx> <audit.json> <payload.json> --version vN`.
3. `python scripts/validate_conversion.py <payload.json> <validation.json> --recomputed-only`. Review only Updated/Added semantic results; preserve Unchanged conversion exactly. Mandatory FIB_Numberline skips apply to the merged output and are recorded separately in `numberlineSkipUnchangedKeys`.
4. Export with existing builder/restoration; inspect saved-file report for source, retained values/styles and `Data_Change`. Publish only after gates pass; save checkpoint/contract.

## `targeted-fix`

1. Use explicit UID/row allowlist and fix type, actual user-edited baseline, current source and shared hashes. If only DOM boundary correction is requested, preserve semantic classification.
2. Use an existing supported targeted entrypoint that preserves unrelated results. Do not full-convert/select or reuse a previous batch's hard-coded row transformation. If no reusable capability supports this baseline/fix, report the specific missing capability for shared maintenance.
3. Packet review and semantic/structural checks cover the allowlist; independently verify whole-file source/retained-cell preservation. FIB_Numberline always skip, with any out-of-allowlist policy exceptions listed separately.
4. Existing export/restore/saved-check path, new numbered destination, final receipt. Existing unrelated review cases are retained, not silently repaired or counted as new failures.
