# Worker job contract

Prompt chứa skill invocation, một manifest và checkpoint path nếu resume. Không copy rules/HTML/tool manuals.

```yaml
jobId: <stable id>
dataset: <name>
operation: full-compute | compare-audit | incremental-update | targeted-fix
model: gpt-6-luna
thinking: medium # low for compare-audit; user override recorded explicitly
workspaceRoot: <absolute root>
inputPath: <absolute primary input>
baselineInputPath: <absolute path or null>
baselineOutputPath: <absolute path or null>
outputPath: <absolute new numbered path or null for audit>
outputVersion: <vN or null>
targetRowsOrIds: <explicit list for targeted, otherwise null>
allowSharedRuleChanges: false
checkpointPath: <absolute job-local path>
```

Control checks exact existing sources, preceding natural input version for compare, destination collision, explicit targeted scope, one assignment per input and dataset/global locks. Reuse the input's worker chat. Apply manifest model/thinking with supported tool overrides on the next actual dispatch; do not wake an idle worker just for configuration.

Worker stores this final JSON contract and returns a short summary and its path:

```yaml
jobId: <same id>
dataset: <same dataset>
operation: <same operation>
status: DONE | NEEDS_REVIEW | BLOCKED | FAILED | BLOCKED_SHARED_RULE_CHANGE
model: <actual model>
thinking: <actual effort>
engineSha256: <hash>
sourceSha256: <hash>
ruleHashes: <GOAL/RULES/VALIDATION hashes>
outputOrReport: <absolute path or null>
outputSha256: <hash or null>
checkpointPath: <absolute path>
validationReports: <paths to actual semantic/structural/saved reports>
counts: <scope/recompute/eligible/labelled/errors/skips/retained-review>
validation: PASS | FAIL | NOT_RUN
reviewRowsOrIds: <list; split recomputed versus retained review>
sharedFilesChanged: false
notes: <short factual text>
```

Receipts bind the exact artifacts; a checkpoint phase alone does not prove validation PASS. Control center checks this contract and receipts once, without repeating worker computation.
