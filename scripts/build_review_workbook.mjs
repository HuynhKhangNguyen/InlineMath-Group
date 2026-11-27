import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const [inputPath, reviewJsonPath, outputPath, previewDir] = process.argv.slice(2);
if (!inputPath || !reviewJsonPath || !outputPath || !previewDir) {
  throw new Error("Usage: node build_review_workbook.mjs <input.xlsx> <review.json> <output.xlsx> <preview-dir>");
}

const payload = JSON.parse(await fs.readFile(reviewJsonPath, "utf8"));
const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);

const outputSheet = workbook.worksheets.add("CLA_G3_Output");
const detailSheet = workbook.worksheets.add("Groups_Detail");
const summarySheet = workbook.worksheets.add("Review_Summary");

const outputHeaders = [
  "sourceRow",
  "questionId",
  "resourceCode",
  "questionNumber",
  "groupCount",
  "itemCount",
  "status",
  "groupsJson",
];
const detailHeaders = [
  "sourceRow",
  "questionId",
  "resourceCode",
  "groupOrder",
  "gid",
  "qname",
  "itemIndex",
  "sourceIndex",
  "cid",
  "text",
  "html",
];

function safeCellValue(value) {
  if (typeof value !== "string") return value;
  if (value.startsWith("=") || /^#(?:REF!|DIV\/0!|VALUE!|NAME\?|N\/A|NUM!|NULL!|SPILL!|CALC!)$/.test(value)) {
    return `'${value}`;
  }
  return value;
}

const outputRows = payload.outputRows.map((row) =>
  outputHeaders.map((key) => safeCellValue(row[key] ?? null)),
);
const detailRows = payload.detailRows.map((row) =>
  detailHeaders.map((key) => safeCellValue(row[key] ?? null)),
);
outputSheet.getRange("A1").write([outputHeaders, ...outputRows]);
detailSheet.getRange("A1").write([detailHeaders, ...detailRows]);

const summaryRows = [
  ["Metric", "Value", "Meaning"],
  ["Source rows", payload.summary.sourceRows, "Rows read from Data, excluding the header"],
  ["Questions with top-level InlineMath", payload.summary.questionsWithTopLevelInlineMath, "Questions included in grouping"],
  ["Questions without top-level InlineMath", payload.summary.questionsWithoutTopLevelInlineMath, "Rows retained with an empty groups array"],
  ["Groups", payload.summary.groups, "Stable groups in first-seen order"],
  ["Top-level InlineMath", payload.summary.topLevelInlineMath, "Selected ctype=InlineMath elements"],
  ["Nested InlineMath excluded", payload.summary.nestedInlineMathExcluded, "InlineMath elements with a ctype ancestor"],
  ["Parse errors", payload.summary.parseErrors, "Rows that could not be parsed"],
];
summarySheet.getRange("A2:C9").values = summaryRows;
summarySheet.getRange("A1:C1").merge();
summarySheet.getRange("A1").values = [["CLA_G3 InlineMath review"]];

const headerFill = "#1F4E78";
const headerFont = { name: "Arial", size: 10, bold: true, color: "#FFFFFF" };
const bodyFont = { name: "Arial", size: 10, color: "#222222" };

for (const [sheet, columns, rowCount] of [
  [outputSheet, outputHeaders.length, outputRows.length + 1],
  [detailSheet, detailHeaders.length, detailRows.length + 1],
]) {
  sheet.showGridLines = false;
  sheet.freezePanes.freezeRows(1);
  sheet.freezePanes.freezeColumns(2);
  const used = sheet.getRangeByIndexes(0, 0, rowCount, columns);
  used.format.font = bodyFont;
  used.format.verticalAlignment = "top";
  const header = sheet.getRangeByIndexes(0, 0, 1, columns);
  header.format.fill = headerFill;
  header.format.font = headerFont;
  header.format.horizontalAlignment = "center";
  header.format.verticalAlignment = "center";
  header.format.borders = { preset: "inside", style: "thin", color: "#FFFFFF" };
  header.format.rowHeight = 24;
}

outputSheet.tabColor = "#1F4E78";
detailSheet.tabColor = "#5B9BD5";
summarySheet.tabColor = "#1F4E78";

outputSheet.getRange("A:A").format.columnWidth = 11;
outputSheet.getRange("B:C").format.columnWidth = 18;
outputSheet.getRange(`C2:C${outputRows.length + 1}`).format.numberFormat = "000000000";
outputSheet.getRange("D:F").format.columnWidth = 14;
outputSheet.getRange("G:G").format.columnWidth = 25;
outputSheet.getRange("H:H").format.columnWidth = 85;
outputSheet.getRange(`H2:H${outputRows.length + 1}`).format.wrapText = false;

detailSheet.getRange("A:A").format.columnWidth = 11;
detailSheet.getRange("B:C").format.columnWidth = 18;
detailSheet.getRange(`C2:C${detailRows.length + 1}`).format.numberFormat = "000000000";
detailSheet.getRange("D:H").format.columnWidth = 13;
detailSheet.getRange("I:I").format.columnWidth = 38;
detailSheet.getRange("J:J").format.columnWidth = 42;
detailSheet.getRange("K:K").format.columnWidth = 80;
detailSheet.getRange(`J2:K${detailRows.length + 1}`).format.wrapText = false;

summarySheet.showGridLines = false;
summarySheet.getRange("A1:C9").format.font = bodyFont;
summarySheet.getRange("A1:C1").format.font = { name: "Arial", size: 14, bold: true, color: "#1F1F1F" };
summarySheet.getRange("A1:C1").format.rowHeight = 25;
summarySheet.getRange("A2:C2").format.fill = headerFill;
summarySheet.getRange("A2:C2").format.font = headerFont;
summarySheet.getRange("A2:C2").format.horizontalAlignment = "center";
summarySheet.getRange("A:A").format.columnWidth = 40;
summarySheet.getRange("B:B").format.columnWidth = 14;
summarySheet.getRange("C:C").format.columnWidth = 55;
summarySheet.getRange("A3:A9").format.font = { name: "Arial", size: 10, bold: true, color: "#222222" };
summarySheet.getRange("B3:B9").format.numberFormat = "#,##0";
summarySheet.getRange("A2:C9").format.verticalAlignment = "center";
summarySheet.getRange("A2:C9").format.borders = { preset: "outside", style: "thin", color: "#B4C7E7" };

workbook.recalculate();

const checks = [];
for (const [sheetId, range] of [
  ["Review_Summary", "A1:C9"],
  ["CLA_G3_Output", "A1:H8"],
  ["Groups_Detail", "A1:K8"],
  ["Data", "A1:S4"],
]) {
  const check = await workbook.inspect({
    kind: "table",
    sheetId,
    range,
    include: "values,formulas",
    tableMaxRows: 10,
    tableMaxCols: 19,
    maxChars: 5000,
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
  ["Review_Summary", "A1:C9", "review-summary.png"],
  ["CLA_G3_Output", "A1:H12", "cla-output.png"],
  ["Groups_Detail", "A1:K12", "groups-detail.png"],
  ["Data", "A1:S5", "data.png"],
]) {
  const preview = await workbook.render({ sheetName, range, scale: 1, format: "png" });
  await fs.writeFile(`${previewDir}/${fileName}`, new Uint8Array(await preview.arrayBuffer()));
}

await fs.mkdir(path.dirname(outputPath), { recursive: true });
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
await fs.writeFile(`${previewDir}/verification.ndjson`, checks.join("\n"), "utf8");
console.log(JSON.stringify({ outputPath, summary: payload.summary }));
