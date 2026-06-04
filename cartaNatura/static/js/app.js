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
  const resultText = state.summary?.hasSupportedVegetation
    ? `${state.intersectedMunicipalities.length} comuni, ${formatRoundedNumber(
        state.summary.totalCo2
      )} t CO2/anno`
    : state.summary
      ? "nessuna vegetazione supportata"
      : "nessuna analisi";

  elements.statusContent.innerHTML = `
    <div class="status-chip">
      <span class="status-label">Comuni</span>
      <strong class="status-value">${selectedMunicipalityCount}</strong>
    </div>
    <div class="status-chip">
      <span class="status-label">Geometrie</span>
      <strong class="status-value">${drawnFeatureCount}</strong>
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

function renderInfoSummary() {
  if (!state.summary) {
    elements.infoContainer.innerHTML = "<p>Non ci sono info in questo momento.</p>";
    return;
  }

  if (!state.summary.hasSupportedVegetation) {
    elements.infoContainer.innerHTML =
      "<p>L'area selezionata non contiene vegetazione che il sistema analizza.</p>";
    return;
  }

  const summaryRows = state.summary.items
    .map(
      (item) =>
        `<li><strong>${escapeHtml(item.label)}</strong>: ${formatRoundedNumber(item.hectares)} ha</li>`
    )
    .join("");

  const municipalitiesHtml = state.intersectedMunicipalities.length
    ? `<div class="info-box"><strong>I comuni interessati sono:</strong> ${escapeHtml(
        state.intersectedMunicipalities.join(", ")
      )}</div>`
    : "";

  elements.infoContainer.innerHTML = `
    <div class="summary-section">
      <ul class="summary-list">${summaryRows}</ul>
      <p><strong>Il livello di CO2 assorbita dall'area selezionata è ${formatRoundedNumber(
        state.summary.totalCo2
      )} t annue</strong></p>
      ${municipalitiesHtml}
      <h4>Seleziona valore per ogni tonnellata di CO2</h4>
      <div class="value-row">
        <select id="testoValore">${renderPriceOptions()}</select>
        <button id="butcalcolavalore" type="button" class="btn btn-info btn-sm text-light">
          Calcola valore totale
        </button>
      </div>
      <div id="valoreTotaleCalcolato" class="value-result"></div>
    </div>
  `;

  const calculateButton = document.getElementById("butcalcolavalore");
  calculateButton.addEventListener("click", () => {
    const selectedValue = Number(document.getElementById("testoValore").value || 0);
    state.calculatedValue = selectedValue * state.summary.totalCo2;

    const resultRoot = document.getElementById("valoreTotaleCalcolato");
    resultRoot.innerHTML = `
      <strong>Il valore monetario totale è di ${formatCurrency(state.calculatedValue)}</strong>
      <p>
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

    if (!state.summary.hasSupportedVegetation) {
      alert("L'area selezionata non contiene vegetazione che il sistema analizza.");
    }
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
