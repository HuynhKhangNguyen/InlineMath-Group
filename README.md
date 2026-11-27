# InlineMath Grouping

Recovered local project for reviewing and grouping top-level InlineMath inputs in CLA Excel workbooks.

## Project layout

```text
InlineMath-Grouping/
├── CLA_G3/
│   ├── input/CLA_G3.xlsx
│   ├── output/CLA_G3_output_v1.xlsx
│   └── review/CLA_G3_v1_data.json
├── examples/
├── scripts/
├── src/
├── tests/
├── README.md
├── GOAL.md
├── VALIDATION.md
└── RULES.md
```

## Run the extraction

Create a Python environment and install the two runtime dependencies:

```powershell
python -m pip install -r requirements.txt
python scripts/extract_review_data.py `
  CLA_G3/input/CLA_G3.xlsx `
  CLA_G3/review/CLA_G3_review_data.json
```

The extractor reads the original `Data` sheet without modifying it. The generated JSON contains one output record per source question, flattened item details, and summary totals.

Versioned conversion outputs use `CLA_G3_output_v{n}.xlsx`. Names such as `reviewed`, `latest`, or `final` are not used because every generated workbook remains subject to review.

Run a versioned conversion with:

```powershell
python scripts/convert_workbook.py `
  CLA_G3/input/CLA_G3.xlsx `
  CLA_G3/review/CLA_G3_v3_data.json `
  --version v3
```

## Test

```powershell
python -m unittest discover -s tests -v
```

## Incremental update

Generate a PASS audit of all source fields with `inline-math-data-compare`. Use the last workbook reviewed for this dataset as the baseline. Run from the project root with writable staging paths:

```powershell
python scripts/convert_incremental.py new-input.xlsx baseline-output.xlsx audit.json staging/v4.json --version v4
python scripts/validate_conversion.py staging/v4.json staging/v4-grouping-validation.json --recomputed-only
node scripts/build_versioned_workbook.mjs new-input.xlsx staging/v4.json staging/dataset_output_v4.xlsx staging/preview
```

Set `INLINEMATH_PYTHON_EXECUTABLE` to the Python runtime and `INLINEMATH_SOURCE_RESTORE_SCRIPT` to the project copy of `scripts/restore_source_cells.py`. The builder uses `@oai/artifact-tool`, or the module path configured in `INLINEMATH_ARTIFACT_TOOL_ENTRY`.

Inspect the preview and `*.saved-validation.json` before copying a new numbered output to the dataset folder. Filter `Data_Change` to find Updated, Added or Unchanged questions. Deleted questions are counted in the summary. FIB_Numberline is always skipped in the new output. Unchanged numberline questions keep their audit status and are listed separately in `numberlineSkipUnchangedKeys`.

See `RULES.md` for the recovered behavior and the few conservative assumptions required because the original source repository was not present in chat history.
