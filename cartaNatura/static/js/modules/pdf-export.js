const PAGE = Object.freeze({
  width: 210,
  height: 297,
  margin: 14,
  contentWidth: 182,
});

const COLORS = Object.freeze({
  forest: [23, 79, 64],
  forestMid: [34, 106, 85],
  forestSoft: [230, 240, 235],
  earth: [184, 90, 63],
  gold: [201, 157, 69],
  ink: [24, 35, 30],
  soft: [95, 109, 101],
  muted: [133, 146, 139],
  paper: [255, 255, 255],
  warm: [249, 248, 244],
  line: [222, 228, 223],
});

let activePdfObjectUrl = null;
const MAP_CAPTURE_TIMEOUT_MS = 10000;

function getJsPdfConstructor() {
  return window.jsPDF || window.jspdf?.jsPDF || null;
}

function setText(doc, color = COLORS.ink, size = 10, style = "normal") {
  doc.setTextColor(...color);
  doc.setFontSize(size);
  doc.setFont("helvetica", style);
}

function drawBrandMark(doc, x, y, size = 13) {
  doc.setFillColor(...COLORS.gold);
  doc.roundedRect(x, y, size, size, 2.5, 2.5, "F");
  setText(doc, COLORS.paper, 8, "bold");
  doc.text("GIS", x + size / 2, y + size / 2 + 1.2, { align: "center" });
}

function drawPageHeader(doc, section, subtitle = "") {
  doc.setFillColor(...COLORS.forest);
  doc.rect(0, 0, PAGE.width, 28, "F");
  drawBrandMark(doc, PAGE.margin, 7, 13);
  setText(doc, COLORS.paper, 12, "bold");
  doc.text("Carta Natura", 31, 13.5);
  setText(doc, [195, 218, 208], 6.5, "bold");
  doc.text("SISTEMA INFORMATIVO TERRITORIALE", 31, 18.2);
  setText(doc, COLORS.paper, 10, "bold");
  doc.text(section, PAGE.width - PAGE.margin, 12.5, { align: "right" });
  if (subtitle) {
    setText(doc, [195, 218, 208], 6.5, "normal");
    doc.text(subtitle, PAGE.width - PAGE.margin, 18, { align: "right" });
  }
}

function drawSectionHeading(doc, title, y, kicker = "") {
  if (kicker) {
    setText(doc, COLORS.forestMid, 6.5, "bold");
    doc.text(kicker.toUpperCase(), PAGE.margin, y);
    y += 5;
  }
  setText(doc, COLORS.ink, 15, "bold");
  doc.text(title, PAGE.margin, y);
  doc.setDrawColor(...COLORS.gold);
  doc.setLineWidth(0.8);
  doc.line(PAGE.margin, y + 4, PAGE.margin + 18, y + 4);
  return y + 11;
}

function drawMetric(doc, { x, y, width, label, value, note = "", accent = COLORS.forest }) {
  doc.setDrawColor(...COLORS.line);
  doc.setFillColor(...COLORS.warm);
  doc.roundedRect(x, y, width, 27, 2.5, 2.5, "FD");
  doc.setFillColor(...accent);
  doc.roundedRect(x, y, 2.2, 27, 1, 1, "F");
  setText(doc, COLORS.soft, 6.3, "bold");
  doc.text(label.toUpperCase(), x + 6, y + 7);
  setText(doc, COLORS.ink, 14, "bold");
  const valueLines = doc.splitTextToSize(String(value), width - 11).slice(0, 2);
  doc.text(valueLines, x + 6, y + 16);
  if (note) {
    setText(doc, COLORS.muted, 6.2, "normal");
    doc.text(note, x + 6, y + 24);
  }
}

function drawCallout(doc, { x, y, width, title, value, description = "" }) {
  doc.setFillColor(...COLORS.forest);
  doc.roundedRect(x, y, width, 34, 3, 3, "F");
  setText(doc, [190, 216, 204], 6.5, "bold");
  doc.text(title.toUpperCase(), x + 7, y + 8);
  setText(doc, COLORS.paper, 19, "bold");
  doc.text(String(value), x + 7, y + 20);
  if (description) {
    setText(doc, [208, 225, 217], 6.5, "normal");
    doc.text(doc.splitTextToSize(description, width - 14).slice(0, 2), x + 7, y + 27);
  }
}

function drawTableHeader(doc, y, columns) {
  doc.setFillColor(...COLORS.forest);
  doc.roundedRect(PAGE.margin, y, PAGE.contentWidth, 9, 2, 2, "F");
  setText(doc, COLORS.paper, 6.3, "bold");
  for (const column of columns) {
    doc.text(column.label.toUpperCase(), column.x, y + 5.8, column.align ? { align: column.align } : undefined);
  }
  return y + 9;
}

function drawRowBackground(doc, y, height, index, selected = false) {
  if (selected) {
    doc.setFillColor(...COLORS.forestSoft);
    doc.rect(PAGE.margin, y, PAGE.contentWidth, height, "F");
    doc.setFillColor(...COLORS.forestMid);
    doc.rect(PAGE.margin, y, 1.6, height, "F");
  } else if (index % 2) {
    doc.setFillColor(...COLORS.warm);
    doc.rect(PAGE.margin, y, PAGE.contentWidth, height, "F");
  }
  doc.setDrawColor(...COLORS.line);
  doc.line(PAGE.margin, y + height, PAGE.width - PAGE.margin, y + height);
}

function drawFooter(doc, pageNumber, pageCount, analysisId) {
  const y = PAGE.height - 10;
  doc.setDrawColor(...COLORS.line);
  doc.setLineWidth(0.2);
  doc.line(PAGE.margin, y - 4, PAGE.width - PAGE.margin, y - 4);
  setText(doc, COLORS.muted, 6.2, "normal");
  doc.text("Carta Natura - Report di analisi territoriale", PAGE.margin, y);
  if (analysisId) {
    doc.text(`ID ${analysisId}`, PAGE.width / 2, y, { align: "center" });
  }
  doc.text(`${pageNumber} / ${pageCount}`, PAGE.width - PAGE.margin, y, { align: "right" });
}

function formatDateTime(date = new Date()) {
  return new Intl.DateTimeFormat("it-IT", {
    day: "2-digit",
    month: "long",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatPercent(value) {
  return `${Number(value || 0).toLocaleString("it-IT", { maximumFractionDigits: 1 })}%`;
}

function cleanScenarioLabel(label) {
  return String(label || "Scenario").replace(/:\s*\d+(?:[.,]\d+)?\s*EUR\/t.*$/i, "");
}

function waitForLayout() {
  return new Promise((resolve) => window.setTimeout(resolve, 360));
}

function prepareDocument(doc, filename) {
  if (activePdfObjectUrl) {
    URL.revokeObjectURL(activePdfObjectUrl);
  }
  const blob = doc.output("blob");
  const objectUrl = URL.createObjectURL(blob);
  activePdfObjectUrl = objectUrl;
  return { filename, objectUrl };
}

async function captureMap(mapElement) {
  document.body.classList.add("pdf-map-capture");
  window.dispatchEvent(new Event("resize"));
  try {
    await waitForLayout();
    return await Promise.race([
      window.domtoimage.toPng(mapElement, {
        bgcolor: "#dbe6e5",
        quality: 1,
      }),
      new Promise((_, reject) => {
        window.setTimeout(
          () => reject(new DOMException("Acquisizione mappa scaduta.", "TimeoutError")),
          MAP_CAPTURE_TIMEOUT_MS
        );
      }),
    ]);
  } finally {
    document.body.classList.remove("pdf-map-capture");
    window.dispatchEvent(new Event("resize"));
  }
}

function drawMapFrame(doc, mapImage, x, y, width, height) {
  doc.setFillColor(235, 240, 237);
  doc.roundedRect(x, y, width, height, 3, 3, "F");
  if (mapImage) {
    doc.addImage(mapImage, "PNG", x, y, width, height);
  } else {
    setText(doc, COLORS.forest, 11, "bold");
    doc.text("Area analizzata", x + width / 2, y + height / 2 - 2, { align: "center" });
    setText(doc, COLORS.soft, 7.5, "normal");
    doc.text("Anteprima mappa non disponibile", x + width / 2, y + height / 2 + 5, {
      align: "center",
    });
  }
  doc.setDrawColor(...COLORS.line);
  doc.roundedRect(x, y, width, height, 3, 3, "S");
  doc.setFillColor(...COLORS.forest);
  doc.roundedRect(x + 5, y + height - 12, 42, 8, 1.5, 1.5, "F");
  setText(doc, COLORS.paper, 6.2, "bold");
  doc.text("AREA ANALIZZATA", x + 9, y + height - 7);
}

function drawExecutivePage(doc, context) {
  const {
    analysisId,
    summary,
    derivedMetrics,
    intersectedMunicipalities,
    selectedPrice,
    calculatedValue,
    mapImage,
    formatCurrency,
    formatRoundedNumber,
  } = context;

  doc.setFillColor(...COLORS.forest);
  doc.rect(0, 0, PAGE.width, 47, "F");
  doc.setFillColor(...COLORS.earth);
  doc.rect(0, 47, PAGE.width, 2.5, "F");
  drawBrandMark(doc, PAGE.margin, 13, 16);
  setText(doc, [195, 218, 208], 7, "bold");
  doc.text("SISTEMA INFORMATIVO TERRITORIALE", 36, 17);
  setText(doc, COLORS.paper, 23, "bold");
  doc.text("Carta Natura", 36, 28);
  setText(doc, [216, 231, 224], 9, "normal");
  doc.text("Report professionale di analisi territoriale", 36, 36);
  setText(doc, COLORS.paper, 7, "bold");
  doc.text("REGIONE CAMPANIA", PAGE.width - PAGE.margin, 18, { align: "right" });
  setText(doc, [195, 218, 208], 6.5, "normal");
  doc.text("Vegetazione forestale, CO2 e valore territoriale", PAGE.width - PAGE.margin, 25, { align: "right" });

  drawMapFrame(doc, mapImage, PAGE.margin, 58, 120, 78);

  doc.setFillColor(...COLORS.warm);
  doc.setDrawColor(...COLORS.line);
  doc.roundedRect(139, 58, 57, 78, 3, 3, "FD");
  setText(doc, COLORS.forestMid, 6.5, "bold");
  doc.text("SCHEDA ANALISI", 146, 68);
  setText(doc, COLORS.soft, 6.2, "bold");
  doc.text("GENERATO IL", 146, 79);
  setText(doc, COLORS.ink, 7.5, "normal");
  doc.text(doc.splitTextToSize(context.generatedAt, 43), 146, 84);
  setText(doc, COLORS.soft, 6.2, "bold");
  doc.text("COMUNI INTERESSATI", 146, 98);
  setText(doc, COLORS.ink, 16, "bold");
  doc.text(String(intersectedMunicipalities.length), 146, 107);
  setText(doc, COLORS.soft, 6.2, "bold");
  doc.text("IDENTIFICATIVO", 146, 117);
  setText(doc, COLORS.ink, 6.5, "normal");
  const idLines = doc.splitTextToSize(analysisId || "Non disponibile", 43).slice(0, 2);
  doc.text(idLines, 146, 122);

  drawMetric(doc, {
    x: PAGE.margin,
    y: 147,
    width: 43,
    label: "CO2 annua stimata",
    value: `${formatRoundedNumber(summary.totalCo2)} t`,
    note: "tonnellate / anno",
    accent: COLORS.earth,
  });
  drawMetric(doc, {
    x: 61,
    y: 147,
    width: 43,
    label: "Superficie",
    value: `${formatRoundedNumber(derivedMetrics.totalHectares)} ha`,
    note: "area forestale",
  });
  drawMetric(doc, {
    x: 108,
    y: 147,
    width: 41,
    label: "Categorie",
    value: String(summary.items.length),
    note: "tipologie rilevate",
  });
  drawMetric(doc, {
    x: 153,
    y: 147,
    width: 43,
    label: "Prevalente",
    value: derivedMetrics.topCategory?.label || "-",
    note: "per superficie",
    accent: COLORS.gold,
  });

  let y = drawSectionHeading(doc, "Sintesi esecutiva", 190, "Quadro territoriale");
  setText(doc, COLORS.soft, 8.5, "normal");
  const topShare = derivedMetrics.totalHectares
    ? (Number(derivedMetrics.topCategory?.hectares || 0) / derivedMetrics.totalHectares) * 100
    : 0;
  const summaryText = [
    `L'analisi interessa ${formatRoundedNumber(derivedMetrics.totalHectares)} ettari e individua ${summary.items.length} categorie forestali supportate.`,
    `${derivedMetrics.topCategory?.label || "La categoria prevalente"} rappresenta il ${formatPercent(topShare)} della superficie analizzata.`,
    `L'assorbimento complessivo stimato e pari a ${formatRoundedNumber(summary.totalCo2)} tonnellate di CO2 ogni anno.`,
  ];
  for (const paragraph of summaryText) {
    const lines = doc.splitTextToSize(paragraph, 112);
    doc.text(lines, PAGE.margin, y);
    y += lines.length * 4.5 + 3;
  }

  const priceLabel = selectedPrice
    ? `${formatRoundedNumber(selectedPrice)} EUR/tCO2`
    : "Scenario non selezionato";
  drawCallout(doc, {
    x: 139,
    y: 203,
    width: 57,
    title: "Valore economico stimato",
    value: Number.isFinite(Number(calculatedValue)) ? formatCurrency(calculatedValue) : "-",
    description: priceLabel,
  });

  doc.setFillColor(...COLORS.forestSoft);
  doc.roundedRect(PAGE.margin, 254, PAGE.contentWidth, 20, 3, 3, "F");
  setText(doc, COLORS.forest, 7, "bold");
  doc.text("LETTURA DEL RISULTATO", PAGE.margin + 7, 262);
  setText(doc, COLORS.soft, 7, "normal");
  doc.text(
    doc.splitTextToSize(
      "Le stime descrivono il contributo annuale della vegetazione forestale nell'area selezionata e supportano confronti territoriali e scenari di valorizzazione.",
      PAGE.contentWidth - 14
    ),
    PAGE.margin + 7,
    267
  );
}

function drawVegetationPage(doc, context) {
  const { summary, derivedMetrics, formatRoundedNumber } = context;
  drawPageHeader(doc, "Coperture forestali", "Distribuzione, fattori e assorbimento");
  let y = drawSectionHeading(doc, "Dettaglio della vegetazione", 41, "Risultati ambientali");
  setText(doc, COLORS.soft, 8, "normal");
  doc.text(
    doc.splitTextToSize(
      "La tabella ordina le categorie per superficie e riporta il contributo stimato all'assorbimento annuo di CO2.",
      PAGE.contentWidth
    ),
    PAGE.margin,
    y
  );
  y += 12;

  const columns = [
    { label: "Categoria", x: 21 },
    { label: "Superficie", x: 112, align: "right" },
    { label: "Quota", x: 137, align: "right" },
    { label: "Fattore", x: 164, align: "right" },
    { label: "CO2 / anno", x: 193, align: "right" },
  ];
  y = drawTableHeader(doc, y, columns);

  const sortedItems = [...summary.items].sort((a, b) => Number(b.hectares) - Number(a.hectares));
  sortedItems.forEach((item, index) => {
    const rowHeight = 12;
    drawRowBackground(doc, y, rowHeight, index);
    const rgb = hexToRgb(item.color);
    doc.setFillColor(rgb.r, rgb.g, rgb.b);
    doc.roundedRect(17, y + 3.2, 3, 5.5, 1, 1, "F");
    setText(doc, COLORS.ink, 7.3, "bold");
    doc.text(doc.splitTextToSize(item.label, 75).slice(0, 2), 22, y + 4.8);
    const share = derivedMetrics.totalHectares
      ? (Number(item.hectares || 0) / derivedMetrics.totalHectares) * 100
      : 0;
    const itemCo2 = Number(item.hectares || 0) * Number(item.co2PerHectare || 0);
    setText(doc, COLORS.ink, 7, "normal");
    doc.text(`${formatRoundedNumber(item.hectares)} ha`, 112, y + 7, { align: "right" });
    doc.text(formatPercent(share), 137, y + 7, { align: "right" });
    doc.text(`${formatRoundedNumber(item.co2PerHectare)} t/ha`, 164, y + 7, { align: "right" });
    doc.text(`${formatRoundedNumber(itemCo2)} t`, 193, y + 7, { align: "right" });
    y += rowHeight;
  });

  drawCallout(doc, {
    x: PAGE.margin,
    y: Math.min(y + 8, 242),
    width: PAGE.contentWidth,
    title: "Assorbimento annuale complessivo",
    value: `${formatRoundedNumber(summary.totalCo2)} t CO2 / anno`,
    description: `${formatRoundedNumber(summary.totalCo2 / Math.max(derivedMetrics.totalHectares, 1))} t CO2 per ettaro medio`,
  });
}

function drawEconomicPage(doc, context) {
  const {
    summary,
    priceOptions,
    selectedPrice,
    calculatedValue,
    intersectedMunicipalities,
    buildEconomicScenarioRows,
    formatCurrency,
    formatRoundedNumber,
  } = context;
  const rows = buildEconomicScenarioRows(summary, priceOptions, selectedPrice);
  drawPageHeader(doc, "Valorizzazione", "Scenari economici e perimetro dell'analisi");
  let y = drawSectionHeading(doc, "Scenari economici", 41, "Valore della CO2");
  setText(doc, COLORS.soft, 8, "normal");
  doc.text(
    doc.splitTextToSize(
      "I valori sono ottenuti applicando i prezzi unitari configurati all'assorbimento annuo stimato. Lo scenario selezionato e evidenziato.",
      PAGE.contentWidth
    ),
    PAGE.margin,
    y
  );
  y += 13;

  drawCallout(doc, {
    x: PAGE.margin,
    y,
    width: 88,
    title: "Scenario selezionato",
    value: Number.isFinite(Number(calculatedValue)) ? formatCurrency(calculatedValue) : "-",
    description: selectedPrice ? `${formatRoundedNumber(selectedPrice)} EUR per tCO2` : "Prezzo non disponibile",
  });
  drawMetric(doc, {
    x: 106,
    y,
    width: 43,
    label: "CO2 valorizzata",
    value: `${formatRoundedNumber(summary.totalCo2)} t`,
    note: "stima annuale",
    accent: COLORS.earth,
  });
  drawMetric(doc, {
    x: 153,
    y,
    width: 43,
    label: "Scenari",
    value: String(rows.length),
    note: "configurati",
    accent: COLORS.gold,
  });
  y += 45;

  const columns = [
    { label: "Scenario", x: 18 },
    { label: "Prezzo", x: 120, align: "right" },
    { label: "Valore annuo stimato", x: 193, align: "right" },
  ];
  y = drawTableHeader(doc, y, columns);
  const maxValue = Math.max(...rows.map((row) => Number(row.value || 0)), 1);
  rows.forEach((row, index) => {
    const rowHeight = 19;
    drawRowBackground(doc, y, rowHeight, index, row.selected);
    setText(doc, COLORS.ink, 7.6, "bold");
    doc.text(cleanScenarioLabel(row.label), 18, y + 6);
    if (row.selected) {
      setText(doc, COLORS.forestMid, 5.8, "bold");
      doc.text("SELEZIONATO", 18, y + 12);
    } else if (row.description) {
      setText(doc, COLORS.muted, 5.8, "normal");
      doc.text(doc.splitTextToSize(row.description, 77).slice(0, 1), 18, y + 12);
    }
    setText(doc, COLORS.ink, 7.2, "normal");
    doc.text(`${formatRoundedNumber(row.price)} EUR/tCO2`, 120, y + 7, { align: "right" });
    setText(doc, COLORS.ink, 8, "bold");
    doc.text(formatCurrency(row.value), 193, y + 7, { align: "right" });
    doc.setFillColor(232, 237, 233);
    doc.roundedRect(120, y + 12, 73, 2.5, 1, 1, "F");
    doc.setFillColor(...(row.selected ? COLORS.forestMid : COLORS.gold));
    doc.roundedRect(120, y + 12, Math.max(73 * (row.value / maxValue), 2), 2.5, 1, 1, "F");
    y += rowHeight;
  });

  y += 12;
  y = drawSectionHeading(doc, "Perimetro territoriale", y, "Comuni interessati");
  setText(doc, COLORS.soft, 7.8, "normal");
  const municipalityText = intersectedMunicipalities.length
    ? intersectedMunicipalities.join(" - ")
    : "Nessun comune associato all'area analizzata.";
  const municipalityLines = doc.splitTextToSize(municipalityText, PAGE.contentWidth);
  doc.text(municipalityLines, PAGE.margin, y);
  y += municipalityLines.length * 4.5 + 8;
  doc.setFillColor(...COLORS.forestSoft);
  doc.roundedRect(PAGE.margin, y, PAGE.contentWidth, 18, 2.5, 2.5, "F");
  setText(doc, COLORS.forest, 6.5, "bold");
  doc.text("CRITERIO DI CALCOLO", PAGE.margin + 7, y + 6.5);
  setText(doc, COLORS.soft, 7, "normal");
  doc.text(
    "Valore annuo = assorbimento stimato di CO2 x prezzo unitario dello scenario.",
    PAGE.margin + 7,
    y + 12.5
  );
}

function drawMethodologyPage(doc, context) {
  const { analysisId, generatedAt, intersectedMunicipalities, formatRoundedNumber, derivedMetrics } = context;
  drawPageHeader(doc, "Metodo e tracciabilita", "Criteri di lettura e riferimenti dell'elaborazione");
  let y = drawSectionHeading(doc, "Nota metodologica", 41, "Interpretazione");
  setText(doc, COLORS.soft, 8, "normal");
  doc.text(
    doc.splitTextToSize(
      "Il report sintetizza i risultati prodotti dal WebGIS Carta Natura per l'area selezionata. I calcoli riportati coincidono con quelli mostrati nell'applicazione.",
      PAGE.contentWidth
    ),
    PAGE.margin,
    y
  );
  y += 16;

  setText(doc, COLORS.soft, 7.5, "normal");
  const notes = [
    "Superficie: somma delle aree delle categorie forestali supportate presenti nella selezione.",
    "CO2 annua: superficie per coefficiente di assorbimento specifico della categoria.",
    "Valore economico: CO2 annua stimata per prezzo unitario dello scenario selezionato.",
    "Le stime hanno finalita descrittiva e comparativa e dipendono dai dati territoriali e dai parametri configurati nel sistema.",
  ];
  notes.forEach((note, index) => {
    doc.setFillColor(...(index === notes.length - 1 ? COLORS.forestSoft : COLORS.warm));
    const lines = doc.splitTextToSize(note, PAGE.contentWidth - 16);
    const height = Math.max(11, lines.length * 4 + 5);
    doc.roundedRect(PAGE.margin, y, PAGE.contentWidth, height, 2, 2, "F");
    doc.setFillColor(...(index === notes.length - 1 ? COLORS.forestMid : COLORS.gold));
    doc.circle(PAGE.margin + 5, y + 5.5, 1.4, "F");
    doc.text(lines, PAGE.margin + 9, y + 5.8);
    y += height + 3;
  });

  y += 7;
  y = drawSectionHeading(doc, "Tracciabilita dell'elaborazione", y, "Scheda tecnica");
  const traceRows = [
    ["Identificativo analisi", analysisId || "Non disponibile"],
    ["Data di generazione", generatedAt],
    ["Superficie analizzata", `${formatRoundedNumber(derivedMetrics.totalHectares)} ha`],
    ["Comuni interessati", String(intersectedMunicipalities.length)],
    ["Ambito", "Vegetazione forestale della Regione Campania"],
  ];
  traceRows.forEach(([label, value], index) => {
    drawRowBackground(doc, y, 12, index);
    setText(doc, COLORS.soft, 6.8, "bold");
    doc.text(label.toUpperCase(), PAGE.margin + 4, y + 7.5);
    setText(doc, COLORS.ink, 7.2, "normal");
    doc.text(doc.splitTextToSize(value, 105).slice(0, 2), 84, y + 7.5);
    y += 12;
  });

  doc.setFillColor(...COLORS.forest);
  doc.roundedRect(PAGE.margin, 244, PAGE.contentWidth, 26, 3, 3, "F");
  setText(doc, [195, 218, 208], 6.5, "bold");
  doc.text("USO DEL REPORT", PAGE.margin + 7, 252);
  setText(doc, COLORS.paper, 8, "normal");
  doc.text(
    doc.splitTextToSize(
      "Documento di supporto alla lettura territoriale, alla ricerca e al confronto tra scenari. Non sostituisce valutazioni tecniche o amministrative di dettaglio.",
      PAGE.contentWidth - 14
    ),
    PAGE.margin + 7,
    259
  );
}

export async function generatePdfReport({
  analysisId,
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
  const doc = new JsPdf({ orientation: "portrait", unit: "mm", format: "a4" });
  let mapImage = null;
  try {
    mapImage = await captureMap(mapElement);
  } catch (error) {
    console.warn("PDF map capture unavailable; generating the data report without it.", error);
  }
  const context = {
    analysisId,
    summary,
    intersectedMunicipalities,
    selectedPrice,
    calculatedValue,
    priceOptions,
    mapImage,
    generatedAt: formatDateTime(),
    derivedMetrics: deriveSummaryMetrics(summary),
    buildEconomicScenarioRows,
    formatCurrency,
    formatRoundedNumber,
  };

  doc.setProperties?.({
    title: "Carta Natura - Report di analisi territoriale",
    subject: "Vegetazione forestale, assorbimento annuo di CO2 e valorizzazione economica",
    author: "Carta Natura",
    creator: "Carta Natura WebGIS",
  });

  drawExecutivePage(doc, context);
  doc.addPage();
  drawVegetationPage(doc, context);
  doc.addPage();
  drawEconomicPage(doc, context);
  doc.addPage();
  drawMethodologyPage(doc, context);

  const pageCount = doc.internal.getNumberOfPages();
  for (let pageNumber = 1; pageNumber <= pageCount; pageNumber += 1) {
    doc.setPage(pageNumber);
    drawFooter(doc, pageNumber, pageCount, analysisId);
  }

  return prepareDocument(doc, "carta-natura-report.pdf");
}

function hexToRgb(hexColor) {
  const namedColors = {
    black: "000000",
    maroon: "800000",
    olive: "808000",
    navy: "000080",
    teal: "008080",
    aqua: "00b7c7",
    purple: "800080",
    lime: "32a852",
    blue: "2456d8",
    gray: "6b7280",
    orange: "e47b22",
    gold: "c99d45",
  };
  const raw = String(hexColor || "#4f4f4f").replace("#", "").toLowerCase();
  const normalized = namedColors[raw] || raw;
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
