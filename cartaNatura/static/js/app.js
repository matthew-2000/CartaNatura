const assetVersion = document.documentElement.dataset.assetVersion || "dev";
const versionedPath = (path) =>
  `${path}${path.includes("?") ? "&" : "?"}v=${encodeURIComponent(assetVersion)}`;

let requestNatureClip;
let fetchGeoJson;
let sendInteractionMessage;
let sendInteractionMessageStream;
let deriveSummaryMetrics;
let summarizeClippedFeatures;
let formatCurrency;
let formatRoundedNumber;
let appConfig;
let assistantConfig;
let categories;
let categoryByCode;
let priceOptions;
let MapController;
let generatePdfReport;

const ASSISTANT_PANEL_WIDTH_KEY = "cartaNatura.assistantPanelWidth";
const ASSISTANT_PANEL_MIN_WIDTH = 320;
const ASSISTANT_PANEL_MAX_WIDTH = 560;

async function loadModules() {
  const [apiModule, analysisModule, configModule, mapControllerModule, pdfExportModule] =
    await Promise.all([
      import(versionedPath("./modules/api.js")),
      import(versionedPath("./modules/analysis.js")),
      import(versionedPath("./modules/config.js")),
      import(versionedPath("./modules/map-controller.js")),
      import(versionedPath("./modules/pdf-export.js")),
    ]);

  ({ requestNatureClip, fetchGeoJson, sendInteractionMessage, sendInteractionMessageStream } =
    apiModule);
  ({ deriveSummaryMetrics, summarizeClippedFeatures, formatCurrency, formatRoundedNumber } =
    analysisModule);
  ({ appConfig, assistantConfig, categories, categoryByCode, priceOptions } = configModule);
  ({ MapController } = mapControllerModule);
  ({ generatePdfReport } = pdfExportModule);
}

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
      text: "Assistente pronto.",
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
  assistantResizeHandle: document.getElementById("assistantResizeHandle"),
  assistantMessages: document.getElementById("assistantMessages"),
  assistantForm: document.getElementById("assistantForm"),
  assistantInput: document.getElementById("assistantInput"),
  assistantSendButton: document.getElementById("assistantSendButton"),
  closeAssistantButton: document.getElementById("closeAssistantPanel"),
  infoContainer: document.getElementById("infoNatura"),
  closePopupButton: document.getElementById("butchiudipopup"),
  appInfoModal: document.getElementById("infoApplicazione"),
  closeAppInfoTopButton: document.getElementById("closeInfoAppTop"),
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
  elements.runAnalysisButton.textContent = busy ? "Analisi..." : "Analizza";
  mapController.setInteractionDisabled(busy);
}

function clampAssistantPanelWidth(width) {
  const viewportLimit = Math.max(
    ASSISTANT_PANEL_MIN_WIDTH,
    Math.min(ASSISTANT_PANEL_MAX_WIDTH, Math.floor(window.innerWidth * 0.42))
  );
  return Math.max(ASSISTANT_PANEL_MIN_WIDTH, Math.min(Number(width) || 0, viewportLimit));
}

function setAssistantPanelWidth(width, { persist = true, mapController = null } = {}) {
  const nextWidth = clampAssistantPanelWidth(width);
  document.documentElement.style.setProperty("--assistant-panel-width", `${nextWidth}px`);
  elements.assistantResizeHandle?.setAttribute("aria-valuenow", String(nextWidth));

  if (persist) {
    localStorage.setItem(ASSISTANT_PANEL_WIDTH_KEY, String(nextWidth));
  }

  syncSidePanelLayout(mapController);
}

function restoreAssistantPanelWidth() {
  const storedWidth = Number(localStorage.getItem(ASSISTANT_PANEL_WIDTH_KEY));
  setAssistantPanelWidth(storedWidth || 390, { persist: false });
}

function syncSidePanelLayout(mapController = null) {
  document.body.classList.toggle(
    "side-panel-open",
    elements.municipalityPanel.classList.contains("visualizzaListaComuni") ||
      elements.popup.classList.contains("open-popup") ||
      elements.assistantPanel.classList.contains("is-open")
  );

  if (mapController) {
    window.requestAnimationFrame(() => {
      mapController.syncLayout();
      window.setTimeout(() => {
        mapController.syncLayout();
      }, 220);
    });
  }
}

function initializeAssistantResize(mapController) {
  if (!elements.assistantResizeHandle) {
    return;
  }

  let isDragging = false;

  const stopDragging = () => {
    if (!isDragging) {
      return;
    }
    isDragging = false;
    document.body.classList.remove("assistant-resizing");
    window.removeEventListener("pointermove", handlePointerMove);
    window.removeEventListener("pointerup", stopDragging);
    syncSidePanelLayout(mapController);
  };

  function handlePointerMove(event) {
    if (!isDragging) {
      return;
    }
    setAssistantPanelWidth(window.innerWidth - event.clientX, { mapController });
  }

  elements.assistantResizeHandle.addEventListener("pointerdown", (event) => {
    if (window.innerWidth <= 720) {
      return;
    }
    isDragging = true;
    document.body.classList.add("assistant-resizing");
    elements.assistantResizeHandle.setPointerCapture?.(event.pointerId);
    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", stopDragging);
    event.preventDefault();
  });

  elements.assistantResizeHandle.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
      return;
    }

    const currentWidth =
      Number.parseInt(
        getComputedStyle(document.documentElement).getPropertyValue("--assistant-panel-width"),
        10
      ) || 390;
    const step = event.shiftKey ? 48 : 24;
    let nextWidth = currentWidth;

    if (event.key === "ArrowLeft") {
      nextWidth = currentWidth + step;
    } else if (event.key === "ArrowRight") {
      nextWidth = currentWidth - step;
    } else if (event.key === "Home") {
      nextWidth = ASSISTANT_PANEL_MIN_WIDTH;
    } else if (event.key === "End") {
      nextWidth = ASSISTANT_PANEL_MAX_WIDTH;
    }

    setAssistantPanelWidth(nextWidth, { mapController });
    event.preventDefault();
  });
}

function openPopup(mapController) {
  closeMunicipalityPanel();
  closeAssistantPanel();
  closeAppInfo();
  elements.popup.classList.add("open-popup");
  elements.popup.setAttribute("aria-hidden", "false");
  syncSidePanelLayout(mapController);
}

function closePopup(mapController) {
  elements.popup.classList.remove("open-popup");
  elements.popup.setAttribute("aria-hidden", "true");
  syncSidePanelLayout(mapController);
}

function openAppInfo(mapController) {
  closeMunicipalityPanel();
  closePopup();
  closeAssistantPanel();
  elements.appInfoModal.classList.add("open-infoApp");
  elements.appInfoModal.setAttribute("aria-hidden", "false");
  document.body.classList.add("guide-modal-open");
  syncSidePanelLayout(mapController);
}

function closeAppInfo(mapController) {
  elements.appInfoModal.classList.remove("open-infoApp");
  elements.appInfoModal.setAttribute("aria-hidden", "true");
  document.body.classList.remove("guide-modal-open");
  syncSidePanelLayout(mapController);
}

function openAssistantPanel(mapController = null) {
  if (!assistantConfig.enabled) {
    return;
  }
  closeMunicipalityPanel();
  closePopup();
  closeAppInfo();
  elements.assistantPanel.classList.add("is-open");
  elements.assistantPanel.setAttribute("aria-hidden", "false");
  document.body.classList.add("assistant-panel-open");
  elements.openAssistantButton?.setAttribute("aria-expanded", "true");
  restoreAssistantPanelWidth();
  syncSidePanelLayout(mapController);
}

function closeAssistantPanel(mapController = null) {
  elements.assistantPanel.classList.remove("is-open");
  elements.assistantPanel.setAttribute("aria-hidden", "true");
  document.body.classList.remove("assistant-panel-open");
  elements.openAssistantButton?.setAttribute("aria-expanded", "false");
  syncSidePanelLayout(mapController);
}

function toggleAssistantPanel(mapController = null) {
  if (elements.assistantPanel.classList.contains("is-open")) {
    closeAssistantPanel(mapController);
    return;
  }

  openAssistantPanel(mapController);
}

function syncMunicipalityPanelState() {
  document.body.classList.toggle(
    "municipality-panel-open",
    elements.municipalityPanel.classList.contains("visualizzaListaComuni")
  );
}

function toggleMunicipalityPanel(mapController = null) {
  const shouldOpen = !elements.municipalityPanel.classList.contains("visualizzaListaComuni");
  closePopup();
  closeAssistantPanel();
  closeAppInfo();
  elements.municipalityPanel.classList.toggle("visualizzaListaComuni", shouldOpen);
  syncMunicipalityPanelState();
  syncSidePanelLayout(mapController);
}

function closeMunicipalityPanel(mapController = null) {
  elements.municipalityPanel.classList.remove("visualizzaListaComuni");
  syncMunicipalityPanelState();
  syncSidePanelLayout(mapController);
}

function setPanelCollapsed(panelElement, buttonElement, collapsed) {
  if (!panelElement || !buttonElement) {
    return;
  }
  panelElement.classList.toggle("is-collapsed", collapsed);
  buttonElement.setAttribute("aria-expanded", String(!collapsed));
  buttonElement.textContent = collapsed ? "Apri" : "Riduci";
  if (panelElement === elements.legendPanel) {
    document.body.classList.toggle("legend-modal-open", !collapsed);
  }
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

function setAssistantStatus(providerMode = null, configured = false) {
  let statusText = "Assistente non disponibile";
  if (!assistantConfig.enabled) {
    statusText = configured ? "Assistente disattivato" : "Assistente non configurato";
  } else if (providerMode === "openai" || configured) {
    statusText = "Pronto";
  }

  elements.assistantStatus.textContent = statusText;
  elements.assistantStatus.classList.toggle(
    "is-live",
    assistantConfig.enabled && (providerMode === "openai" || configured)
  );
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

function startAssistantStreamingMessage() {
  state.assistantMessages.push({
    role: "assistant",
    text: "",
    progressText: "Richiesta ricevuta...",
    streaming: true,
  });
  renderAssistantMessages();
  return state.assistantMessages.length - 1;
}

function appendAssistantStreamingDelta(messageIndex, delta) {
  if (!delta) {
    return;
  }

  const message = state.assistantMessages[messageIndex];
  if (!message) {
    return;
  }

  message.progressText = "";
  message.text += delta;
  renderAssistantMessages();
}

function setAssistantStreamingProgress(messageIndex, progressText) {
  const message = state.assistantMessages[messageIndex];
  if (!message || message.text) {
    return;
  }

  message.progressText = progressText;
  renderAssistantMessages();
}

function finalizeAssistantStreamingMessage(messageIndex, fallbackText = "") {
  const message = state.assistantMessages[messageIndex];
  if (!message) {
    return;
  }

  if (!message.text && fallbackText) {
    message.text = fallbackText;
  }

  delete message.progressText;
  delete message.streaming;
  renderAssistantMessages();
}

function removeAssistantMessage(messageIndex) {
  if (messageIndex < 0 || messageIndex >= state.assistantMessages.length) {
    return;
  }

  state.assistantMessages.splice(messageIndex, 1);
  renderAssistantMessages();
}

function extractAssistantResponseText(response) {
  const assistantMessage = (response.messages || []).find((message) => message.role === "assistant");
  return assistantMessage?.text || "";
}

function describeAssistantToolProgress(toolName) {
  if (toolName === "search_municipalities") {
    return "Cerco i comuni indicati...";
  }

  if (toolName === "analyze_municipalities") {
    return "Analizzo i comuni richiesti...";
  }

  if (toolName === "analyze_current_selection") {
    return "Analizzo la selezione corrente...";
  }

  if (toolName === "get_last_analysis") {
    return "Recupero l'ultimo report...";
  }

  if (toolName === "compare_recent_analyses") {
    return "Confronto gli ultimi report...";
  }

  if (toolName === "get_methodology") {
    return "Recupero la metodologia...";
  }

  if (toolName === "reset_analysis_context") {
    return "Azzero la sessione...";
  }

  return "Elaboro la richiesta...";
}

function renderAssistantMessages() {
  elements.assistantMessages.innerHTML = state.assistantMessages
    .map(
      (message) => `
        <article class="assistant-message assistant-message-${message.role}">
          <div class="assistant-message-role">${message.role === "user" ? "Tu" : "Assistente"}</div>
          <p>${escapeHtml(message.text || message.progressText || (message.streaming ? "..." : ""))}</p>
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
    selectionPayload: buildAnalysisPayload(mapController),
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
      ? "nessuna categoria supportata"
      : "non avviata";

  elements.statusContent.innerHTML = `
    <div class="status-chip">
      <span class="status-label">Comuni</span>
      <strong class="status-value">${inputMunicipalities}</strong>
    </div>
    <div class="status-chip">
      <span class="status-label">Geometrie</span>
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
        <h3>Nessun report disponibile</h3>
        <p>Seleziona uno o più comuni, oppure disegna un'area sulla mappa, poi avvia l'analisi.</p>
      </div>
    `;
    return;
  }

  if (!state.summary.hasSupportedVegetation) {
    elements.infoContainer.innerHTML = `
      <div class="analysis-empty-state">
        <h3>Nessuna categoria forestale supportata</h3>
        <p>L'area analizzata non contiene categorie forestali supportate dal modello corrente.</p>
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
          <span class="analysis-metric-label">CO2 annua stimata</span>
          <strong class="analysis-metric-value">${formatRoundedNumber(state.summary.totalCo2)} t</strong>
        </article>
        <article class="analysis-metric-card">
          <span class="analysis-metric-label">Superficie analizzata</span>
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
        <strong>Assorbimento annuo stimato:</strong> ${formatRoundedNumber(state.summary.totalCo2)} tonnellate di CO2.
      </div>
      <div class="analysis-valuation-card">
        <div class="analysis-section-header">
          <h4>Valorizzazione economica</h4>
          <span class="analysis-section-meta">Valore stimato in base al prezzo scelto</span>
        </div>
        <div class="value-row">
          <select id="testoValore">${renderPriceOptions()}</select>
          <button id="butcalcolavalore" type="button" class="btn btn-info btn-sm text-light">
            Calcola
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
        <span class="analysis-metric-label">Valore stimato</span>
        <strong class="analysis-value-amount">${formatCurrency(state.calculatedValue)}</strong>
      </div>
      <p class="analysis-value-actions">
        <button id="butstampadettagli" type="button" class="btn btn-success btn-sm text-light mt-3">
          Esporta PDF
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
        `<div class="pdf-status"><strong>Generazione PDF in corso...</strong></div>`
      );

      try {
        await generatePdfReport({
          summary: state.summary,
          intersectedMunicipalities: state.intersectedMunicipalities,
          selectedPrice: selectedValue,
          calculatedValue: state.calculatedValue,
          mapElement: elements.map,
        });
        showNotice("PDF generato.", "success");
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
    showNotice("Seleziona almeno un comune o disegna un'area prima di avviare l'analisi.", "warning");
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
        ? "Analisi completata. Report aggiornato."
        : "Analisi completata: nessuna categoria forestale supportata nell'area.",
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
    showNotice("Assistente non disponibile in questa configurazione.", "warning");
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
  openAssistantPanel(mapController);
  setAssistantBusy(true);

  try {
    const payload = {
      message: trimmedMessage,
      context: buildInteractionContext(mapController),
    };
    let response;

    if (appConfig.interactionStreamUrl) {
      const streamingMessageIndex = startAssistantStreamingMessage();
      let analysisApplied = false;

      try {
        response = await sendInteractionMessageStream(appConfig.interactionStreamUrl, payload, {
          onStatus: (event) => {
            if (event.phase === "started") {
              setAssistantStreamingProgress(streamingMessageIndex, "Richiesta ricevuta...");
            } else if (event.phase === "model_created") {
              setAssistantStreamingProgress(streamingMessageIndex, "Preparo la risposta...");
            }
          },
          onToolPending: (event) => {
            setAssistantStreamingProgress(
              streamingMessageIndex,
              describeAssistantToolProgress(event.toolName)
            );
          },
          onToolStart: (event) => {
            setAssistantStreamingProgress(
              streamingMessageIndex,
              describeAssistantToolProgress(event.toolName)
            );
          },
          onMessageDelta: (event) => {
            appendAssistantStreamingDelta(streamingMessageIndex, event.delta || "");
          },
          onAnalysisResult: (event) => {
            if (event.analysisResult?.clipped) {
              applyAnalysisResult(mapController, event.analysisResult);
              analysisApplied = true;
            }
            setAssistantStreamingProgress(
              streamingMessageIndex,
              "Analisi completata. Scrivo la risposta..."
            );
          },
        });
      } catch (error) {
        removeAssistantMessage(streamingMessageIndex);
        throw error;
      }

      finalizeAssistantStreamingMessage(
        streamingMessageIndex,
        extractAssistantResponseText(response)
      );

      if (!analysisApplied && response.analysisResult?.clipped) {
        applyAnalysisResult(mapController, response.analysisResult);
      }
    } else {
      response = await sendInteractionMessage(appConfig.interactionUrl, payload);

      for (const messageItem of response.messages || []) {
        appendAssistantMessage(messageItem.role, messageItem.text);
      }
    }

    setAssistantStatus(response.uiHints?.providerMode || null, assistantConfig.providerConfigured);

    if (response.uiHints?.mode === "reset") {
      resetAnalysis(mapController);
      showNotice("Sessione e risultati cancellati.", "success");
    } else if (response.analysisResult?.clipped) {
      applyAnalysisResult(mapController, response.analysisResult);
      showNotice("Analisi completata. Mappa aggiornata.", "success");
    } else if (response.uiHints?.mode === "compare_analyses") {
      showNotice("Confronto analisi completato.", "success");
    } else if (response.uiHints?.needsClarification) {
      showNotice("Serve un chiarimento per continuare.", "warning");
    } else if ((response.messages || []).length > 0) {
      showNotice("Risposta completata.", "success");
    }
  } catch (error) {
    appendAssistantMessage(
      "assistant",
      error.message || "Errore durante la richiesta all'assistente."
    );
    showNotice(error.message || "Errore durante la richiesta all'assistente.", "error");
  } finally {
    setAssistantBusy(false);
    updateActionStates(mapController);
  }
}

async function bootstrap() {
  syncChromeOffset();
  restoreAssistantPanelWidth();

  if (elements.appInfoModal?.parentElement !== document.body) {
    document.body.appendChild(elements.appInfoModal);
  }

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
  setAssistantStatus(null, assistantConfig.providerConfigured);
  renderAssistantMessages();
  updateActionStates(mapController);
  initializeAssistantResize(mapController);

  if (!assistantConfig.enabled) {
    elements.openAssistantButton.hidden = true;
    elements.assistantPanel.hidden = true;
    state.assistantMessages = [];
  }

  elements.selectMunicipalityButton.addEventListener("click", () => {
    toggleMunicipalityPanel(mapController);
  });

  if (assistantConfig.enabled) {
    elements.openAssistantButton.addEventListener("click", () => {
      toggleAssistantPanel(mapController);
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

  elements.closeAppInfoTopButton?.addEventListener("click", () => {
    closeAppInfo(mapController);
  });

  if (assistantConfig.enabled) {
    elements.closeAssistantButton.addEventListener("click", () => {
      closeAssistantPanel(mapController);
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

  window.addEventListener("resize", () => {
    syncChromeOffset();
    restoreAssistantPanelWidth();
    syncSidePanelLayout(mapController);
  });
  window.addEventListener("orientationchange", () => {
    syncChromeOffset();
    restoreAssistantPanelWidth();
    syncSidePanelLayout(mapController);
  });

  document.addEventListener("click", (event) => {
    if (window.innerWidth > 920) {
      return;
    }

    if (
      !elements.municipalityPanel.contains(event.target) &&
      event.target !== elements.selectMunicipalityButton
    ) {
      closeMunicipalityPanel(mapController);
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
      closeAssistantPanel(mapController);
      return;
    }

    closeMunicipalityPanel();
  });
}

loadModules()
  .then(() => bootstrap())
  .catch((error) => {
  console.error("Application bootstrap failed", error);
  showNotice(error.message || "Errore durante inizializzazione applicazione.", "error");
  });
