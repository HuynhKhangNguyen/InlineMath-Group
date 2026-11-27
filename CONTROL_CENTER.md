# InlineMath control center

## Workspace

- Processing workspace: `C:\Users\khang.nguyen-huynh\Workspace\InlineMath-Grouping`
- Canonical control project: this `InlineMath-Grouping` project
- Shared rules: `GOAL.md`, `RULES.md`, `VALIDATION.md` in the processing workspace

## Operations

| Operation | Worker behavior | Writes output |
|---|---|---|
| `full-compute` | Process one new input completely | Yes |
| `compare-audit` | Compare new input with its preceding version | No |
| `incremental-update` | Recompute only Updated/Added and merge | Yes |
| `targeted-fix` | Change only an explicit row/UID allowlist | Yes |

## Dispatch policy

Each requested primary input file gets its own worker chat. The exact `inputPath` identifies the file. The worker uses that same chat for the full job, including any audit, recompute, validation and publication. Baseline files are references in the job. Different versions of the same dataset get separate chats and run in sequence. The control center validates paths and collisions, dispatches independent jobs and reports their results.

Execution/model policy is maintained in `WORKFLOW.md`. Default writer: `gpt-6-luna` / `medium`; compare audit: `/ low`. `xhigh` requires an explicit user request. Apply settings on the next actual dispatch, reuse the file worker and its valid checkpoints; control center does not duplicate semantic review.

The user can request a batch in plain language, for example:

```text
Chạy song song:
- full-compute PostPreTest_G3_v3
- compare-audit PIM27DP-4126_IB_G4_v4 với v3
- incremental-update Fluency_Practice_G3-5_v2 từ output v1
```

## Batch ledger

Only the control center updates this table. Worker chats must not edit this file.

| Job ID | Dataset | Operation | Input | Output/report | Thread | Status | Validation |
|---|---|---|---|---|---|---|---|
| batch-20261104-pimk5m295-full-v1 | PIMK5M-295_G1_IDP | full-compute | `PIMK5M-295_G1_IDP\input\PIMK5M-295_G1_IDP_v1.xlsx` | `PIMK5M-295_G1_IDP\output\PIMK5M-295_G1_IDP_v1_output_v1.xlsx` | 01a1a4b7-018e-7583-a863-88910f8e2399 | NEEDS_REVIEW | PASS |
| batch-20261104-pimk5m301-full-v1 | PIMK5M-301_G1_Benchmark_Assessments | full-compute | `PIMK5M-301_G1_Benchmark_Assessments\input\PIMK5M-301_G1_Benchmark_Assessments_v1.xlsx` | `PIMK5M-301_G1_Benchmark_Assessments\output\PIMK5M-301_G1_Benchmark_Assessments_v1_output_v1.xlsx` | 01a1a4b7-3278-7e90-9ab8-c9dbf6268f6e | NEEDS_REVIEW | PASS |

| batch-20261104-pimk5m302-full-v1 | PIMK5M-302_G1_IDA (requested as PIMK5M-302_G1) | full-compute | `PIMK5M-302_G1_IDA\input\PIMK5M-302_G1_IDA_v1.xlsx` | `PIMK5M-302_G1_IDA\output\PIMK5M-302_G1_IDA_v1_output_v1.xlsx` | 01a1a55a-7e8d-7871-94c2-3e57b08d4857 | NEEDS_REVIEW | PASS |
| batch-20261104-pimk5m304-full-v1 | PIMK5M-304_G1_Diagnostic_Pretest | full-compute | `PIMK5M-304_G1_Diagnostic_Pretest\input\PIMK5M-304_G1_Diagnostic_Pretest_v1.xlsx` | `PIMK5M-304_G1_Diagnostic_Pretest\output\PIMK5M-304_G1_Diagnostic_Pretest_v1_output_v1.xlsx` | 01a1a55a-afd0-7f53-8c38-ca191eace173 | NEEDS_REVIEW | PASS |
| batch-20261104-pimk5m311-full-v1 | PIMK5M-311_GK_Benchmark_Assessments | full-compute | `PIMK5M-311_GK_Benchmark_Assessments\input\PIMK5M-311_GK_Benchmark_Assessments_v1.xlsx` | `PIMK5M-311_GK_Benchmark_Assessments\output\PIMK5M-311_GK_Benchmark_Assessments_v1_output_v1.xlsx` | 01a1a55a-e3e6-7241-a117-3b38128784c7 | NEEDS_REVIEW | PASS |
| batch-20261104-pimk5m316-full-v1 | PIMK5M-316_GK_IDA | full-compute | `PIMK5M-316_GK_IDA\input\PIMK5M-316_GK_IDA_v1.xlsx` | `PIMK5M-316_GK_IDA\output\PIMK5M-316_GK_IDA_v1_output_v1.xlsx` | 01a1a55b-34a9-7550-bfde-282c5fa4a8c5 | NEEDS_REVIEW | PASS |
| batch-20261104-pimk5m322-full-v1 | PIMK5M-322_GK_IDP | full-compute | `PIMK5M-322_GK_IDP\input\PIMK5M-322_GK_IDP_v1.xlsx` | `PIMK5M-322_GK_IDP\output\PIMK5M-322_GK_IDP_v1_output_v1.xlsx` | 01a1a55b-6a4e-7f80-a2e8-b22eefbca81b | NEEDS_REVIEW | PASS |

| batch-20261104-pimk5m305-full-v1 | PIMK5M-305_G1_Chapter_Pretest | full-compute | `PIMK5M-305_G1_Chapter_Pretest\input\PIMK5M-305_G1_Chapter_Pretest_v1.xlsx` | `PIMK5M-305_G1_Chapter_Pretest\output\PIMK5M-305_G1_Chapter_Pretest_v1_output_v1.xlsx` | 01a1a5c5-3eea-7603-b656-90e041562a6e | NEEDS_REVIEW | PASS |
| batch-20261104-pimk5m306-full-v1 | PIMK5M-306_G1_Post_Test | full-compute | `PIMK5M-306_G1_Post_Test\input\PIMK5M-306_G1_Post_Test_v1.xlsx` | `PIMK5M-306_G1_Post_Test\output\PIMK5M-306_G1_Post_Test_v1_output_v1.xlsx` | 01a1a5c5-8c97-7330-b7b5-7f04bf2d68fe | NEEDS_REVIEW | PASS |
| batch-20261104-pimk5m307-full-v1 | PIMK5M-307_G1_CPT | full-compute | `PIMK5M-307_G1_CPT\input\PIMK5M-307_G1_CPT_v1.xlsx` | `PIMK5M-307_G1_CPT\output\PIMK5M-307_G1_CPT_v1_output_v1.xlsx` | 01a1a5c5-f1cb-7f30-8ed9-d98c8620e443 | NEEDS_REVIEW | PASS |

| batch-20261104-pimk5m305-targeted-fix-v2 | PIMK5M-305_G1_Chapter_Pretest | targeted-fix | `PIMK5M-305_G1_Chapter_Pretest\input\PIMK5M-305_G1_Chapter_Pretest_v1.xlsx` | `PIMK5M-305_G1_Chapter_Pretest\output\PIMK5M-305_G1_Chapter_Pretest_v1_output_v2.xlsx` | 01a1a5f4-6f0e-78b0-b0a6-7c787412648d | NEEDS_REVIEW | PASS |
| batch-20261104-pimk5m306-targeted-fix-v2 | PIMK5M-306_G1_Post_Test | targeted-fix | `PIMK5M-306_G1_Post_Test\input\PIMK5M-306_G1_Post_Test_v1.xlsx` | `PIMK5M-306_G1_Post_Test\output\PIMK5M-306_G1_Post_Test_v1_output_v2.xlsx` | 01a1a5f4-9315-74a0-82db-b2666fab9d3c | NEEDS_REVIEW | PASS |
| batch-20261104-pimk5m307-targeted-fix-v2 | PIMK5M-307_G1_CPT | targeted-fix | `PIMK5M-307_G1_CPT\input\PIMK5M-307_G1_CPT_v1.xlsx` | `PIMK5M-307_G1_CPT\output\PIMK5M-307_G1_CPT_v1_output_v2.xlsx` | 01a1a5f4-c94c-7ba2-ac95-e350d4353797 | NEEDS_REVIEW | PASS |

| batch-20261105-pimk5m295-grouping-error-fix-v2 | PIMK5M-295_G1_IDP | targeted-fix | `PIMK5M-295_G1_IDP\input\PIMK5M-295_G1_IDP_v1.xlsx` | `PIMK5M-295_G1_IDP\output\PIMK5M-295_G1_IDP_v1_output_v2.xlsx` | 01a1aa07-fc9a-7fd3-9d6e-83cd38bd08a2 | NEEDS_REVIEW | PASS |
| batch-20261105-pimk5m301-grouping-error-fix-v2 | PIMK5M-301_G1_Benchmark_Assessments | targeted-fix | `PIMK5M-301_G1_Benchmark_Assessments\input\PIMK5M-301_G1_Benchmark_Assessments_v1.xlsx` | `PIMK5M-301_G1_Benchmark_Assessments\output\PIMK5M-301_G1_Benchmark_Assessments_v1_output_v2.xlsx` | 01a1aa08-5b29-7943-ae72-906b421e8586 | NEEDS_REVIEW | PASS |
| batch-20261105-pimk5m302-grouping-error-fix-v2 | PIMK5M-302_G1_IDA | targeted-fix | `PIMK5M-302_G1_IDA\input\PIMK5M-302_G1_IDA_v1.xlsx` | `PIMK5M-302_G1_IDA\output\PIMK5M-302_G1_IDA_v1_output_v2.xlsx` | 01a1aa09-2062-78d2-8cd0-bc12fb179399 | NEEDS_REVIEW | PASS |
| batch-20261105-pimk5m304-grouping-error-fix-v2 | PIMK5M-304_G1_Diagnostic_Pretest | targeted-fix | `PIMK5M-304_G1_Diagnostic_Pretest\input\PIMK5M-304_G1_Diagnostic_Pretest_v1.xlsx` | `PIMK5M-304_G1_Diagnostic_Pretest\output\PIMK5M-304_G1_Diagnostic_Pretest_v1_output_v2.xlsx` | 01a1aa08-a267-7101-bd0e-4a2dc282c8bc | NEEDS_REVIEW | PASS |
| batch-20261105-pimk5m316-grouping-error-fix-v2 | PIMK5M-316_GK_IDA | targeted-fix | `PIMK5M-316_GK_IDA\input\PIMK5M-316_GK_IDA_v1.xlsx` | `PIMK5M-316_GK_IDA\output\PIMK5M-316_GK_IDA_v1_output_v2.xlsx` | 01a1aa09-e762-7b81-be66-ed3281b3d27a | NEEDS_REVIEW | PASS |
| batch-20261105-pimk5m322-grouping-error-fix-v2 | PIMK5M-322_GK_IDP | targeted-fix | `PIMK5M-322_GK_IDP\input\PIMK5M-322_GK_IDP_v1.xlsx` | `PIMK5M-322_GK_IDP\output\PIMK5M-322_GK_IDP_v1_output_v2.xlsx` | 01a1aa0b-a862-7901-9118-c3baa4033b9f | NEEDS_REVIEW | PASS |

Terminal statuses: `DONE`, `NEEDS_REVIEW`, `BLOCKED`, `FAILED`, `BLOCKED_SHARED_RULE_CHANGE`.

## Shared-rule defect

When a worker finds a reusable grouping defect, it stops before publish and returns evidence. A shared-rule update is handled as a separate exclusive task, validated against the project regression suite, then affected file jobs are rerun from their original manifests.
