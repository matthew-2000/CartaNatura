import { requestNatureClip, fetchGeoJson, sendInteractionMessage } from "./modules/api.js";
import {
  deriveSummaryMetrics,
  summarizeClippedFeatures,
  formatCurrency,
  formatRoundedNumber,
} from "./modules/analysis.js";
import {
  appConfig,
  assistantConfig,
  categories,
  categoryByCode,
  priceOptions,
} from "./modules/config.js";
import { MapController } from "./modules/map-controller.js";
import { generatePdfReport } from "./modules/pdf-export.js";

const state = {
  summary: null,
  clipped: null,
  intersectedMunicipalities: [],
  calculatedValue: 0,
  analysisContext: null,
  noticeTimer: null,
  assistantMessages: [
    {
      role: "assistant",
      text: "Assistente pronto. Posso gia analizzare comuni citati nel testo, per esempio: analizza Avellino e Benevento.",
    },
  ],
  assistantBusy: false,
};

const elements = {
  navbar: document.querySelector(".navbar"),
  selectMunicipalityButton: document.getElementById("butSelezionaComune"),
  resetButton: document.getElementById("resetMapState"),
  openAssistantButton: document.getElementById("openAssistantPanel"),
  runAnalysisButton: document.getElementById("eseguiClipBut"),
  infoButton: document.getElementById("mostraInfoBut"),
  appInfoButton: document.getElementById("infoApp"),
  municipalityPanel: document.getElementById("navListaComuni"),
  municipalityList: document.getElementById("lista-comuni"),
  municipalitySearch: document.getElementById("municipalitySearch"),
  selectedCountLabel: document.getElementById("selectedCountLabel"),
  loadingOverlay: document.querySelector(".loading"),
  appNotice: document.getElementById("appNotice"),
  popup: document.getElementById("popup"),
  assistantPanel: document.getElementById("assistantPanel"),
  assistantTitle: document.querySelector(".assistant-panel-title"),
  assistantStatus: document.getElementById("assistantStatus"),
  assistantMessages: document.getElementById("assistantMessages"),
  assistantForm: document.getElementById("assistantForm"),
  assistantInput: document.getElementById("assistantInput"),
  assistantSendButton: document.getElementById("assistantSendButton"),
  closeAssistantButton: document.getElementById("closeAssistantPanel"),
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
  elements.loadingOverlay.setAttribute("aria-hidden", String(!busy));
  elements.selectMunicipalityButton.disabled = busy;
  elements.runAnalysisButton.disabled = busy;
  elements.infoButton.disabled = busy;
  elements.appInfoButton.disabled = busy;
  elements.runAnalysisButton.textContent = busy ? "Estrazione..." : "Estrai";
  mapController.setInteractionDisabled(busy);
}

function openPopup(mapController) {
  elements.popup.classList.add("open-popup");
  elements.popup.setAttribute("aria-hidden", "false");
  mapController.setInteractionDisabled(true);
}

function closePopup(mapController) {
  elements.popup.classList.remove("open-popup");
  elements.popup.setAttribute("aria-hidden", "true");
  mapController.setInteractionDisabled(false);
}

function openAppInfo(mapController) {
  elements.appInfoModal.classList.add("open-infoApp");
  elements.appInfoModal.setAttribute("aria-hidden", "false");
  mapController.setInteractionDisabled(true);
}

function closeAppInfo(mapController) {
  elements.appInfoModal.classList.remove("open-infoApp");
  elements.appInfoModal.setAttribute("aria-hidden", "true");
  mapController.setInteractionDisabled(false);
}

function openAssistantPanel() {
  if (!assistantConfig.enabled) {
    return;
  }
  elements.assistantPanel.classList.add("is-open");
  elements.assistantPanel.setAttribute("aria-hidden", "false");
}

function closeAssistantPanel() {
  elements.assistantPanel.classList.remove("is-open");
  elements.assistantPanel.setAttribute("aria-hidden", "true");
}

function toggleAssistantPanel() {
  if (elements.assistantPanel.classList.contains("is-open")) {
    closeAssistantPanel();
    return;
  }

  openAssistantPanel();
}

function syncMunicipalityPanelState() {
  document.body.classList.toggle(
    "municipality-panel-open",
    elements.municipalityPanel.classList.contains("visualizzaListaComuni")
  );
}

function toggleMunicipalityPanel() {
  elements.municipalityPanel.classList.toggle("visualizzaListaComuni");
  syncMunicipalityPanelState();
}

function closeMunicipalityPanel() {
  elements.municipalityPanel.classList.remove("visualizzaListaComuni");
  syncMunicipalityPanelState();
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

function showNotice(message, tone = "info") {
  if (!elements.appNotice) {
    return;
  }

  if (state.noticeTimer) {
    clearTimeout(state.noticeTimer);
  }

  elements.appNotice.textContent = message;
  elements.appNotice.className = `app-notice is-visible is-${tone}`;
  elements.appNotice.hidden = false;

  state.noticeTimer = window.setTimeout(() => {
    elements.appNotice.className = "app-notice";
    elements.appNotice.hidden = true;
  }, 3400);
}

function setAssistantStatus(providerMode = "local", configured = false) {
  let statusText = "Fallback locale attivo";
  if (!assistantConfig.enabled) {
    statusText = "Assistente disattivato";
  } else if (providerMode === "openai") {
    statusText = "LLM configurato";
  } else if (configured) {
    statusText = "Provider configurato, fallback locale attivo";
  }

  elements.assistantStatus.textContent = statusText;
  elements.assistantStatus.classList.toggle("is-live", providerMode === "openai");
}

function setAssistantBusy(busy) {
  state.assistantBusy = busy;
  elements.assistantSendButton.disabled = busy;
  elements.assistantInput.disabled = busy;
  elements.assistantSendButton.textContent = busy ? "Invio..." : "Invia";
}

function appendAssistantMessage(role, text) {
  if (!text) {
    return;
  }

  state.assistantMessages.push({ role, text });
  renderAssistantMessages();
}

function renderAssistantMessages() {
  elements.assistantMessages.innerHTML = state.assistantMessages
    .map(
      (message) => `
        <article class="assistant-message assistant-message-${message.role}">
          <div class="assistant-message-role">${message.role === "user" ? "Tu" : "Assistente"}</div>
          <p>${escapeHtml(message.text)}</p>
        </article>
      `
    )
    .join("");
  elements.assistantMessages.scrollTop = elements.assistantMessages.scrollHeight;
}

function buildInteractionContext(mapController) {
  return {
    selectedMunicipalities: mapController.getSelectedMunicipalityNames(),
    mapExtent: mapController.getMapExtent(),
  };
}

function applyAnalysisResult(mapController, analysisResult, analysisContext = null) {
  state.clipped = analysisResult.clipped;
  state.intersectedMunicipalities = analysisResult.intersectedMunicipalities || [];
  state.summary =
    analysisResult.summary ||
    summarizeClippedFeatures(analysisResult.clipped, categories, categoryByCode);
  state.calculatedValue = 0;
  state.analysisContext =
    analysisContext ||
    {
      selectedMunicipalityCount: analysisResult.requestedMunicipalities?.length || 0,
      drawnFeatureCount: 0,
    };

  mapController.clearResults();
  mapController.renderNature(analysisResult.clipped);
  mapController.renderIntersectedMunicipalities(state.intersectedMunicipalities);
  mapController.clearUserSelections();
  clearMunicipalityChecks();
  elements.municipalitySearch.value = "";
  filterMunicipalityList();
  renderStatusPanel({
    selectedMunicipalityCount: mapController.getSelectedMunicipalityCount(),
    drawnFeatureCount: mapController.getDrawnFeatureCount(),
  });
  updateActionStates(mapController);
  renderInfoSummary();
}

function updateActionStates(mapController) {
  const hasInputs = mapController.hasSelectedMunicipalities() || mapController.hasDrawnAreas();
  const hasSummary = Boolean(state.summary);
  elements.runAnalysisButton.disabled = !hasInputs;
  elements.infoButton.disabled = !hasSummary;
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

  const derivedMetrics = deriveSummaryMetrics(state.summary);
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
        });
        showNotice("PDF generato correttamente.", "success");
      } catch (error) {
        showNotice(error.message || "Errore nella generazione del PDF.", "error");
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
  updateActionStates(mapController);
}

async function runAnalysis(mapController) {
  closePopup(mapController);
  closeAppInfo(mapController);
  closeMunicipalityPanel();

  const payload = buildAnalysisPayload(mapController);
  const analysisContext = {
    selectedMunicipalityCount: mapController.getSelectedMunicipalityCount(),
    drawnFeatureCount: mapController.getDrawnFeatureCount(),
  };
  if (!payload.areas.length) {
    showNotice("Seleziona almeno un comune o disegna un'area prima di estrarre.", "warning");
    return;
  }

  setBusy(mapController, true);

  try {
    const response = await requestNatureClip(appConfig.apiUrl, payload);
    applyAnalysisResult(
      mapController,
      {
        clipped: response.clipped,
        intersectedMunicipalities: response.intersectedMunicipalities,
        summary: response.summary,
      },
      analysisContext
    );
    openPopup(mapController);
    showNotice(
      state.summary.hasSupportedVegetation
        ? "Estrazione completata. Report aggiornato."
        : "Estrazione completata, ma senza categorie supportate.",
      state.summary.hasSupportedVegetation ? "success" : "warning"
    );
  } catch (error) {
    showNotice(error.message || "Errore durante l'analisi.", "error");
  } finally {
    setBusy(mapController, false);
    updateActionStates(mapController);
  }
}

async function runAssistantInteraction(mapController, message) {
  if (!assistantConfig.enabled) {
    showNotice("Assistente disattivato dalla configurazione applicativa.", "warning");
    return;
  }

  if (state.assistantBusy) {
    return;
  }

  const trimmedMessage = message.trim();
  if (!trimmedMessage) {
    showNotice("Scrivi un messaggio prima di inviare.", "warning");
    return;
  }

  appendAssistantMessage("user", trimmedMessage);
  elements.assistantInput.value = "";
  openAssistantPanel();
  setAssistantBusy(true);

  try {
    const response = await sendInteractionMessage(appConfig.interactionUrl, {
      message: trimmedMessage,
      context: buildInteractionContext(mapController),
    });

    for (const messageItem of response.messages || []) {
      appendAssistantMessage(messageItem.role, messageItem.text);
    }

    setAssistantStatus(
      response.uiHints?.providerMode || "local",
      response.uiHints?.llmConfigured
    );

    if (response.uiHints?.warning) {
      showNotice(response.uiHints.warning, "warning");
    }

    if (response.uiHints?.mode === "reset") {
      resetAnalysis(mapController);
      showNotice("Sessione assistente e risultati locali azzerati.", "success");
    } else if (response.analysisResult) {
      applyAnalysisResult(mapController, response.analysisResult);
      showNotice("Analisi testuale completata e mappa aggiornata.", "success");
    }
  } catch (error) {
    appendAssistantMessage(
      "assistant",
      error.message || "Errore durante l'interazione testuale."
    );
    showNotice(error.message || "Errore durante l'interazione testuale.", "error");
  } finally {
    setAssistantBusy(false);
    updateActionStates(mapController);
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
    updateActionStates(mapControllerRef || mapController);
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
  elements.assistantTitle.textContent = assistantConfig.title || "Assistente Carta Natura";
  setAssistantStatus(assistantConfig.providerConfigured ? "local" : "local", assistantConfig.providerConfigured);
  renderAssistantMessages();
  updateActionStates(mapController);

  if (!assistantConfig.enabled) {
    elements.openAssistantButton.hidden = true;
    elements.assistantPanel.hidden = true;
  }

  elements.selectMunicipalityButton.addEventListener("click", () => {
    toggleMunicipalityPanel();
  });

  if (assistantConfig.enabled) {
    elements.openAssistantButton.addEventListener("click", () => {
      toggleAssistantPanel();
    });
  }

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

  if (assistantConfig.enabled) {
    elements.closeAssistantButton.addEventListener("click", () => {
      closeAssistantPanel();
    });

    elements.assistantForm.addEventListener("submit", (event) => {
      event.preventDefault();
      runAssistantInteraction(mapController, elements.assistantInput.value);
    });

    for (const chip of document.querySelectorAll(".assistant-chip")) {
      chip.addEventListener("click", () => {
        const prompt = chip.dataset.prompt || "";
        elements.assistantInput.value = prompt;
        runAssistantInteraction(mapController, prompt);
      });
    }
  }

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

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") {
      return;
    }

    if (elements.popup.classList.contains("open-popup")) {
      closePopup(mapController);
      return;
    }

    if (elements.appInfoModal.classList.contains("open-infoApp")) {
      closeAppInfo(mapController);
      return;
    }

    if (elements.assistantPanel.classList.contains("is-open")) {
      closeAssistantPanel();
      return;
    }

    closeMunicipalityPanel();
  });
}

bootstrap().catch((error) => {
  showNotice(error.message || "Errore durante inizializzazione applicazione.", "error");
});
