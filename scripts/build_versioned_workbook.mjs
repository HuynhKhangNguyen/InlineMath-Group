import fs from "node:fs/promises";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath, pathToFileURL } from "node:url";

const artifactToolModule = process.env.INLINEMATH_ARTIFACT_TOOL_ENTRY
  ? await import(pathToFileURL(process.env.INLINEMATH_ARTIFACT_TOOL_ENTRY).href)
  : await import("@oai/artifact-tool");
const { FileBlob, SpreadsheetFile } = artifactToolModule;

const [inputPath, conversionJsonPath, outputPath, previewDir] = process.argv.slice(2);
if (!inputPath || !conversionJsonPath || !outputPath || !previewDir) {
  throw new Error("Usage: node build_versioned_workbook.mjs <input.xlsx> <conversion.json> <output.xlsx> <preview-dir>");
}
const sourceRestoreScript = process.env.INLINEMATH_SOURCE_RESTORE_SCRIPT;
const pythonExecutable = process.env.INLINEMATH_PYTHON_EXECUTABLE;
if (!sourceRestoreScript || !pythonExecutable) {
  throw new Error("Set INLINEMATH_SOURCE_RESTORE_SCRIPT and INLINEMATH_PYTHON_EXECUTABLE so source cell values are restored after export.");
}

const payload = JSON.parse(await fs.readFile(conversionJsonPath, "utf8"));
const incremental = payload.incremental?.files?.baseline ? payload.incremental : null;
const artifactOutputPath = path.join(previewDir, `${path.basename(outputPath)}.artifact.xlsx`);
for (const candidate of [outputPath, artifactOutputPath]) {
  try {
    await fs.access(candidate);
    throw new Error(`Refusing to overwrite existing output: ${candidate}`);
  } catch (error) {
    if (error.code !== "ENOENT") throw error;
  }
}
const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);
const datasetTitle = path.basename(inputPath, path.extname(inputPath));
const dataSheet = workbook.worksheets.getItem(payload.sourceSheet ?? "Data");
const rowCount = payload.rows.length + 1;
const sourceColumnCount = Math.max(...payload.sourceValues.map((row) => row.length));
const outputHeaders = [["convertedQuestionHtml", "convertedQuestionXml", "Type", "ErrorType", "ContextType", "conversionNote",
  ...(incremental?.extraHeaders ?? [])]];
const outputColumnStartIndex = sourceColumnCount;
const outputColumnEndIndex = outputColumnStartIndex + outputHeaders[0].length - 1;
const columnName = (zeroBasedIndex) => {
  let value = zeroBasedIndex + 1;
  let name = "";
  while (value > 0) {
    const remainder = (value - 1) % 26;
    name = String.fromCharCode(65 + remainder) + name;
    value = Math.floor((value - 1) / 26);
  }
  return name;
};
const outputEndColumn = columnName(outputColumnEndIndex);
if (Array.isArray(payload.sourceValues) && payload.sourceValues.length === rowCount) {
  const sourceRange = dataSheet.getRangeByIndexes(0, 0, rowCount, sourceColumnCount);
  sourceRange.values = payload.sourceValues.map((row) => [
    ...row,
    ...Array(Math.max(0, sourceColumnCount - row.length)).fill(null),
  ]);
}
const outputRows = payload.rows.map((row) => [
  row.convertedQuestionHtml,
  row.convertedQuestionXml,
  row.Type,
  row.ErrorType ?? "",
  row.ContextType,
  row.conversionNote,
  ...(row.extraValues ?? []),
]);

const outputRange = dataSheet.getRangeByIndexes(0, outputColumnStartIndex, rowCount, outputHeaders[0].length);
outputRange.values = [...outputHeaders, ...outputRows];
const outputHeaderRange = dataSheet.getRangeByIndexes(0, outputColumnStartIndex, 1, outputHeaders[0].length);
outputHeaderRange.format.fill = "#1F4E78";
outputHeaderRange.format.font = { name: "Arial", size: 10, bold: true, color: "#FFFFFF" };
outputHeaderRange.format.horizontalAlignment = "center";
for (const [offset, width] of [85, 85, 28, 26, 34, 60, ...(incremental?.extraHeaders ?? []).map(() => 20)].entries()) {
  const column = columnName(outputColumnStartIndex + offset);
  dataSheet.getRange(`${column}:${column}`).format.columnWidth = width;
}
if (payload.rows.length) {
  const outputDataRange = dataSheet.getRangeByIndexes(1, outputColumnStartIndex, payload.rows.length, outputHeaders[0].length);
  outputDataRange.format.verticalAlignment = "top";
  outputDataRange.format.wrapText = false;
}
dataSheet.freezePanes.freezeRows(1);

const summarySheet = workbook.worksheets.add("Conversion_Summary");
const metrics = [
  [`${datasetTitle} InlineMath conversion`, payload.version, ""],
  ["Metric", "Value", "Meaning"],
  ["Source rows", payload.summary.sourceRows ?? 0, "Rows read from Data"],
  ["Source InlineMath", payload.summary.sourceInlineMath ?? 0, "ctype or itype InlineMath, including nested controls"],
  ["In-scope InlineMath", payload.summary.processableInlineMath ?? 0, "Eligible controls after protected and layout exclusions"],
  ["Processed InlineMath", payload.summary.processedInlineMath ?? 0, "Controls assigned a non-empty accessible label or retaining a valid source accessible name"],
  ["Grouping Error InlineMath", payload.summary.groupingErrorInlineMath ?? 0, "Controls preserved unchanged and flagged in ErrorType and Review_Queue"],
  ["Grouping Error Questions", payload.errorTypeCounts?.["Grouping Error"] ?? 0, "Rows containing one or more grouping-error controls"],
  ["Semantic groups", payload.summary.processedGroups ?? 0, "Distinct context containers"],
  ["Protected InlineMath", payload.summary.protectedInlineMath ?? 0, "Skipped inside table.verticalEquation or table.default_style"],
  ["FIB_Numberline skipped InlineMath", payload.summary.numberlineSkippedInlineMath ?? 0, "Controls skipped because the question contains FIB_Numberline"],
  ["Nested excluded", payload.summary.nestedExcluded ?? 0, "InlineMath nested inside another InlineMath"],
  ["Outside layout", payload.summary.outsideLayout ?? 0, "Controls outside question-stem-content"],
  ["Parse errors", payload.summary.parseErrors ?? 0, "Rows retained for manual review"],
];
const contextRows = Object.entries(payload.contextTypeCounts ?? {}).map(([name, value]) => [
  `ContextType: ${name}`,
  value,
  "Source rows",
]);
const summaryRows = [...metrics, ...contextRows];
if (incremental) {
  for (const name of ["Updated", "Added", "Deleted", "Unchanged"]) {
    summaryRows.push([`${name} questions`, incremental.counts[name.toLowerCase()], "Source audit"]);
  }
  summaryRows.push([
    "FIB_Numberline skips in Unchanged", incremental.numberlineSkipUnchangedKeys.length,
    "Unchanged questions marked Skip without grouping",
  ]);
  if (incremental.requestedRepairKeys?.length) {
    summaryRows.push(["Additional repaired questions", incremental.repairKeys.length, "Unchanged source questions explicitly selected for repair"]);
  }
}
summarySheet.getRange(`A1:C${summaryRows.length}`).values = summaryRows;
summarySheet.getRange("A1:C1").format.font = { name: "Arial", size: 14, bold: true, color: "#1F1F1F" };
summarySheet.getRange("A2:C2").format.fill = "#1F4E78";
summarySheet.getRange("A2:C2").format.font = { name: "Arial", size: 10, bold: true, color: "#FFFFFF" };
summarySheet.getRange("A:A").format.columnWidth = 36;
summarySheet.getRange("B:B").format.columnWidth = 14;
summarySheet.getRange("C:C").format.columnWidth = 65;
summarySheet.getRange(`B3:B${summaryRows.length}`).format.numberFormat = "#,##0";
summarySheet.showGridLines = false;

const reviewRows = payload.rows
  .filter((row) => row.ErrorType === "Grouping Error" ||
    ["Manual Review", "Mixed Context", "Skipped/FIB_Numberline"].includes(row.ContextType))
  .map((row) => [row.excelRow, row.questionId, row.Type, row.ErrorType ?? "", row.ContextType, row.conversionNote]);
const reviewSheet = workbook.worksheets.add("Review_Queue");
reviewSheet.getRange(`A1:F${reviewRows.length + 1}`).values = [
  ["sourceRow", "questionId", "Type", "ErrorType", "ContextType", "conversionNote"],
  ...reviewRows,
];
reviewSheet.getRange("A1:F1").format.fill = "#1F4E78";
reviewSheet.getRange("A1:F1").format.font = { name: "Arial", size: 10, bold: true, color: "#FFFFFF" };
reviewSheet.getRange("A:A").format.columnWidth = 12;
reviewSheet.getRange("B:B").format.columnWidth = 18;
reviewSheet.getRange("C:C").format.columnWidth = 28;
reviewSheet.getRange("D:D").format.columnWidth = 34;
reviewSheet.getRange("D:D").format.columnWidth = 26;
reviewSheet.getRange("E:E").format.columnWidth = 34;
reviewSheet.getRange("F:F").format.columnWidth = 80;
reviewSheet.freezePanes.freezeRows(1);
reviewSheet.showGridLines = false;

workbook.recalculate();
const checks = [];
for (const [sheetId, range] of [
  ["Conversion_Summary", `A1:C${summaryRows.length}`],
  ["Review_Queue", `A1:E${reviewRows.length + 1}`],
  [dataSheet.name, `${columnName(outputColumnStartIndex)}1:${outputEndColumn}${Math.min(rowCount, 6)}`],
]) {
  const check = await workbook.inspect({
    kind: "table",
    sheetId,
    range,
    include: "values,formulas",
    tableMaxRows: 10,
    tableMaxCols: 23,
    maxChars: 8000,
  });
  checks.push(check.ndjson);
}
const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
  options: { useRegex: true, maxResults: 100 },
  summary: "final formula error scan",
});
checks.push(errors.ndjson);

await fs.mkdir(previewDir, { recursive: true });
for (const [sheetName, range, fileName] of [
  ["Conversion_Summary", `A1:C${summaryRows.length}`, `conversion-summary-${payload.version}.png`],
  ["Review_Queue", `A1:E${reviewRows.length + 1}`, `review-queue-${payload.version}.png`],
  [dataSheet.name, `${columnName(outputColumnStartIndex)}1:${outputEndColumn}${Math.min(rowCount, 6)}`, `data-output-${payload.version}.png`],
]) {
  const preview = await workbook.render({ sheetName, range, scale: 1, format: "png" });
  await fs.writeFile(path.join(previewDir, fileName), new Uint8Array(await preview.arrayBuffer()));
}

await fs.mkdir(path.dirname(outputPath), { recursive: true });
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(artifactOutputPath);
const restoreScript = incremental
  ? fileURLToPath(new URL("./restore_incremental_workbook.py", import.meta.url))
  : sourceRestoreScript;
execFileSync(pythonExecutable, [restoreScript, inputPath, artifactOutputPath, outputPath, conversionJsonPath], { stdio: "inherit" });
const savedVerifier = fileURLToPath(new URL("./verify_saved_workbook.py", import.meta.url));
execFileSync(pythonExecutable, [savedVerifier, outputPath, conversionJsonPath,
  path.join(previewDir, `${path.basename(outputPath)}.saved-validation.json`)], { stdio: "inherit" });
await fs.writeFile(path.join(previewDir, `verification-${payload.version}.ndjson`), checks.join("\n"), "utf8");
console.log(JSON.stringify({ outputPath, summary: payload.summary, typeCounts: payload.typeCounts }));
