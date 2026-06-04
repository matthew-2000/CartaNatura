import { requestNatureClip, fetchGeoJson } from "./modules/api.js";
import { summarizeClippedFeatures, formatCurrency, formatRoundedNumber } from "./modules/analysis.js";
import { appConfig, categories, categoryByCode, priceOptions } from "./modules/config.js";
import { MapController } from "./modules/map-controller.js";
import { generatePdfReport } from "./modules/pdf-export.js";

const state = {
  summary: null,
  clipped: null,
  intersectedMunicipalities: [],
  calculatedValue: 0,
  analysisContext: null,
};

const elements = {
  navbar: document.querySelector(".navbar"),
  selectMunicipalityButton: document.getElementById("butSelezionaComune"),
  resetButton: document.getElementById("resetMapState"),
  runAnalysisButton: document.getElementById("eseguiClipBut"),
  infoButton: document.getElementById("mostraInfoBut"),
  appInfoButton: document.getElementById("infoApp"),
  municipalityPanel: document.getElementById("navListaComuni"),
  municipalityList: document.getElementById("lista-comuni"),
  municipalitySearch: document.getElementById("municipalitySearch"),
  selectedCountLabel: document.getElementById("selectedCountLabel"),
  loadingOverlay: document.querySelector(".loading"),
  popup: document.getElementById("popup"),
  infoContainer: document.getElementById("infoNatura"),
  closePopupButton: document.getElementById("butchiudipopup"),
  appInfoModal: document.getElementById("infoApplicazione"),
  closeAppInfoButton: document.getElementById("closeInfoApp"),
  statusContent: document.getElementById("statusContent"),
  legendContent: document.getElementById("legendContent"),
  statusPanel: document.getElementById("mapStatusPanel"),
  legendPanel: document.getElementById("legendPanel"),
  toggleLegendPanelButton: document.getElementById("toggleLegendPanel"),
  map: document.getElementById("map"),
};

function syncChromeOffset() {
  const navbarHeight = elements.navbar?.getBoundingClientRect().height ?? 0;
  const viewportWidth = window.innerWidth;
  const extraGap = viewportWidth <= 760 ? 14 : 18;
  const offset = Math.ceil(navbarHeight + 14 + extraGap);
  document.documentElement.style.setProperty("--shell-offset", `${offset}px`);
}

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function setBusy(mapController, busy) {
  elements.loadingOverlay.classList.toggle("visible", busy);
  elements.selectMunicipalityButton.disabled = busy;
  elements.runAnalysisButton.disabled = busy;
  elements.infoButton.disabled = busy;
  elements.appInfoButton.disabled = busy;
  mapController.setInteractionDisabled(busy);
}

function openPopup(mapController) {
  elements.popup.classList.add("open-popup");
  mapController.setInteractionDisabled(true);
}

function closePopup(mapController) {
  elements.popup.classList.remove("open-popup");
  mapController.setInteractionDisabled(false);
}

function openAppInfo(mapController) {
  elements.appInfoModal.classList.add("open-infoApp");
  mapController.setInteractionDisabled(true);
}

function closeAppInfo(mapController) {
  elements.appInfoModal.classList.remove("open-infoApp");
  mapController.setInteractionDisabled(false);
}

function toggleMunicipalityPanel() {
  elements.municipalityPanel.classList.toggle("visualizzaListaComuni");
}

function closeMunicipalityPanel() {
  elements.municipalityPanel.classList.remove("visualizzaListaComuni");
}

function setPanelCollapsed(panelElement, buttonElement, collapsed) {
  if (!panelElement || !buttonElement) {
    return;
  }
  panelElement.classList.toggle("is-collapsed", collapsed);
  buttonElement.setAttribute("aria-expanded", String(!collapsed));
  buttonElement.textContent = collapsed ? "Apri" : "Riduci";
}

function togglePanel(panelElement, buttonElement) {
  setPanelCollapsed(panelElement, buttonElement, !panelElement.classList.contains("is-collapsed"));
}

function renderLegend() {
  elements.legendContent.innerHTML = `
    <div class="legend-grid">
      ${categories
        .map(
          (category) => `
            <div class="legend-item">
              <span class="legend-swatch" style="background:${category.color}"></span>
              <span>${escapeHtml(category.label)}</span>
            </div>
          `
        )
        .join("")}
    </div>
  `;
}

function renderStatusPanel({ selectedMunicipalityCount = 0, drawnFeatureCount = 0 } = {}) {
  const inputMunicipalities = state.analysisContext?.selectedMunicipalityCount ?? selectedMunicipalityCount;
  const inputGeometries = state.analysisContext?.drawnFeatureCount ?? drawnFeatureCount;
  const resultText = state.summary?.hasSupportedVegetation
    ? `${state.intersectedMunicipalities.length} comuni, ${formatRoundedNumber(
        state.summary.totalCo2
      )} t CO2/anno`
    : state.summary
      ? "nessuna vegetazione supportata"
      : "nessuna analisi";

  elements.statusContent.innerHTML = `
    <div class="status-chip">
      <span class="status-label">Input comuni</span>
      <strong class="status-value">${inputMunicipalities}</strong>
    </div>
    <div class="status-chip">
      <span class="status-label">Input geometrie</span>
      <strong class="status-value">${inputGeometries}</strong>
    </div>
    <div class="status-chip">
      <span class="status-label">Categorie</span>
      <strong class="status-value">${state.summary?.items.length ?? 0}</strong>
    </div>
    <div class="status-chip status-chip-wide">
      <span class="status-label">Risultato</span>
      <strong class="status-value">${escapeHtml(resultText)}</strong>
    </div>
  `;

  elements.selectedCountLabel.textContent = `${selectedMunicipalityCount} selezionati`;
}

function clearMunicipalityChecks() {
  for (const checkbox of elements.municipalityList.querySelectorAll('input[type="checkbox"]')) {
    checkbox.checked = false;
  }
}

function filterMunicipalityList() {
  const query = elements.municipalitySearch.value.trim().toLowerCase();

  for (const item of elements.municipalityList.querySelectorAll(".comune-item")) {
    const name = item.dataset.name || "";
    item.classList.toggle("hidden", query && !name.includes(query));
  }
}

function renderMunicipalityList(mapController, onChange) {
  const template = document.querySelector(".comune-template");
  const fragment = document.createDocumentFragment();

  for (const municipalityName of mapController.getMunicipalityNames()) {
    const item = template.content.cloneNode(true);
    const root = item.querySelector(".comune-item");
    const label = item.querySelector(".nome-comune");
    const checkbox = item.querySelector('input[type="checkbox"]');
    const checkboxId = `comune-${municipalityName.replaceAll(/[^a-z0-9]+/gi, "-").toLowerCase()}`;

    root.dataset.name = municipalityName.toLowerCase();
    label.textContent = municipalityName;
    label.setAttribute("for", checkboxId);
    checkbox.id = checkboxId;
    checkbox.setAttribute("aria-label", municipalityName);
    checkbox.addEventListener("change", (event) => {
      mapController.toggleMunicipalitySelection(municipalityName, event.target.checked);
      onChange();
    });

    fragment.appendChild(item);
  }

  elements.municipalityList.replaceChildren(fragment);
  filterMunicipalityList();
}

function renderPriceOptions() {
  return priceOptions
    .map(
      (option) => `<option value="${option.value}">${escapeHtml(option.label)}</option>`
    )
    .join("");
}

function getDerivedSummaryMetrics() {
  const items = state.summary?.items || [];
  const totalHectares = items.reduce((sum, item) => sum + (Number(item.hectares) || 0), 0);
  const topCategory = items.reduce(
    (current, item) => ((Number(item.hectares) || 0) > (Number(current?.hectares) || 0) ? item : current),
    null
  );

  return {
    totalHectares,
    topCategory,
  };
}

function renderInfoSummary() {
  if (!state.summary) {
    elements.infoContainer.innerHTML = `
      <div class="analysis-empty-state">
        <h3>Nessuna analisi disponibile</h3>
        <p>Seleziona uno o piu comuni, oppure disegna un'area sulla mappa, poi esegui l'estrazione.</p>
      </div>
    `;
    return;
  }

  if (!state.summary.hasSupportedVegetation) {
    elements.infoContainer.innerHTML = `
      <div class="analysis-empty-state">
        <h3>Nessuna vegetazione supportata</h3>
        <p>L'area estratta non contiene categorie forestali comprese nell'analisi corrente.</p>
      </div>
    `;
    return;
  }

  const derivedMetrics = getDerivedSummaryMetrics();
  const maxHectares = Math.max(...state.summary.items.map((item) => item.hectares), 1);
  const summaryRows = state.summary.items
    .map(
      (item) =>
        `
          <li class="analysis-breakdown-item">
            <div class="analysis-breakdown-header">
              <span class="analysis-breakdown-name">${escapeHtml(item.label)}</span>
              <strong>${formatRoundedNumber(item.hectares)} ha</strong>
            </div>
            <div class="analysis-breakdown-bar">
              <span style="width:${Math.max((item.hectares / maxHectares) * 100, 6)}%; background:${item.color}"></span>
            </div>
          </li>
        `
    )
    .join("");

  const municipalitiesHtml = state.intersectedMunicipalities.length
    ? `<div class="analysis-note-card"><strong>Comuni interessati:</strong> ${escapeHtml(
        state.intersectedMunicipalities.join(", ")
      )}</div>`
    : "";

  elements.infoContainer.innerHTML = `
    <div class="summary-section analysis-summary">
      <div class="analysis-metrics-grid">
        <article class="analysis-metric-card">
          <span class="analysis-metric-label">CO2 annua</span>
          <strong class="analysis-metric-value">${formatRoundedNumber(state.summary.totalCo2)} t</strong>
        </article>
        <article class="analysis-metric-card">
          <span class="analysis-metric-label">Superficie</span>
          <strong class="analysis-metric-value">${formatRoundedNumber(derivedMetrics.totalHectares)} ha</strong>
        </article>
        <article class="analysis-metric-card">
          <span class="analysis-metric-label">Categorie rilevate</span>
          <strong class="analysis-metric-value">${state.summary.items.length}</strong>
        </article>
        <article class="analysis-metric-card">
          <span class="analysis-metric-label">Categoria prevalente</span>
          <strong class="analysis-metric-value">${escapeHtml(derivedMetrics.topCategory?.label || "-")}</strong>
        </article>
      </div>
      <div class="analysis-section">
        <div class="analysis-section-header">
          <h4>Ripartizione della vegetazione</h4>
          <span class="analysis-section-meta">${formatRoundedNumber(derivedMetrics.totalHectares)} ha complessivi</span>
        </div>
        <ul class="analysis-breakdown-list">${summaryRows}</ul>
      </div>
      ${municipalitiesHtml}
      <div class="analysis-note-card">
        <strong>Assorbimento stimato:</strong> ${formatRoundedNumber(state.summary.totalCo2)} tonnellate di CO2 all'anno.
      </div>
      <div class="analysis-valuation-card">
        <div class="analysis-section-header">
          <h4>Valorizzazione economica</h4>
          <span class="analysis-section-meta">Stima basata sul prezzo selezionato</span>
        </div>
        <div class="value-row">
          <select id="testoValore">${renderPriceOptions()}</select>
          <button id="butcalcolavalore" type="button" class="btn btn-info btn-sm text-light">
            Calcola valore
          </button>
        </div>
        <div id="valoreTotaleCalcolato" class="value-result"></div>
      </div>
    </div>
  `;

  const calculateButton = document.getElementById("butcalcolavalore");
  calculateButton.addEventListener("click", () => {
    const selectedValue = Number(document.getElementById("testoValore").value || 0);
    state.calculatedValue = selectedValue * state.summary.totalCo2;

    const resultRoot = document.getElementById("valoreTotaleCalcolato");
    resultRoot.innerHTML = `
      <div class="analysis-value-total">
        <span class="analysis-metric-label">Valore economico stimato</span>
        <strong class="analysis-value-amount">${formatCurrency(state.calculatedValue)}</strong>
      </div>
      <p class="analysis-value-actions">
        <button id="butstampadettagli" type="button" class="btn btn-success btn-sm text-light mt-3">
          Stampa dettagli
        </button>
      </p>
    `;

    document.getElementById("butstampadettagli").addEventListener("click", async () => {
      const printButton = document.getElementById("butstampadettagli");
      const closeButton = elements.closePopupButton;
      calculateButton.disabled = true;
      printButton.disabled = true;
      closeButton.disabled = true;
      resultRoot.insertAdjacentHTML(
        "beforeend",
        `<div class="pdf-status"><strong>Stiamo generando documento</strong></div>`
      );

      try {
        await generatePdfReport({
          summary: state.summary,
          intersectedMunicipalities: state.intersectedMunicipalities,
          selectedPrice: selectedValue,
          calculatedValue: state.calculatedValue,
          mapElement: elements.map,
          reportLogoUrl: appConfig.assets.reportLogoUrl,
        });
      } catch (error) {
        alert(error.message || "Errore nella generazione del PDF.");
      } finally {
        calculateButton.disabled = false;
        printButton.disabled = false;
        closeButton.disabled = false;
        const status = resultRoot.querySelector(".pdf-status");
        if (status) {
          status.remove();
        }
      }
    });
  });
}

function buildAnalysisPayload(mapController) {
  const areas = [];

  if (mapController.hasSelectedMunicipalities()) {
    areas.push({
      kind: "municipalities",
      geojson: mapController.buildSelectedMunicipalityGeoJson(),
    });
  }

  if (mapController.hasDrawnAreas()) {
    areas.push({
      kind: "drawn",
      geojson: mapController.buildDrawnGeoJson(),
    });
  }

  return { areas };
}

function resetAnalysis(mapController) {
  state.summary = null;
  state.clipped = null;
  state.intersectedMunicipalities = [];
  state.calculatedValue = 0;
  state.analysisContext = null;
  mapController.clearResults();
  mapController.clearUserSelections();
  clearMunicipalityChecks();
  elements.municipalitySearch.value = "";
  filterMunicipalityList();
  renderStatusPanel({
    selectedMunicipalityCount: mapController.getSelectedMunicipalityCount(),
    drawnFeatureCount: mapController.getDrawnFeatureCount(),
  });
  closePopup(mapController);
  closeAppInfo(mapController);
}

async function runAnalysis(mapController) {
  closePopup(mapController);
  closeAppInfo(mapController);

  const payload = buildAnalysisPayload(mapController);
  const analysisContext = {
    selectedMunicipalityCount: mapController.getSelectedMunicipalityCount(),
    drawnFeatureCount: mapController.getDrawnFeatureCount(),
  };
  if (!payload.areas.length) {
    alert("Non hai selezionato alcuna area.");
    return;
  }

  setBusy(mapController, true);

  try {
    const response = await requestNatureClip(appConfig.apiUrl, payload);
    state.clipped = response.clipped;
    state.intersectedMunicipalities = response.intersectedMunicipalities;
    state.summary = summarizeClippedFeatures(response.clipped, categories, categoryByCode);
    state.calculatedValue = 0;
    state.analysisContext = analysisContext;

    mapController.clearResults();
    mapController.renderNature(response.clipped);
    mapController.renderIntersectedMunicipalities(state.intersectedMunicipalities);
    mapController.clearUserSelections();
    clearMunicipalityChecks();
    elements.municipalitySearch.value = "";
    filterMunicipalityList();
    renderStatusPanel({
      selectedMunicipalityCount: mapController.getSelectedMunicipalityCount(),
      drawnFeatureCount: mapController.getDrawnFeatureCount(),
    });
    renderInfoSummary();
    openPopup(mapController);
  } catch (error) {
    alert(error.message || "Errore durante analisi.");
  } finally {
    setBusy(mapController, false);
  }
}

async function bootstrap() {
  syncChromeOffset();

  const [municipalitySource, municipalityBoundaries] = await Promise.all([
    fetchGeoJson(appConfig.datasets.municipalitiesUrl),
    fetchGeoJson(appConfig.datasets.boundariesUrl),
  ]);

  const refreshSelectionStatus = (selectionState = null, mapControllerRef = null) => {
    const selectedMunicipalityCount =
      selectionState?.selectedMunicipalityCount ?? mapControllerRef?.getSelectedMunicipalityCount() ?? 0;
    const drawnFeatureCount =
      selectionState?.drawnFeatureCount ?? mapControllerRef?.getDrawnFeatureCount() ?? 0;

    renderStatusPanel({ selectedMunicipalityCount, drawnFeatureCount });
  };

  const mapController = new MapController({
    mapConfig: appConfig.map,
    municipalitySource,
    municipalityBoundaries,
    categoryByCode,
    onSelectionChange: (selectionState) => refreshSelectionStatus(selectionState),
  });

  renderLegend();
  renderStatusPanel();
  renderMunicipalityList(mapController, () => refreshSelectionStatus(null, mapController));

  elements.selectMunicipalityButton.addEventListener("click", () => {
    toggleMunicipalityPanel();
  });

  elements.resetButton.addEventListener("click", () => {
    resetAnalysis(mapController);
  });

  elements.runAnalysisButton.addEventListener("click", () => {
    runAnalysis(mapController);
  });

  elements.infoButton.addEventListener("click", () => {
    renderInfoSummary();
    openPopup(mapController);
  });

  elements.closePopupButton.addEventListener("click", () => {
    closePopup(mapController);
  });

  elements.appInfoButton.addEventListener("click", () => {
    openAppInfo(mapController);
  });

  elements.closeAppInfoButton.addEventListener("click", () => {
    closeAppInfo(mapController);
  });

  elements.municipalitySearch.addEventListener("input", () => {
    filterMunicipalityList();
  });

  if (elements.toggleLegendPanelButton) {
    elements.toggleLegendPanelButton.addEventListener("click", () => {
      togglePanel(elements.legendPanel, elements.toggleLegendPanelButton);
    });
  }

  window.addEventListener("resize", syncChromeOffset);
  window.addEventListener("orientationchange", syncChromeOffset);

  document.addEventListener("click", (event) => {
    if (
      !elements.municipalityPanel.contains(event.target) &&
      event.target !== elements.selectMunicipalityButton
    ) {
      closeMunicipalityPanel();
    }
  });
}

bootstrap().catch((error) => {
  alert(error.message || "Errore durante inizializzazione applicazione.");
});
