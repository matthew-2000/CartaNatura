import { formatCurrency, formatRoundedNumber } from "./analysis.js";

function getJsPdfConstructor() {
  return window.jsPDF || window.jspdf?.jsPDF || null;
}

function addOptionalLogo(doc, logoUrl) {
  if (!logoUrl) {
    return Promise.resolve();
  }

  return new Promise((resolve) => {
    const image = new Image();
    image.crossOrigin = "anonymous";
    image.onload = () => {
      try {
        doc.addImage(image, "JPEG", 62, 5, 90, 38);
      } catch (error) {
        // Ignore logo errors. Report still valid.
      }
      resolve();
    };
    image.onerror = () => resolve();
    image.src = logoUrl;
  });
}

export async function generatePdfReport({
  summary,
  intersectedMunicipalities,
  selectedPrice,
  calculatedValue,
  mapElement,
  reportLogoUrl,
}) {
  const JsPdf = getJsPdfConstructor();
  if (!JsPdf || !window.domtoimage) {
    throw new Error("PDF libraries not available.");
  }

  const doc = new JsPdf();
  await addOptionalLogo(doc, reportLogoUrl);

  const title = "Informazioni sulla natura";
  const pageWidth = doc.internal.pageSize.getWidth();
  const titleWidth = (doc.getStringUnitWidth(title) * 20) / doc.internal.scaleFactor;
  doc.setFontSize(20);
  doc.text(title, (pageWidth - titleWidth) / 2, 50);

  const mapImage = await window.domtoimage.toPng(mapElement);
  doc.addImage(mapImage, "PNG", 10, 55, 130, 120);

  doc.setFontSize(11);
  let cursorY = 185;
  for (const item of summary.items) {
    doc.text(`${item.label}: ${formatRoundedNumber(item.hectares)} ha`, 10, cursorY);
    cursorY += 6;
  }

  doc.text(
    `CO2 assorbita annua: ${formatRoundedNumber(summary.totalCo2)} t`,
    10,
    cursorY + 4
  );
  cursorY += 12;

  if (selectedPrice) {
    doc.text(`Valore per tonnellata: ${selectedPrice} EUR`, 10, cursorY);
    cursorY += 6;
  }

  if (calculatedValue > 0) {
    doc.text(`Valore monetario totale: ${formatCurrency(calculatedValue)}`, 10, cursorY);
  }

  doc.addPage();
  const municipalitiesText = intersectedMunicipalities.length
    ? `I comuni interessati sono: ${intersectedMunicipalities.join(", ")}`
    : "Nessun comune interessato.";
  const lines = doc.splitTextToSize(municipalitiesText, 180);
  for (let index = 0; index < lines.length; index += 1) {
    doc.text(lines[index], 10, 10 + index * 6);
  }

  doc.save("carta-natura-report.pdf");
}
