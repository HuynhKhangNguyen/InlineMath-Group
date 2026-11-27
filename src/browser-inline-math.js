/** Browser/jQuery helpers recovered from the original InlineMath discussions. */
(function (global, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory;
  } else {
    global.InlineMathGrouping = factory(global.jQuery);
  }
})(typeof window !== "undefined" ? window : globalThis, function createInlineMathGrouping($) {
  "use strict";

  function requireJQuery() {
    if (!$) throw new Error("InlineMathGrouping requires jQuery");
  }

  function decodeHtmlOnce(value) {
    const textarea = document.createElement("textarea");
    textarea.innerHTML = value || "";
    return textarea.value;
  }

  function getDecodedHtmlFromXml(xmlString) {
    if (!xmlString) return "";
    const xmlDoc = new DOMParser().parseFromString(xmlString, "text/xml");
    if (xmlDoc.querySelector("parsererror")) return "";
    const question = xmlDoc.querySelector("question");
    return question ? decodeHtmlOnce(question.textContent) : "";
  }

  function findTopLevelInlineMath($root) {
    requireJQuery();
    return $root.find("[ctype='InlineMath']").filter(function () {
      return $(this).parentsUntil($root, "[ctype]").length === 0;
    });
  }

  function groupByStableKey($root) {
    requireJQuery();
    const ordered = [];
    const byKey = new Map();
    findTopLevelInlineMath($root).each(function () {
      const $item = $(this);
      const key =
        $item.attr("gid") ||
        $item.attr("qname") ||
        $item.attr("cid") ||
        `inline-math-group-${ordered.length + 1}`;
      if (!byKey.has(key)) {
        const group = { gid: key, qname: $item.attr("qname") || "", items: [] };
        byKey.set(key, group);
        ordered.push(group);
      }
      const group = byKey.get(key);
      const sourceIndex = $item.attr("index") || "";
      group.items.push({
        index: Number(sourceIndex) || group.items.length + 1,
        text: ($item.attr("aria-label") || "").trim(),
        html: this.outerHTML,
        cid: $item.attr("cid") || "",
        qname: $item.attr("qname") || "",
        sourceIndex,
      });
    });
    return ordered;
  }

  return { decodeHtmlOnce, getDecodedHtmlFromXml, findTopLevelInlineMath, groupByStableKey };
});
