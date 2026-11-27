# InlineMath execution policy

## Context and ownership

- Worker alone owns question decisions and processing. Control center sends a manifest and checks the final contract; no duplicate HTML analysis or parallel helper implementation.
- Read instructions once per hash; on resume, read checkpoint and changed dependencies only. Worker reads GOAL/RULES/VALIDATION, control center does not preload them. Read only the matching execution-mode section.
- Keep raw HTML, payloads and verbose logs in files. Query exact tools and source ranges; narrow truncated queries. Batch independent reads. Reuse existing scripts instead of reimplementing them.
- Preserve one chat per file. Checkpoints avoid more history reads; they do not erase already accumulated runtime context. Do not create replacement chats without instruction.

## Model and effort

| Work | Default |
|---|---|
| Control center | Configured model; request low effort on future dispatch where supported |
| Compare audit, filesystem/report checks | `gpt-6-luna`, `low`; script does the computation |
| Full/incremental/targeted semantic decisions | `gpt-6-luna`, `medium` |
| A demonstrated ambiguous semantic case | `high`, restricted to affected rows |
| `xhigh` | Only when explicitly requested by user |

Apply manifest model/thinking through supported dispatch tools, not just prompt text. Correct legacy settings on the next real dispatch; do not wake idle workers for configuration. Escalation identifies the missing semantic relationship and affected rows. No automatic model switching or extra reviewer agents.

## One execution cycle

1. **Preflight:** exact paths, allowlist, collision/locks, source/baseline/engine/rule hashes; save manifest and source evidence in job staging. Configuration maintenance does not run datasets.
2. **Prepare:** existing entrypoint once. Audit is script-only; incremental converts Updated/Added; targeted converts allowlist only. Never full-convert then select. Always apply declared FIB_Numberline skips.
3. **Review:** structural validation, then `scripts/job_context.py packet`. Review meaning once for every recomputed question in batches; summaries first, full source as needed. Flags are triage, not semantic PASS. Inspect complete relevant stem/part before Grouping Error. Keep policy skips and retained review separate.
4. **Export:** correct affected results; rerun invalidated checks only. Existing builder/restoration, required preview and saved-workbook check cover source and retained cells.
5. **Publish:** verify source/baseline unchanged; new exact destination, no overwrite. Published hash equals verified staged hash. Store final contract and receipt.

Missing reusable capability becomes one shared maintenance task while workers are inactive, not duplicated job-local redesign in both chats.

## Checkpoints and stop conditions

`scripts/job_context.py` uses only the Python standard library; it never edits a workbook or grants validation PASS.

```text
python scripts/job_context.py checkpoint <state.json> --job-id <id> --phase <phase> --artifact manifest=<path> --artifact input=<path> --artifact engine=<path> --artifact rules=<path> --artifact goal=<path> --artifact validation_rules=<path> ...
python scripts/job_context.py status <state.json>
python scripts/job_context.py packet <payload.json> <new-packet-directory> [--rows 2,3,4] [--batch-size 8]
```

Checkpoint meaningful stages with all dependencies: source/baseline, engine/rules/scripts, scope/manifest, payload, semantic decisions and actual reports. SHA-256 receipts detect changed/missing files; phase/hash match does not certify PASS. Changed dependency invalidates downstream stages. A later saved-file hash change requires data-diff inspection, not immediate full recompute.

- One focused correction attempt per failed check in a cycle; persistent failure gets evidence and honest review/blocker status, not endless replanning or false PASS.
- Full regression suite for shared implementation/rule changes, not every file; reuse only with matching tested hashes/dependencies. Operation-specific and saved-file checks remain required.
- Stop after required gates pass. No second model audit, repeated verifier or preview without new evidence/change.

## Monitoring and final report

- `wait_threads`: persisted cursor, compact results, bounded wait up to 60 seconds. No repeated history reads or steering unchanged progress. Status updates need not interrupt workers.
- Stalled/failed: latest status + relevant checkpoint/log tail, then one actionable instruction. Resume last valid stage.
- Final JSON contract in a file; return brief counts, status, validation and output/receipt paths. Control checks once. No duplicate calculations/narrative.
- Usage reporting, when available, is scoped to job/turn. Cached input and reasoning are subsets, not extra tokens. No money estimates or savings claims without measurement.
