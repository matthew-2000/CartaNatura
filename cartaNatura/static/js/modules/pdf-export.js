function getJsPdfConstructor() {
  return window.jsPDF || window.jspdf?.jsPDF || null;
}

function addMetricCard(doc, { x, y, width, height, label, value }) {
  doc.setDrawColor(224, 229, 225);
  doc.setFillColor(249, 247, 242);
  doc.roundedRect(x, y, width, height, 4, 4, "FD");
  doc.setFontSize(9);
  doc.setTextColor(98, 108, 102);
  doc.text(label.toUpperCase(), x + 4, y + 6);
  doc.setFontSize(16);
  doc.setTextColor(22, 38, 31);
  const lines = doc.splitTextToSize(value, width - 8);
  doc.text(lines, x + 4, y + 15);
}

function addSectionTitle(doc, title, x, y) {
  doc.setFontSize(16);
  doc.setTextColor(22, 38, 31);
  doc.text(title, x, y);
}

function ensureSpace(doc, cursorY, requiredHeight) {
  const pageHeight = doc.internal.pageSize.getHeight();
  if (cursorY + requiredHeight <= pageHeight - 18) {
    return cursorY;
  }
  doc.addPage();
  return 20;
}

function addScenarioComparisonTable(doc, {
  summary,
  priceOptions,
  selectedPrice,
  cursorY,
  buildEconomicScenarioRows,
  formatCurrency,
  formatRoundedNumber,
}) {
  const rows = buildEconomicScenarioRows(summary, priceOptions, selectedPrice);
  if (!rows.length) {
    return cursorY;
  }

  cursorY = ensureSpace(doc, cursorY, 18 + rows.length * 9);
  addSectionTitle(doc, "Confronto scenari economici", 14, cursorY);
  cursorY += 9;

  doc.setFontSize(8);
  doc.setTextColor(98, 108, 102);
  doc.text("Scenario", 14, cursorY);
  doc.text("Prezzo", 98, cursorY);
  doc.text("Valore stimato", 132, cursorY);
  doc.text("Stato", 178, cursorY, { align: "right" });
  cursorY += 4;
  doc.setDrawColor(224, 229, 225);
  doc.line(14, cursorY, 196, cursorY);
  cursorY += 6;

  for (const row of rows) {
    cursorY = ensureSpace(doc, cursorY, 10);
    doc.setFontSize(9);
    doc.setTextColor(22, 38, 31);
    const scenarioLines = doc.splitTextToSize(row.label, 78);
    doc.text(scenarioLines, 14, cursorY);
    doc.text(`${formatRoundedNumber(row.price)} EUR/tCO2`, 98, cursorY);
    doc.text(formatCurrency(row.value), 132, cursorY);
    doc.text(row.selected ? "Selezionato" : "", 178, cursorY, { align: "right" });
    cursorY += Math.max(8, scenarioLines.length * 5);
  }

  return cursorY + 3;
}

export async function generatePdfReport({
  summary,
  intersectedMunicipalities,
  selectedPrice,
  calculatedValue,
  priceOptions = [],
  mapElement,
  analysisUtils,
}) {
  const JsPdf = getJsPdfConstructor();
  if (!JsPdf || !window.domtoimage) {
    throw new Error("Generazione PDF non disponibile.");
  }

  const {
    buildEconomicScenarioRows,
    deriveSummaryMetrics,
    formatCurrency,
    formatRoundedNumber,
  } = analysisUtils;
  const doc = new JsPdf();
  const derivedMetrics = deriveSummaryMetrics(summary);

  const title = "Report Carta della Natura";
  const pageWidth = doc.internal.pageSize.getWidth();
  doc.setFontSize(22);
  doc.setTextColor(22, 38, 31);
  doc.text(title, 14, 24);
  doc.setFontSize(10);
  doc.setTextColor(98, 108, 102);
  doc.text("Analisi GIS, assorbimento annuo stimato e valorizzazione forestale", 14, 31);

  const mapImage = await window.domtoimage.toPng(mapElement);
  doc.addImage(mapImage, "PNG", 14, 38, 108, 88);

  addMetricCard(doc, {
    x: 128,
    y: 38,
    width: 68,
    height: 22,
    label: "CO2 annua stimata",
    value: `${formatRoundedNumber(summary.totalCo2)} t`,
  });
  addMetricCard(doc, {
    x: 128,
    y: 64,
    width: 68,
    height: 22,
    label: "Superficie",
    value: `${formatRoundedNumber(derivedMetrics.totalHectares)} ha`,
  });
  addMetricCard(doc, {
    x: 128,
    y: 90,
    width: 68,
    height: 22,
    label: "Categoria prevalente",
    value: derivedMetrics.topCategory?.label || "-",
  });

  addSectionTitle(doc, "Ripartizione della vegetazione", 14, 138);
  doc.setFontSize(11);
  let cursorY = 147;
  for (const item of summary.items) {
    doc.setTextColor(22, 38, 31);
    doc.text(item.label, 14, cursorY);
    doc.text(`${formatRoundedNumber(item.hectares)} ha`, 176, cursorY, { align: "right" });
    doc.setFillColor(234, 237, 233);
    doc.roundedRect(14, cursorY + 2, 162, 2.8, 1, 1, "F");
    const width = Math.max((item.hectares / Math.max(derivedMetrics.totalHectares, 1)) * 162, 5);
    const rgb = hexToRgb(item.color);
    doc.setFillColor(rgb.r, rgb.g, rgb.b);
    doc.roundedRect(14, cursorY + 2, width, 2.8, 1, 1, "F");
    cursorY += 12;
  }

  cursorY += 2;
  doc.text(`Assorbimento annuo stimato: ${formatRoundedNumber(summary.totalCo2)} t CO2`, 14, cursorY);
  cursorY += 12;

  if (selectedPrice) {
    doc.text(`Prezzo selezionato: ${selectedPrice} EUR/t`, 14, cursorY);
    cursorY += 6;
  }

  if (Number.isFinite(Number(calculatedValue))) {
    doc.text(`Valore stimato: ${formatCurrency(calculatedValue)}`, 14, cursorY);
    cursorY += 8;
  }

  cursorY = addScenarioComparisonTable(doc, {
    summary,
    priceOptions,
    selectedPrice,
    cursorY: cursorY + 6,
    buildEconomicScenarioRows,
    formatCurrency,
    formatRoundedNumber,
  });

  doc.addPage();
  doc.setFontSize(18);
  doc.setTextColor(22, 38, 31);
  doc.text("Comuni interessati", 14, 20);
  doc.setFontSize(10);
  doc.setTextColor(98, 108, 102);
  doc.text("Comuni compresi nell'area analizzata", 14, 26);
  const municipalitiesText = intersectedMunicipalities.length
    ? `I comuni interessati sono: ${intersectedMunicipalities.join(", ")}`
    : "Nessun comune interessato.";
  const lines = doc.splitTextToSize(municipalitiesText, 178);
  for (let index = 0; index < lines.length; index += 1) {
    doc.setTextColor(22, 38, 31);
    doc.text(lines[index], 14, 40 + index * 7);
  }

  doc.save("carta-natura-report.pdf");
}

function hexToRgb(hexColor) {
  const normalized = hexColor.replace("#", "");
  const safe = normalized.length === 3
    ? normalized.split("").map((char) => `${char}${char}`).join("")
    : normalized;

  const value = Number.parseInt(safe, 16);

  return {
    r: (value >> 16) & 255,
    g: (value >> 8) & 255,
    b: value & 255,
  };
}
