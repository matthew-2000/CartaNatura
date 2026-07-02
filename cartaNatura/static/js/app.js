const assetVersion = document.documentElement.dataset.assetVersion || "dev";
const versionedPath = (path) =>
  `${path}${path.includes("?") ? "&" : "?"}v=${encodeURIComponent(assetVersion)}`;

let requestSpatialAnalysis;
let fetchGeoJson;
let fetchAnalysisHistory;
let fetchAnalysisHistoryDetail;
let renameAnalysisHistoryItem;
let deleteAnalysisHistoryItem;
let clearAnalysisHistory;
let compareAnalysisHistory;
let sendExperimentEvent;
let startStudySession;
let clearStudySession;
let fetchStudyExport;
let transcribeVoiceMessage;
let sendInteractionMessage;
let sendInteractionMessageStream;
let deriveSummaryMetrics;
let summarizeClippedFeatures;
let buildEconomicScenarioRows;
let formatCurrency;
let formatRoundedNumber;
let appConfig;
let assistantConfig;
let categories;
let categoryByCode;
let priceOptions;
let MapController;
let generatePdfReport;
let renderAnalysisHistoryList;
let renderAnalysisComparison;
let experimentLogQueue = Promise.resolve();

const ASSISTANT_PANEL_WIDTH_KEY = "cartaNatura.assistantPanelWidth";
const ASSISTANT_PANEL_MIN_WIDTH = 320;
const ASSISTANT_PANEL_MAX_WIDTH = 560;
const MediaRecorderApi = window.MediaRecorder || null;
const ALLOWED_ASSISTANT_UI_ACTIONS = new Set([
  "show_last_analysis",
  "open_report_panel",
  "show_legend",
  "focus_map_results",
]);
const PANEL_COPY = {
  municipality: {
    title: "Selezione area",
    description: "Cerca comuni, seleziona territori e combina la scelta con geometrie disegnate.",
  },
  report: {
    title: "Report analitico",
    description: "Risultati GIS, categorie forestali, CO2 annua stimata, scenari economici ed export.",
  },
  history: {
    title: "Storico e confronto",
    description: "Gestisci analisi salvate, rinomina o elimina elementi e confronta scenari.",
  },
  assistant: {
    title: "Assistente conversazionale",
    description: "Interroga l'app con testo o voce senza perdere il contesto della mappa.",
  },
};

async function loadModules() {
  const [
    apiModule,
    analysisModule,
    configModule,
    mapControllerModule,
    pdfExportModule,
    analysisHistoryModule,
  ] =
    await Promise.all([
      import(versionedPath("./modules/api.js")),
      import(versionedPath("./modules/analysis.js")),
      import(versionedPath("./modules/config.js")),
      import(versionedPath("./modules/map-controller.js")),
      import(versionedPath("./modules/pdf-export.js")),
      import(versionedPath("./modules/analysis-history.js")),
    ]);

  ({
    requestSpatialAnalysis,
    fetchGeoJson,
    fetchAnalysisHistory,
    fetchAnalysisHistoryDetail,
    renameAnalysisHistoryItem,
    deleteAnalysisHistoryItem,
    clearAnalysisHistory,
    compareAnalysisHistory,
    sendExperimentEvent,
    startStudySession,
    clearStudySession,
    fetchStudyExport,
    transcribeVoiceMessage,
    sendInteractionMessage,
    sendInteractionMessageStream,
  } = apiModule);
  ({ deriveSummaryMetrics, summarizeClippedFeatures, buildEconomicScenarioRows, formatCurrency, formatRoundedNumber } =
    analysisModule);
  ({ appConfig, assistantConfig, categories, categoryByCode, priceOptions } = configModule);
  ({ MapController } = mapControllerModule);
  ({ generatePdfReport } = pdfExportModule);
  ({ renderAnalysisHistoryList, renderAnalysisComparison } = analysisHistoryModule);
}

const state = {
  analysisId: null,
  summary: null,
  clipped: null,
  intersectedMunicipalities: [],
  calculatedValue: 0,
  economicValueCalculated: false,
  selectedEconomicPrice: null,
  analysisContext: null,
  mapController: null,
  noticeTimer: null,
  assistantMessages: [
    {
      role: "assistant",
      text: "Assistente pronto.",
    },
  ],
  assistantBusy: false,
  voiceListening: false,
  voiceTimer: null,
  analysisHistory: {
    items: [],
    selectedIds: new Set(),
    comparison: null,
    renamingId: null,
    pendingDeleteId: null,
    confirmClear: false,
    busy: false,
  },
  study: {
    panel: null,
    session: null,
    activeTask: null,
  },
};

const elements = {
  navbar: document.querySelector(".navbar"),
  selectMunicipalityButton: document.getElementById("butSelezionaComune"),
  resetButton: document.getElementById("resetMapState"),
  openHistoryButton: document.getElementById("openHistoryPanel"),
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
  analysisHistoryPanel: document.getElementById("analysisHistoryPanel"),
  analysisHistoryStatus: document.getElementById("analysisHistoryStatus"),
  analysisHistoryList: document.getElementById("analysisHistoryList"),
  analysisHistoryComparison: document.getElementById("analysisHistoryComparison"),
  refreshHistoryButton: document.getElementById("refreshHistoryList"),
  compareHistoryButton: document.getElementById("compareHistorySelection"),
  clearHistoryButton: document.getElementById("clearHistoryList"),
  closeHistoryButton: document.getElementById("closeHistoryPanel"),
  assistantPanel: document.getElementById("assistantPanel"),
  assistantTitle: document.querySelector(".assistant-panel-title"),
  assistantStatus: document.getElementById("assistantStatus"),
  assistantResizeHandle: document.getElementById("assistantResizeHandle"),
  assistantMessages: document.getElementById("assistantMessages"),
  assistantForm: document.getElementById("assistantForm"),
  assistantInput: document.getElementById("assistantInput"),
  assistantSendButton: document.getElementById("assistantSendButton"),
  assistantVoiceButton: document.getElementById("assistantVoiceButton"),
  assistantVoiceStatus: document.getElementById("assistantVoiceStatus"),
  closeAssistantButton: document.getElementById("closeAssistantPanel"),
  infoContainer: document.getElementById("infoNatura"),
  closePopupButton: document.getElementById("butchiudipopup"),
  appInfoModal: document.getElementById("infoApplicazione"),
  closeAppInfoTopButton: document.getElementById("closeInfoAppTop"),
  closeAppInfoButton: document.getElementById("closeInfoApp"),
  workspacePanelTitle: document.getElementById("workspacePanelTitle"),
  workspacePanelDescription: document.getElementById("workspacePanelDescription"),
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
  elements.openHistoryButton.disabled = busy;
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

function getActivePanelName() {
  if (elements.municipalityPanel.classList.contains("visualizzaListaComuni")) {
    return "municipality";
  }
  if (elements.popup.classList.contains("open-popup")) {
    return "report";
  }
  if (elements.analysisHistoryPanel.classList.contains("is-open")) {
    return "history";
  }
  if (elements.assistantPanel.classList.contains("is-open")) {
    return "assistant";
  }
  return null;
}

function syncPanelChrome(activePanelName) {
  const panelCopy = activePanelName ? PANEL_COPY[activePanelName] : null;
  if (panelCopy) {
    elements.workspacePanelTitle.textContent = panelCopy.title;
    elements.workspacePanelDescription.textContent = panelCopy.description;
  }

  for (const button of document.querySelectorAll("[data-panel-nav]")) {
    const isActive = button.dataset.panelNav === activePanelName;
    button.classList.toggle("is-active", isActive);
    button.setAttribute("aria-pressed", String(isActive));
  }
}

function syncSidePanelLayout(mapController = null) {
  const activePanelName = getActivePanelName();
  document.body.classList.toggle("side-panel-open", Boolean(activePanelName));
  document.body.classList.toggle("municipality-workbench-open", activePanelName === "municipality");
  document.body.classList.toggle("report-workbench-open", activePanelName === "report");
  document.body.classList.toggle("history-workbench-open", activePanelName === "history");
  document.body.classList.toggle("assistant-workbench-open", activePanelName === "assistant");
  syncPanelChrome(activePanelName);

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

function openPopup(mapController, { source = "ui" } = {}) {
  closeMunicipalityPanel();
  closeAssistantPanel();
  closeHistoryPanel();
  closeAppInfo();
  elements.popup.classList.add("open-popup");
  elements.popup.setAttribute("aria-hidden", "false");
  elements.infoButton?.setAttribute("aria-expanded", "true");
  syncSidePanelLayout(mapController);
  if (state.analysisId) {
    recordExperiment({
      eventType: "report_opened",
      channel: source === "assistant" ? "web_chat" : "web_map",
      operation: "report_opened",
      interactionMode: source === "assistant" ? "text" : "map",
      stepCount: 1,
      details: {
        analysisId: state.analysisId,
        eventSource: source,
      },
    });
  }
}

function closePopup(mapController) {
  elements.popup.classList.remove("open-popup");
  elements.popup.setAttribute("aria-hidden", "true");
  elements.infoButton?.setAttribute("aria-expanded", "false");
  syncSidePanelLayout(mapController);
}

function openAppInfo(mapController) {
  closeMunicipalityPanel();
  closePopup();
  closeAssistantPanel();
  closeHistoryPanel();
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
  closeHistoryPanel();
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

function openHistoryPanel(mapController = null) {
  closeMunicipalityPanel();
  closePopup();
  closeAssistantPanel();
  closeAppInfo();
  elements.analysisHistoryPanel.classList.add("is-open");
  elements.analysisHistoryPanel.setAttribute("aria-hidden", "false");
  elements.openHistoryButton?.setAttribute("aria-expanded", "true");
  syncSidePanelLayout(mapController);
  recordExperiment({
    eventType: "interaction_started",
    channel: "web_map",
    operation: "analysis_history_opened",
    interactionMode: "map",
    stepCount: 1,
  });
  loadAnalysisHistory().catch((error) => {
    setHistoryStatus(error.message || "Storico non caricato.", "error");
  });
}

function closeHistoryPanel(mapController = null) {
  elements.analysisHistoryPanel.classList.remove("is-open");
  elements.analysisHistoryPanel.setAttribute("aria-hidden", "true");
  elements.openHistoryButton?.setAttribute("aria-expanded", "false");
  syncSidePanelLayout(mapController);
}

function toggleAssistantPanel(mapController = null) {
  if (elements.assistantPanel.classList.contains("is-open")) {
    closeAssistantPanel(mapController);
    return;
  }

  openAssistantPanel(mapController);
}

function toggleHistoryPanel(mapController = null) {
  if (elements.analysisHistoryPanel.classList.contains("is-open")) {
    closeHistoryPanel(mapController);
    return;
  }

  openHistoryPanel(mapController);
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
  closeHistoryPanel();
  closeAppInfo();
  elements.municipalityPanel.classList.toggle("visualizzaListaComuni", shouldOpen);
  elements.selectMunicipalityButton?.setAttribute("aria-expanded", String(shouldOpen));
  syncMunicipalityPanelState();
  syncSidePanelLayout(mapController);
}

function closeMunicipalityPanel(mapController = null) {
  elements.municipalityPanel.classList.remove("visualizzaListaComuni");
  elements.selectMunicipalityButton?.setAttribute("aria-expanded", "false");
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

function recordExperiment(event) {
  if (!appConfig?.experimentLogUrl || !sendExperimentEvent) {
    return Promise.resolve(null);
  }

  const payload = { ...event };
  const activeStudySession = state.study.session || appConfig.study?.currentSession || null;
  if (activeStudySession?.taskId && !payload.taskId) {
    payload.taskId = activeStudySession.taskId;
  }
  if (activeStudySession?.condition && !payload.condition) {
    payload.condition = activeStudySession.condition;
  }
  if (state.study.activeTask) {
    payload.taskId = state.study.activeTask.taskId;
    payload.taskRunId = payload.taskRunId || state.study.activeTask.taskRunId;
  }

  experimentLogQueue = experimentLogQueue
    .catch(() => null)
    .then(() => sendExperimentEvent(appConfig.experimentLogUrl, payload))
    .catch((error) => {
      console.debug("Experiment event not recorded", error);
      return null;
    });
  return experimentLogQueue;
}

function initializeUiActionLogging() {
  document.addEventListener(
    "click",
    (event) => {
      const control = event.target.closest("button, a, input[type='checkbox'], input[type='radio']");
      if (!control || control.closest("#studyConsole") || control.disabled) {
        return;
      }
      const controlId =
        control.id ||
        control.dataset.studyAction ||
        control.getAttribute("aria-label") ||
        control.getAttribute("name") ||
        control.tagName.toLowerCase();
      const controlLabel =
        control.getAttribute("aria-label") ||
        control.textContent?.trim() ||
        control.getAttribute("title") ||
        controlId;
      recordExperiment({
        eventType: "ui_action",
        channel: "web_map",
        operation: String(controlId).slice(0, 80),
        interactionMode: "map",
        stepCount: 1,
        details: {
          controlId: String(controlId).slice(0, 80),
          controlLabel: String(controlLabel || "").slice(0, 80),
          eventSource: "frontend",
        },
      });
    },
    { capture: true }
  );
}

function setHistoryStatus(message, tone = "info") {
  elements.analysisHistoryStatus.textContent = message;
  elements.analysisHistoryStatus.dataset.tone = tone;
}

function renderHistoryPanel() {
  const selectedIds = state.analysisHistory.selectedIds;
  const validIds = new Set(state.analysisHistory.items.map((item) => item.id));
  for (const id of [...selectedIds]) {
    if (!validIds.has(id)) {
      selectedIds.delete(id);
    }
  }
  if (state.analysisHistory.renamingId && !validIds.has(state.analysisHistory.renamingId)) {
    state.analysisHistory.renamingId = null;
  }
  if (state.analysisHistory.pendingDeleteId && !validIds.has(state.analysisHistory.pendingDeleteId)) {
    state.analysisHistory.pendingDeleteId = null;
  }

  elements.analysisHistoryList.innerHTML = renderAnalysisHistoryList({
    items: state.analysisHistory.items,
    selectedIds,
    renamingId: state.analysisHistory.renamingId,
    pendingDeleteId: state.analysisHistory.pendingDeleteId,
  });
  elements.analysisHistoryComparison.innerHTML = renderAnalysisComparison(
    state.analysisHistory.comparison
  );
  elements.compareHistoryButton.disabled = state.analysisHistory.busy;
  elements.clearHistoryButton.disabled = state.analysisHistory.items.length === 0 || state.analysisHistory.busy;
  elements.clearHistoryButton.textContent = state.analysisHistory.confirmClear ? "Conferma" : "Svuota";
  elements.refreshHistoryButton.disabled = state.analysisHistory.busy;
}

async function loadAnalysisHistory() {
  if (!appConfig.analysisHistoryUrl) {
    return;
  }

  state.analysisHistory.busy = true;
  setHistoryStatus("Caricamento...");
  renderHistoryPanel();
  try {
    const payload = await fetchAnalysisHistory(appConfig.analysisHistoryUrl);
    state.analysisHistory.items = Array.isArray(payload.items) ? payload.items : [];
    setHistoryStatus(`${state.analysisHistory.items.length} analisi salvate`);
  } finally {
    state.analysisHistory.busy = false;
    renderHistoryPanel();
  }
}

async function renameHistoryItem(analysisId) {
  state.analysisHistory.renamingId = analysisId;
  state.analysisHistory.pendingDeleteId = null;
  state.analysisHistory.confirmClear = false;
  renderHistoryPanel();
}

async function saveHistoryRename(analysisId) {
  const current = state.analysisHistory.items.find((item) => item.id === analysisId);
  if (!current) {
    return;
  }
  const input = elements.analysisHistoryPanel.querySelector(
    `[data-history-rename-input="${CSS.escape(analysisId)}"]`
  );
  const cleanLabel = String(input?.value || "").trim();
  if (!cleanLabel) {
    showNotice("Inserisci un'etichetta valida.", "warning");
    return;
  }

  try {
    await renameAnalysisHistoryItem(appConfig.analysisHistoryUrl, analysisId, cleanLabel);
    recordExperiment({
      eventType: "interaction_completed",
      channel: "web_map",
      operation: "analysis_history_rename",
      interactionMode: "map",
      stepCount: 1,
      details: { analysisId },
    });
    showNotice("Analisi rinominata.", "success");
    state.analysisHistory.renamingId = null;
    await loadAnalysisHistory();
  } catch (error) {
    showNotice(error.message || "Rinomina non completata.", "error");
  }
}

function cancelHistoryRename(analysisId) {
  if (state.analysisHistory.renamingId === analysisId) {
    state.analysisHistory.renamingId = null;
    renderHistoryPanel();
  }
}

function deleteHistoryItem(analysisId) {
  state.analysisHistory.pendingDeleteId = analysisId;
  state.analysisHistory.renamingId = null;
  state.analysisHistory.confirmClear = false;
  renderHistoryPanel();
}

async function confirmDeleteHistoryItem(analysisId) {
  const item = state.analysisHistory.items.find((entry) => entry.id === analysisId);
  if (!item) {
    return;
  }

  try {
    await deleteAnalysisHistoryItem(appConfig.analysisHistoryUrl, analysisId);
    state.analysisHistory.selectedIds.delete(analysisId);
    state.analysisHistory.comparison = null;
    state.analysisHistory.pendingDeleteId = null;
    recordExperiment({
      eventType: "interaction_completed",
      channel: "web_map",
      operation: "analysis_history_delete",
      interactionMode: "map",
      stepCount: 1,
      details: { analysisId },
    });
    showNotice("Analisi eliminata.", "success");
    await loadAnalysisHistory();
  } catch (error) {
    showNotice(error.message || "Eliminazione non completata.", "error");
  }
}

function cancelDeleteHistoryItem(analysisId) {
  if (state.analysisHistory.pendingDeleteId === analysisId) {
    state.analysisHistory.pendingDeleteId = null;
    renderHistoryPanel();
  }
}

async function clearHistory() {
  if (!state.analysisHistory.items.length) {
    return;
  }

  if (!state.analysisHistory.confirmClear) {
    state.analysisHistory.confirmClear = true;
    state.analysisHistory.pendingDeleteId = null;
    state.analysisHistory.renamingId = null;
    renderHistoryPanel();
    showNotice("Premi Conferma per svuotare lo storico.", "warning");
    return;
  }

  try {
    await clearAnalysisHistory(appConfig.analysisHistoryUrl);
    state.analysisHistory.items = [];
    state.analysisHistory.selectedIds.clear();
    state.analysisHistory.comparison = null;
    state.analysisHistory.confirmClear = false;
    recordExperiment({
      eventType: "reset_completed",
      channel: "web_map",
      operation: "analysis_history_clear",
      interactionMode: "map",
      stepCount: 1,
    });
    setHistoryStatus("0 analisi salvate");
    renderHistoryPanel();
    showNotice("Storico svuotato.", "success");
  } catch (error) {
    showNotice(error.message || "Storico non svuotato.", "error");
  }
}

async function compareSelectedHistory() {
  const ids = [...state.analysisHistory.selectedIds];
  if (ids.length < 2) {
    showNotice("Seleziona almeno due analisi da confrontare.", "warning");
    return;
  }

  state.analysisHistory.busy = true;
  setHistoryStatus("Confronto in corso...");
  renderHistoryPanel();
  recordExperiment({
    eventType: "interaction_started",
    channel: "web_map",
    operation: "analysis_history_compare",
    interactionMode: "map",
    stepCount: ids.length,
  });
  try {
    state.analysisHistory.comparison = await compareAnalysisHistory(
      appConfig.analysisHistoryUrl,
      ids
    );
    recordExperiment({
      eventType: "interaction_completed",
      channel: "web_map",
      operation: "analysis_history_compare",
      interactionMode: "map",
      stepCount: ids.length,
    });
    setHistoryStatus(`Confrontate ${ids.length} analisi`);
    showNotice("Confronto completato.", "success");
  } catch (error) {
    recordExperiment({
      eventType: "error",
      channel: "web_map",
      operation: "analysis_history_compare",
      interactionMode: "map",
      stepCount: ids.length,
      error: error.message || "history_compare_failed",
    });
    showNotice(error.message || "Confronto non completato.", "error");
  } finally {
    state.analysisHistory.busy = false;
    renderHistoryPanel();
  }
}

function isStudyConsoleEnabled() {
  return Boolean(appConfig?.study?.enabled && appConfig.study.sessionUrl);
}

function getStudySession() {
  return state.study.session || appConfig.study?.currentSession || null;
}

function setStudySession(session) {
  state.study.session = session || null;
  state.study.activeTask = session?.activeTask || null;
  if (appConfig.study) {
    appConfig.study.currentSession = session || null;
  }
  renderStudyStatus();
}

function getActiveStudyCondition() {
  return state.study.activeTask ? getStudySession()?.condition || null : null;
}

function updateStudyConditionIndicator() {
  const toggle = state.study.panel?.querySelector(".study-console-toggle");
  if (!toggle) {
    return;
  }
  const condition = getActiveStudyCondition();
  toggle.textContent = condition ? `Controllo · ${condition.toUpperCase()}` : "Controllo";
}

function applyConditionPolicy() {
  const condition = getActiveStudyCondition();
  const webgisActive = condition === "webgis";
  const conversationalActive = condition === "conversational";

  elements.openAssistantButton.disabled = webgisActive || !assistantConfig.enabled;
  elements.assistantInput.disabled = webgisActive || state.assistantBusy;
  elements.assistantSendButton.disabled = webgisActive || state.assistantBusy;
  if (elements.assistantVoiceButton) {
    elements.assistantVoiceButton.disabled =
      webgisActive || (state.assistantBusy && !state.voiceListening);
  }
  elements.assistantPanel
    ?.querySelectorAll("[data-prompt]")
    .forEach((control) => {
      control.disabled = webgisActive;
    });
  if (webgisActive) {
    closeAssistantPanel(state.mapController);
  }

  elements.selectMunicipalityButton.disabled = conversationalActive;
  elements.openHistoryButton.disabled = conversationalActive;
  if (conversationalActive) {
    closeMunicipalityPanel(state.mapController);
    closeHistoryPanel(state.mapController);
  }

  const hasInputs =
    state.mapController?.hasSelectedMunicipalities() || state.mapController?.hasDrawnAreas();
  elements.runAnalysisButton.disabled = conversationalActive || !hasInputs;

  const economicControls = elements.infoContainer?.querySelectorAll(
    "#testoValore, #butcalcolavalore, #butstampadettagli"
  );
  economicControls?.forEach((control) => {
    control.disabled = conversationalActive;
    control.title = conversationalActive
      ? "Controllo disponibile tramite assistente nella condizione conversazionale."
      : "";
  });

  document.body.classList.toggle("study-condition-webgis", webgisActive);
  document.body.classList.toggle("study-condition-conversational", conversationalActive);
  updateStudyConditionIndicator();
}

function blockedProtocolAction(control) {
  const condition = getActiveStudyCondition();
  if (!condition || !control) {
    return null;
  }
  if (
    condition === "webgis" &&
    (control.closest("#openAssistantPanel") || control.closest("#assistantPanel"))
  ) {
    return "conversational_control";
  }
  if (
    condition === "conversational" &&
    (control.closest("#butSelezionaComune") ||
      control.closest("#eseguiClipBut") ||
      control.closest("#navListaComuni") ||
      control.closest(".leaflet-draw-toolbar") ||
      control.closest("#openHistoryPanel") ||
      control.closest("#analysisHistoryPanel") ||
      control.closest("#testoValore") ||
      control.closest("#butcalcolavalore") ||
      control.closest("#butstampadettagli"))
  ) {
    return "graphical_completion_control";
  }
  return null;
}

function initializeConditionControl() {
  document.addEventListener(
    "click",
    (event) => {
      const control = event.target.closest("button, a, input, select");
      const blockedAction = blockedProtocolAction(control);
      if (!blockedAction) {
        return;
      }
      event.preventDefault();
      event.stopImmediatePropagation();
      recordExperiment({
        eventType: "protocol_violation",
        channel: "system",
        operation: blockedAction,
        interactionMode: "system",
        status: "blocked",
        details: {
          attemptedAction: control.id || control.getAttribute("aria-label") || control.tagName,
          blockedByCondition: getActiveStudyCondition(),
          eventSource: "frontend",
        },
      });
      showNotice("Azione non consentita nella condizione sperimentale attiva.", "warning");
    },
    { capture: true }
  );
}

function buildStudyTaskOptions() {
  return (appConfig.study?.tasks || [])
    .map((task) => `<option value="${escapeHtml(task.id)}">${escapeHtml(task.label)}</option>`)
    .join("");
}

function buildStudyConsole() {
  if (!isStudyConsoleEnabled()) {
    return;
  }

  const panel = document.createElement("section");
  panel.id = "studyConsole";
  panel.className = "study-console is-collapsed";
  panel.innerHTML = `
    <button type="button" class="study-console-toggle" aria-expanded="false" aria-controls="studyConsoleBody">
      Controllo
    </button>
    <div id="studyConsoleBody" class="study-console-body">
      <div class="study-console-header">
        <div>
          <div class="study-console-kicker">Riservato</div>
          <div class="study-console-title">Console operatore</div>
        </div>
        <div id="studyConsoleStatus" class="study-console-status">Non avviata</div>
      </div>
      <div class="study-console-grid">
        <label>
          <span>Codice</span>
          <input id="studyParticipantId" type="text" value="participant_001" autocomplete="off" spellcheck="false">
        </label>
        <label>
          <span>Percorso</span>
          <select id="studyCondition">
            <option value="webgis">webgis</option>
            <option value="conversational">conversational</option>
          </select>
        </label>
        <label class="study-console-wide">
          <span>Attività</span>
          <select id="studyTaskId">${buildStudyTaskOptions()}</select>
        </label>
      </div>
      <div class="study-console-actions">
        <button type="button" class="study-action is-primary" data-study-action="start-session">Avvia</button>
        <button type="button" class="study-action" data-study-action="start-task">Inizia attività</button>
        <button type="button" class="study-action" data-study-action="complete-task">Completa</button>
        <button type="button" class="study-action" data-study-action="mark-error">Errore</button>
        <button type="button" class="study-action" data-study-action="mark-unknown">Non compresa</button>
        <button type="button" class="study-action" data-study-action="export-json">JSON</button>
        <button type="button" class="study-action" data-study-action="export-jsonl">JSONL</button>
        <button type="button" class="study-action is-danger" data-study-action="reset-session">Reset</button>
      </div>
    </div>
  `;
  document.body.appendChild(panel);
  state.study.panel = panel;

  panel.querySelector(".study-console-toggle").addEventListener("click", () => {
    const collapsed = !panel.classList.contains("is-collapsed");
    panel.classList.toggle("is-collapsed", collapsed);
    panel.querySelector(".study-console-toggle").setAttribute("aria-expanded", String(!collapsed));
  });

  panel.addEventListener("click", (event) => {
    const action = event.target.closest("[data-study-action]")?.dataset.studyAction;
    if (!action) {
      return;
    }
    handleStudyAction(action);
  });

  const currentSession = getStudySession();
  if (currentSession) {
    panel.querySelector("#studyParticipantId").value = currentSession.participantId || "";
    panel.querySelector("#studyCondition").value = currentSession.condition || "webgis";
    panel.querySelector("#studyTaskId").value = currentSession.taskId || "";
  }
  renderStudyStatus();
}

function renderStudyStatus(message = null) {
  const status = state.study.panel?.querySelector("#studyConsoleStatus");
  if (!status) {
    return;
  }
  const session = getStudySession();
  if (!session) {
    status.textContent = message || "Non avviata";
    status.classList.remove("is-active");
    return;
  }
  status.textContent = message || `${session.participantId} / ${session.condition}`;
  status.classList.add("is-active");
}

async function handleStudyAction(action) {
  try {
    if (action === "start-session") {
      await startCurrentStudySession();
    } else if (action === "start-task") {
      await startStudyTask();
    } else if (action === "complete-task") {
      await finishStudyTask("task_completed", "completed");
    } else if (action === "mark-error") {
      await finishStudyTask("task_failed", "failed", { error: "manual_task_failure" });
    } else if (action === "mark-unknown") {
      await markStudyEvent("unknown_request", "manual_mark", "marked", {
        error: "manual_unknown_request",
      });
    } else if (action === "export-json") {
      await downloadStudyExport("json");
    } else if (action === "export-jsonl") {
      await downloadStudyExport("jsonl");
    } else if (action === "reset-session") {
      await resetCurrentStudySession();
    }
  } catch (error) {
    renderStudyStatus(error.message || "Errore");
    showNotice(error.message || "Operazione non completata.", "error");
  }
}

async function startCurrentStudySession() {
  const participantId = state.study.panel.querySelector("#studyParticipantId").value.trim();
  const condition = state.study.panel.querySelector("#studyCondition").value;
  const taskId = state.study.panel.querySelector("#studyTaskId").value;
  const result = await startStudySession(appConfig.study.sessionUrl, {
    participantId,
    condition,
    taskId,
  });
  setStudySession(result.session);
  if (state.mapController) {
    resetAnalysis(state.mapController, { operation: "condition_transition_reset" });
  }
  state.assistantMessages = [{ role: "assistant", text: "Assistente pronto." }];
  renderAssistantMessages();
  applyConditionPolicy();
  showNotice("Sessione riservata avviata.", "success");
}

async function startStudyTask() {
  const session = getStudySession();
  if (!session) {
    throw new Error("Avvia prima la sessione riservata.");
  }
  const taskId = state.study.panel.querySelector("#studyTaskId").value;
  if (state.mapController) {
    resetAnalysis(state.mapController, { operation: "task_transition_reset" });
  }
  state.assistantMessages = [{ role: "assistant", text: "Assistente pronto." }];
  renderAssistantMessages();
  const result = await recordExperiment({
    eventType: "task_started",
    channel: "system",
    operation: "study_task",
    interactionMode: "system",
    taskId,
    condition: session.condition,
    status: "started",
  });
  const event = result?.event;
  if (!event?.taskRunId) {
    throw new Error("Avvio attività non registrato.");
  }
  state.study.activeTask = {
    taskId: event.taskId || taskId,
    taskRunId: event.taskRunId,
  };
  applyConditionPolicy();
  renderStudyStatus(
    `In corso: ${state.study.activeTask.taskId} / ${session.condition}`
  );
}

async function finishStudyTask(eventType, status, extra = {}) {
  if (!state.study.activeTask) {
    throw new Error("Nessuna attività in corso.");
  }
  const result = await recordExperiment({
    eventType,
    channel: "system",
    operation: "study_task",
    interactionMode: "system",
    taskId: state.study.activeTask.taskId,
    taskRunId: state.study.activeTask.taskRunId,
    status,
    ...extra,
  });
  if (!result?.event) {
    throw new Error("Chiusura attività non registrata.");
  }
  state.study.activeTask = null;
  applyConditionPolicy();
  renderStudyStatus(status === "completed" ? "Completata" : "Terminata con errore");
}

async function markStudyEvent(eventType, operation, status, extra = {}) {
  if (!getStudySession()) {
    throw new Error("Avvia prima la sessione riservata.");
  }
  await recordExperiment({
    eventType,
    channel: "system",
    operation,
    interactionMode: "system",
    status,
    stepCount: 1,
    ...extra,
  });
  renderStudyStatus(status === "completed" ? "Completata" : "Evento registrato");
}

async function downloadStudyExport(format) {
  if (!getStudySession()) {
    throw new Error("Nessuna sessione attiva da esportare.");
  }
  const session = getStudySession();
  const payload = await fetchStudyExport(appConfig.study.sessionUrl, format);
  const text =
    format === "jsonl" ? payload : JSON.stringify(payload.export || payload, null, 2);
  const blob = new Blob([text], {
    type: format === "jsonl" ? "application/jsonl" : "application/json",
  });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `${session.participantId}_${session.studySessionId}.${format}`;
  document.body.appendChild(link);
  link.click();
  URL.revokeObjectURL(link.href);
  link.remove();
  renderStudyStatus("Esportata");
}

async function resetCurrentStudySession() {
  if (state.study.activeTask) {
    await finishStudyTask("task_interrupted", "interrupted", {
      error: "study_session_reset",
    });
  }
  if (getStudySession()) {
    await recordExperiment({
      eventType: "reset_completed",
      channel: "system",
      operation: "study_console_reset",
      interactionMode: "system",
      status: "completed",
    });
  }
  await clearStudySession(appConfig.study.sessionUrl);
  setStudySession(null);
  if (state.mapController) {
    resetAnalysis(state.mapController, { operation: "condition_transition_reset" });
  }
  applyConditionPolicy();
  renderStudyStatus("Reset completato");
  showNotice("Sessione riservata azzerata.", "success");
}

function elapsedSince(startedAt) {
  return Math.max(0, Math.round(performance.now() - startedAt));
}

function buildAnalysisEventDetails(mapController, analysisResult = null, analysisContext = null) {
  const summary = analysisResult?.summary || state.summary || {};
  return {
    analysisId: analysisResult?.analysisId || state.analysisId,
    selectedMunicipalityCount:
      analysisContext?.selectedMunicipalityCount ?? mapController.getSelectedMunicipalityCount(),
    drawnFeatureCount: analysisContext?.drawnFeatureCount ?? mapController.getDrawnFeatureCount(),
    intersectedMunicipalityCount:
      analysisResult?.intersectedMunicipalities?.length || state.intersectedMunicipalities.length,
    categoryCount: summary.items?.length || 0,
    hasSupportedVegetation: Boolean(summary.hasSupportedVegetation),
    totalCo2: Number(summary.totalCo2 || 0),
  };
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
  if (elements.assistantVoiceButton) {
    elements.assistantVoiceButton.disabled = busy && !state.voiceListening;
    elements.assistantVoiceButton.classList.toggle("is-unavailable", !isVoiceRecordingSupported());
  }
  elements.assistantSendButton.setAttribute("aria-busy", String(busy));
  applyConditionPolicy();
}

function setVoiceButtonState({ listening = state.voiceListening, unavailable = false } = {}) {
  if (!elements.assistantVoiceButton) {
    return;
  }
  const label = unavailable
    ? "Registrazione vocale non supportata da questo browser"
    : listening
      ? "Ferma e trascrivi registrazione"
      : "Registra messaggio vocale";
  elements.assistantVoiceButton.classList.toggle("is-listening", listening);
  elements.assistantVoiceButton.classList.toggle("is-unavailable", unavailable);
  elements.assistantVoiceButton.setAttribute("aria-pressed", String(listening));
  elements.assistantVoiceButton.setAttribute("aria-label", label);
  elements.assistantVoiceButton.title = label;
}

function setVoiceListening(listening) {
  state.voiceListening = listening;
  setVoiceButtonState({ listening });
}

const voiceStatusIcons = {
  cancel:
    '<svg aria-hidden="true" viewBox="0 0 24 24" class="assistant-action-icon"><path d="M18 6 6 18"></path><path d="m6 6 12 12"></path></svg>',
  transcribe:
    '<svg aria-hidden="true" viewBox="0 0 24 24" class="assistant-action-icon"><path d="m5 12 5 5L20 7"></path></svg>',
  send:
    '<svg aria-hidden="true" viewBox="0 0 24 24" class="assistant-action-icon"><path d="M12 19V5"></path><path d="M5 12l7-7 7 7"></path></svg>',
};

function createVoiceStatusAction({ label, icon, className = "", onClick }) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `assistant-status-icon-button ${className}`.trim();
  button.setAttribute("aria-label", label);
  button.title = label;
  button.innerHTML = icon;
  button.addEventListener("click", onClick);
  return button;
}

function setVoiceStatus(message = "", tone = "info", actions = []) {
  if (!elements.assistantVoiceStatus) {
    return;
  }

  const nextMessage = String(message || "").trim();
  elements.assistantVoiceStatus.hidden = !nextMessage;
  elements.assistantVoiceStatus.className = `assistant-voice-status is-${tone}`;
  elements.assistantVoiceStatus.replaceChildren();
  if (!nextMessage) {
    return;
  }

  const wave = document.createElement("span");
  wave.className = "assistant-voice-wave";
  wave.setAttribute("aria-hidden", "true");
  for (let index = 0; index < 5; index += 1) {
    wave.appendChild(document.createElement("span"));
  }

  const text = document.createElement("span");
  text.className = "assistant-voice-status-text";
  text.textContent = nextMessage;
  elements.assistantVoiceStatus.append(wave, text);

  if (actions.length > 0) {
    const actionGroup = document.createElement("span");
    actionGroup.className = "assistant-voice-status-actions";
    actionGroup.append(...actions);
    elements.assistantVoiceStatus.append(actionGroup);
  }
}

function formatVoiceElapsed(durationMs) {
  const totalSeconds = Math.max(0, Math.floor(durationMs / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = String(totalSeconds % 60).padStart(2, "0");
  return `${minutes}:${seconds}`;
}

function stopVoiceTimer() {
  if (state.voiceTimer) {
    window.clearInterval(state.voiceTimer);
    state.voiceTimer = null;
  }
}

function isVoiceRecordingSupported() {
  return Boolean(navigator.mediaDevices?.getUserMedia && MediaRecorderApi);
}

function getSupportedAudioMimeType() {
  if (!MediaRecorderApi?.isTypeSupported) {
    return "";
  }

  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4",
    "audio/ogg;codecs=opus",
  ];
  return candidates.find((mimeType) => MediaRecorderApi.isTypeSupported(mimeType)) || "";
}

function audioFilenameForMimeType(mimeType) {
  if (mimeType.includes("mp4")) {
    return "voice-message.mp4";
  }
  if (mimeType.includes("ogg")) {
    return "voice-message.ogg";
  }
  return "voice-message.webm";
}

function initializeVoiceInput(mapController) {
  if (!elements.assistantVoiceButton) {
    return;
  }

  if (!isVoiceRecordingSupported()) {
    elements.assistantVoiceButton.disabled = false;
    setVoiceButtonState({ unavailable: true });
    elements.assistantVoiceButton.addEventListener("click", () => {
      setVoiceStatus("Registrazione vocale non supportata da questo browser.", "warning");
      recordExperiment({
        eventType: "error",
        channel: "voice",
        operation: "voice_input",
        interactionMode: "voice",
        error: "media_recorder_unavailable",
      });
    });
    return;
  }

  setVoiceButtonState();

  let recorder = null;
  let audioChunks = [];
  let audioStream = null;
  let recordingStartedAt = 0;
  let recordingAction = "transcribe";

  const stopRecording = (action = "transcribe") => {
    recordingAction = action;
    if (recorder && recorder.state !== "inactive") {
      recorder.stop();
    }
  };

  const renderRecordingStatus = () => {
    const cancelAction = createVoiceStatusAction({
      label: "Annulla registrazione",
      icon: voiceStatusIcons.cancel,
      className: "is-cancel",
      onClick: () => stopRecording("cancel"),
    });
    const transcribeAction = createVoiceStatusAction({
      label: "Trascrivi senza inviare",
      icon: voiceStatusIcons.transcribe,
      className: "is-confirm",
      onClick: () => stopRecording("transcribe"),
    });
    const sendAction = createVoiceStatusAction({
      label: "Trascrivi e invia",
      icon: voiceStatusIcons.send,
      className: "is-send",
      onClick: () => stopRecording("send"),
    });
    setVoiceStatus(
      `Registrazione ${formatVoiceElapsed(elapsedSince(recordingStartedAt))}`,
      "recording",
      [cancelAction, transcribeAction, sendAction]
    );
  };

  elements.assistantVoiceButton.addEventListener("click", () => {
    if (state.assistantBusy) {
      return;
    }

    if (state.voiceListening) {
      stopRecording("transcribe");
      return;
    }

    startVoiceRecording(mapController).catch((error) => {
      setVoiceListening(false);
      stopVoiceTimer();
      setVoiceStatus("Input vocale non acquisito.", "warning");
      recordExperiment({
        eventType: "error",
        channel: "voice",
        operation: "voice_input",
        interactionMode: "voice",
        error: error.message || "voice_recording_failed",
      });
    });
  });

  async function startVoiceRecording(mapControllerRef) {
    audioChunks = [];
    audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mimeType = getSupportedAudioMimeType();
    recordingAction = "transcribe";
    recorder = new MediaRecorderApi(
      audioStream,
      mimeType ? { mimeType } : undefined
    );
    recordingStartedAt = performance.now();

    recorder.addEventListener("dataavailable", (event) => {
      if (event.data?.size > 0) {
        audioChunks.push(event.data);
      }
    });

    recorder.addEventListener("stop", () => {
      const durationMs = elapsedSince(recordingStartedAt);
      const recordedType = recorder.mimeType || mimeType || "audio/webm";
      const audioBlob = new Blob(audioChunks, { type: recordedType });
      audioStream?.getTracks().forEach((track) => track.stop());
      audioStream = null;
      setVoiceListening(false);
      stopVoiceTimer();

      if (recordingAction === "cancel") {
        audioChunks = [];
        setVoiceStatus("");
        return;
      }

      if (!audioBlob.size) {
        setVoiceStatus("Nessun audio registrato.", "warning");
        return;
      }

      handleVoiceAudioBlob(mapControllerRef, audioBlob, durationMs, recordedType, {
        sendAfterTranscription: recordingAction === "send",
      });
    });

    setVoiceListening(true);
    stopVoiceTimer();
    renderRecordingStatus();
    state.voiceTimer = window.setInterval(renderRecordingStatus, 1000);
    recordExperiment({
      eventType: "voice_started",
      channel: "voice",
      operation: "voice_input",
      interactionMode: "voice",
      stepCount: 1,
    });
    recorder.start();
  }

  async function handleVoiceAudioBlob(
    mapControllerRef,
    audioBlob,
    durationMs,
    mimeType,
    { sendAfterTranscription = false } = {}
  ) {
    setAssistantBusy(true);
    try {
      setVoiceStatus(
        sendAfterTranscription ? "Trascrizione in corso. Invio automatico..." : "Trascrizione in corso...",
        "processing"
      );
      const result = await transcribeVoiceMessage(
        appConfig.voiceTranscriptionUrl,
        audioBlob,
        {
          durationMs,
          filename: audioFilenameForMimeType(mimeType),
        }
      );
      const transcript = String(result.transcript || "").trim();
      if (!transcript) {
        throw new Error("Nessun testo riconosciuto.");
      }
      elements.assistantInput.value = transcript;
      elements.assistantInput.focus();
      if (sendAfterTranscription) {
        setVoiceStatus("Trascrizione completata. Invio...", "success");
        setAssistantBusy(false);
        await runAssistantInteraction(mapControllerRef, transcript, { interactionMode: "voice" });
        setVoiceStatus("");
      } else {
        setVoiceStatus("Trascrizione pronta. Modifica o invia.", "success");
      }
    } catch (error) {
      recordExperiment({
        eventType: "error",
        channel: "voice",
        operation: "voice_transcription",
        interactionMode: "voice",
        durationMs,
        error: error.message || "voice_transcription_failed",
      });
      setVoiceStatus(error.message || "Trascrizione vocale non riuscita.", "error");
    } finally {
      if (state.assistantBusy) {
        setAssistantBusy(false);
      }
      updateActionStates(mapControllerRef);
    }
  }
}

function appendAssistantMessage(role, text) {
  if (!text) {
    return -1;
  }

  state.assistantMessages.push({ role, text });
  renderAssistantMessages();
  return state.assistantMessages.length - 1;
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

function finalizeAssistantStreamingMessage(messageIndex, finalText = "") {
  const message = state.assistantMessages[messageIndex];
  if (!message) {
    return;
  }

  if (finalText) {
    message.text = finalText;
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

function normalizeAssistantList(value) {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .map((item) => String(item || "").trim())
    .filter(Boolean)
    .slice(0, 4);
}

function normalizeAssistantUiActions(value) {
  return normalizeAssistantList(value).filter((action) => ALLOWED_ASSISTANT_UI_ACTIONS.has(action));
}

function attachAssistantHints(messageIndex, uiHints = {}) {
  const message = state.assistantMessages[messageIndex];
  if (!message || message.role !== "assistant") {
    return;
  }

  message.followUpSuggestions = normalizeAssistantList(uiHints.followUpSuggestions);
  message.uiActions = normalizeAssistantUiActions(uiHints.uiActions);
  renderAssistantMessages();
}

function applyAssistantUiActions(mapController, uiActions = []) {
  const actions = normalizeAssistantUiActions(uiActions);
  if (!actions.length) {
    return;
  }

  let reportOpened = false;
  for (const action of actions) {
    if (action === "show_last_analysis" || action === "open_report_panel") {
      if (reportOpened) {
        continue;
      }
      renderInfoSummary();
      openPopup(mapController, { source: "assistant" });
      reportOpened = true;
    } else if (action === "show_legend") {
      setPanelCollapsed(elements.legendPanel, elements.toggleLegendPanelButton, false);
    } else if (action === "focus_map_results") {
      mapController.syncLayout();
    }
  }
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

  if (toolName === "calculate_economic_value") {
    return "Calcolo il valore economico...";
  }

  if (toolName === "compare_economic_scenarios") {
    return "Confronto gli scenari economici...";
  }

  if (toolName === "prepare_report") {
    return "Preparo il report esistente...";
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
          ${renderAssistantHintList(message)}
        </article>
      `
    )
    .join("");
  elements.assistantMessages.scrollTop = elements.assistantMessages.scrollHeight;
}

function renderAssistantHintList(message) {
  const followUps = normalizeAssistantList(message.followUpSuggestions);
  const uiActions = normalizeAssistantUiActions(message.uiActions);
  if (!followUps.length && !uiActions.length) {
    return "";
  }

  const followUpButtons = followUps
    .map(
      (item) =>
        `<button type="button" class="assistant-suggestion" data-assistant-prompt="${escapeHtml(
          item
        )}">${escapeHtml(item)}</button>`
    )
    .join("");
  const actionItems = uiActions
    .map((item) => `<span class="assistant-ui-action">${escapeHtml(item)}</span>`)
    .join("");

  return `
    <div class="assistant-message-hints">
      ${followUpButtons}
      ${actionItems}
    </div>
  `;
}

function buildInteractionContext(mapController) {
  return {
    selectedMunicipalities: mapController.getSelectedMunicipalityNames(),
    mapExtent: mapController.getMapExtent(),
    selectionPayload: buildAnalysisPayload(mapController),
  };
}

function applyAnalysisResult(mapController, analysisResult, analysisContext = null) {
  state.analysisId = analysisResult.analysisId || null;
  state.clipped = analysisResult.clipped;
  state.intersectedMunicipalities = analysisResult.intersectedMunicipalities || [];
  state.summary =
    analysisResult.summary ||
    summarizeClippedFeatures(analysisResult.clipped, categories, categoryByCode);
  state.calculatedValue = 0;
  state.economicValueCalculated = false;
  state.selectedEconomicPrice = priceOptions[0]?.value ?? null;
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
  if (elements.analysisHistoryPanel.classList.contains("is-open")) {
    loadAnalysisHistory().catch((error) => {
      setHistoryStatus(error.message || "Storico non aggiornato.", "error");
    });
  }
}

function applyEconomicResult(
  economicResult,
  { interactionMode = "text", recordEvent = true } = {}
) {
  if (!economicResult || !Number.isFinite(Number(economicResult.totalValueEur))) {
    return;
  }

  state.analysisId = economicResult.analysisId || state.analysisId;
  state.selectedEconomicPrice = Number(economicResult.priceEurPerTon || 0);
  state.calculatedValue = Number(economicResult.totalValueEur || 0);
  state.economicValueCalculated = true;
  renderInfoSummary();
  if (recordEvent) {
    recordExperiment({
      eventType: "valuation_completed",
      channel: interactionMode === "voice" ? "voice" : "web_chat",
      operation: "economic_valuation",
      interactionMode,
      stepCount: 1,
      details: {
        analysisId: state.analysisId,
        scenarioKey: economicResult.scenarioKey,
        priceEurPerTon: state.selectedEconomicPrice,
        totalCo2: Number(economicResult.totalCo2 || state.summary?.totalCo2 || 0),
        totalValueEur: state.calculatedValue,
      },
    });
  }
}

function updateActionStates(mapController) {
  const hasInputs = mapController.hasSelectedMunicipalities() || mapController.hasDrawnAreas();
  const hasSummary = Boolean(state.summary);
  elements.runAnalysisButton.disabled =
    getActiveStudyCondition() === "conversational" || !hasInputs;
  elements.infoButton.disabled = !hasSummary;
  applyConditionPolicy();
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

function renderScenarioComparisonTable(selectedPrice) {
  const rows = buildEconomicScenarioRows(state.summary, priceOptions, selectedPrice);
  if (!rows.length) {
    return "";
  }

  return `
    <div class="scenario-comparison-card">
      <div class="analysis-section-header">
        <h4>Confronto scenari economici</h4>
        <span class="analysis-section-meta">${formatRoundedNumber(state.summary?.totalCo2 || 0)} tCO2/anno</span>
      </div>
      <div class="scenario-table-wrap">
        <table class="scenario-table">
          <thead>
            <tr>
              <th>Scenario</th>
              <th>Prezzo</th>
              <th>Valore stimato</th>
              <th>Stato</th>
            </tr>
          </thead>
          <tbody>
            ${rows
              .map(
                (row) => `
                  <tr class="${row.selected ? "is-selected" : ""}">
                    <td>
                      <strong>${escapeHtml(row.label)}</strong>
                      ${row.description ? `<small>${escapeHtml(row.description)}</small>` : ""}
                    </td>
                    <td>${formatRoundedNumber(row.price)} €/tCO2</td>
                    <td>${formatCurrency(row.value)}</td>
                    <td>${row.selected ? "Selezionato" : ""}</td>
                  </tr>
                `
              )
              .join("")}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

function updateScenarioComparison(selectedPrice) {
  const comparisonRoot = document.getElementById("scenarioComparison");
  if (!comparisonRoot || !state.summary) {
    return;
  }
  comparisonRoot.innerHTML = renderScenarioComparisonTable(selectedPrice);
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
      <div class="analysis-report-intro">
        <div>
          <span class="analysis-metric-label">Analisi corrente</span>
          <h3>Quadro sintetico dell'area</h3>
        </div>
        <span class="analysis-report-badge">${state.intersectedMunicipalities.length} comuni interessati</span>
      </div>
      <div class="analysis-report-layout">
        <div class="analysis-report-primary">
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
        </div>
        <div class="analysis-report-secondary">
          <div class="analysis-valuation-card">
            <div class="analysis-section-header">
              <h4>Valorizzazione economica</h4>
              <span class="analysis-section-meta">Prezzo scelto</span>
            </div>
            <div class="value-row">
              <select id="testoValore">${renderPriceOptions()}</select>
              <button id="butcalcolavalore" type="button" class="btn btn-info btn-sm text-light">
                Calcola
              </button>
            </div>
            <div id="valoreTotaleCalcolato" class="value-result"></div>
            <div id="scenarioComparison" class="scenario-comparison-root">
              ${renderScenarioComparisonTable(state.selectedEconomicPrice ?? priceOptions[0]?.value)}
            </div>
          </div>
        </div>
      </div>
    </div>
  `;

  const priceSelect = document.getElementById("testoValore");
  const calculateButton = document.getElementById("butcalcolavalore");
  priceSelect.value = String(state.selectedEconomicPrice ?? priceOptions[0]?.value ?? "");
  priceSelect.addEventListener("change", () => {
    if (getActiveStudyCondition() === "conversational") {
      applyConditionPolicy();
      return;
    }
    const selectedValue = Number(priceSelect.value || 0);
    state.selectedEconomicPrice = selectedValue;
    updateScenarioComparison(selectedValue);
    recordExperiment({
      eventType: "interaction_completed",
      channel: "web_map",
      operation: "scenario_comparison_viewed",
      interactionMode: "map",
      stepCount: 1,
      details: {
        analysisId: state.analysisId,
        scenarioKey: priceOptions.find((option) => Number(option.value) === selectedValue)?.key,
        priceEurPerTon: selectedValue,
        totalCo2: Number(state.summary.totalCo2 || 0),
      },
    });

    if (state.economicValueCalculated) {
      state.calculatedValue = selectedValue * state.summary.totalCo2;
      renderSelectedScenarioValue(selectedValue, calculateButton);
    }
  });

  function renderSelectedScenarioValue(selectedValue, calculateButtonRef) {
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
      if (getActiveStudyCondition() === "conversational") {
        return;
      }
      const reportStartedAt = performance.now();
      const printButton = document.getElementById("butstampadettagli");
      const closeButton = elements.closePopupButton;
      calculateButtonRef.disabled = true;
      printButton.disabled = true;
      closeButton.disabled = true;
      resultRoot.insertAdjacentHTML(
        "beforeend",
        `<div class="pdf-status"><strong>Generazione PDF in corso...</strong></div>`
      );

      try {
        await generatePdfReport({
          analysisId: state.analysisId,
          summary: state.summary,
          intersectedMunicipalities: state.intersectedMunicipalities,
          selectedPrice: selectedValue,
          calculatedValue: state.calculatedValue,
          priceOptions,
          mapElement: elements.map,
          analysisUtils: {
            buildEconomicScenarioRows,
            deriveSummaryMetrics,
            formatCurrency,
            formatRoundedNumber,
          },
        });
        recordExperiment({
          eventType: "report_generated",
          channel: "web_map",
          operation: "report_generation",
          interactionMode: "map",
          durationMs: elapsedSince(reportStartedAt),
          stepCount: 1,
          details: {
            reportFormat: "pdf",
            analysisId: state.analysisId,
            scenarioKey: priceOptions.find((option) => Number(option.value) === selectedValue)?.key,
            priceEurPerTon: selectedValue,
            totalCo2: Number(state.summary.totalCo2 || 0),
            totalValueEur: state.calculatedValue,
          },
        });
        showNotice("PDF generato.", "success");
      } catch (error) {
        const failureStatus =
          error?.name === "AbortError" || /timeout/i.test(error?.message || "")
            ? "timeout"
            : "failed";
        recordExperiment({
          eventType: "error",
          channel: "web_map",
          operation: "report_generation",
          interactionMode: "map",
          durationMs: elapsedSince(reportStartedAt),
          status: failureStatus,
          error: error.message || "pdf_generation_failed",
          details: {
            analysisId: state.analysisId,
            scenarioKey: priceOptions.find((option) => Number(option.value) === selectedValue)?.key,
            priceEurPerTon: selectedValue,
            totalValueEur: state.calculatedValue,
            taskOutcome: failureStatus,
          },
        });
        showNotice(error.message || "Errore nella generazione del PDF.", "error");
      } finally {
        calculateButtonRef.disabled = false;
        printButton.disabled = false;
        closeButton.disabled = false;
        const status = resultRoot.querySelector(".pdf-status");
        if (status) {
          status.remove();
        }
      }
    });
  }

  calculateButton.addEventListener("click", () => {
    if (getActiveStudyCondition() === "conversational") {
      return;
    }
    const valuationStartedAt = performance.now();
    const selectedValue = Number(priceSelect.value || 0);
    state.selectedEconomicPrice = selectedValue;
    state.calculatedValue = selectedValue * state.summary.totalCo2;
    state.economicValueCalculated = true;
    updateScenarioComparison(selectedValue);
    recordExperiment({
      eventType: "valuation_completed",
      channel: "web_map",
      operation: "economic_valuation",
      interactionMode: "map",
      durationMs: elapsedSince(valuationStartedAt),
      stepCount: 1,
      details: {
        analysisId: state.analysisId,
        scenarioKey: priceOptions.find((option) => Number(option.value) === selectedValue)?.key,
        priceEurPerTon: selectedValue,
        totalCo2: Number(state.summary.totalCo2 || 0),
        totalValueEur: state.calculatedValue,
      },
    });
    renderSelectedScenarioValue(selectedValue, calculateButton);
  });

  if (state.economicValueCalculated) {
    renderSelectedScenarioValue(state.selectedEconomicPrice, calculateButton);
  }
  applyConditionPolicy();
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

function resetAnalysis(mapController, { operation = "reset_analysis_workspace" } = {}) {
  state.analysisId = null;
  state.summary = null;
  state.clipped = null;
  state.intersectedMunicipalities = [];
  state.calculatedValue = 0;
  state.economicValueCalculated = false;
  state.selectedEconomicPrice = null;
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
  closeHistoryPanel(mapController);
  updateActionStates(mapController);
  recordExperiment({
    eventType: "reset_completed",
    channel: "web_map",
    operation,
    interactionMode: "map",
    stepCount: 1,
  });
}

async function runAnalysis(mapController) {
  const analysisStartedAt = performance.now();
  if (getActiveStudyCondition() === "conversational") {
    recordExperiment({
      eventType: "protocol_violation",
      channel: "web_map",
      operation: "spatial_analysis_ui",
      interactionMode: "map",
      status: "blocked",
      details: {
        attemptedAction: "spatial_analysis_ui",
        blockedByCondition: "conversational",
        eventSource: "frontend",
      },
    });
    showNotice("Analisi disponibile tramite assistente in questa condizione.", "warning");
    return;
  }
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
    recordExperiment({
      eventType: "error",
      channel: "web_map",
      operation: "spatial_analysis",
      interactionMode: "map",
      status: "failed",
      error: "missing_selection",
      details: {
        ...buildAnalysisEventDetails(mapController),
        taskOutcome: "failed",
      },
    });
    return;
  }

  setBusy(mapController, true);

  try {
    const response = await requestSpatialAnalysis(appConfig.apiUrl, payload);
    applyAnalysisResult(
      mapController,
      {
        analysisId: response.analysisId,
        clipped: response.clipped,
        intersectedMunicipalities: response.intersectedMunicipalities,
        summary: response.summary,
      },
      analysisContext
    );
    openPopup(mapController, { source: "analysis" });
    showNotice(
      state.summary.hasSupportedVegetation
        ? "Analisi completata. Report aggiornato."
        : "Analisi completata: nessuna categoria forestale supportata nell'area.",
      state.summary.hasSupportedVegetation ? "success" : "warning"
    );
  } catch (error) {
    const failureStatus =
      error?.name === "AbortError" || /timeout/i.test(error?.message || "") ? "timeout" : "failed";
    recordExperiment({
      eventType: "error",
      channel: "web_map",
      operation: "spatial_analysis",
      interactionMode: "map",
      durationMs: elapsedSince(analysisStartedAt),
      status: failureStatus,
      error: error.message || "analysis_failed",
      details: {
        ...buildAnalysisEventDetails(mapController),
        taskOutcome: failureStatus,
      },
    });
    showNotice(error.message || "Errore durante l'analisi.", "error");
  } finally {
    setBusy(mapController, false);
    updateActionStates(mapController);
  }
}

async function runAssistantInteraction(mapController, message, { interactionMode = "text" } = {}) {
  const interactionStartedAt = performance.now();
  if (getActiveStudyCondition() === "webgis") {
    recordExperiment({
      eventType: "protocol_violation",
      channel: interactionMode === "voice" ? "voice" : "web_chat",
      operation: "conversational_request",
      interactionMode,
      status: "blocked",
      details: {
        attemptedAction: "conversational_request",
        blockedByCondition: "webgis",
        eventSource: "frontend",
      },
    });
    showNotice("Assistente non consentito nella condizione WebGIS.", "warning");
    return;
  }
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
  let response;
  let analysisApplied = false;
  const activeToolCalls = new Map();

  try {
    const payload = {
      message: trimmedMessage,
      context: buildInteractionContext(mapController),
      metadata: {
        interactionMode,
        studySessionId: getStudySession()?.studySessionId || null,
      },
    };
    recordExperiment({
      eventType: "chat_message",
      channel: interactionMode === "voice" ? "voice" : "web_chat",
      operation: "conversational_request",
      interactionMode,
      stepCount: 1,
      details: {
        messageLength: trimmedMessage.length,
        eventSource: "frontend",
      },
      userText: trimmedMessage,
      userTranscript: interactionMode === "voice" ? trimmedMessage : "",
    });

    if (appConfig.interactionStreamUrl) {
      const streamingMessageIndex = startAssistantStreamingMessage();

      try {
        response = await sendInteractionMessageStream(appConfig.interactionStreamUrl, payload, {
          onStatus: (event) => {
            if (event.stage === "started") {
              setAssistantStreamingProgress(streamingMessageIndex, "Richiesta ricevuta...");
            } else if (event.stage === "model_created") {
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
            activeToolCalls.set(event.toolCallId || event.toolName, event.toolName);
            recordExperiment({
              eventType: "tool_started",
              channel: interactionMode === "voice" ? "voice" : "web_chat",
              operation: event.toolName || "assistant_tool",
              interactionMode,
              status: "started",
              details: {
                toolName: event.toolName || "",
                toolCallId: event.toolCallId || "",
                eventSource: "assistant_runtime",
              },
            });
          },
          onToolResult: (event) => {
            activeToolCalls.delete(event.toolCallId || event.toolName);
            recordExperiment({
              eventType: "tool_completed",
              channel: interactionMode === "voice" ? "voice" : "web_chat",
              operation: event.toolName || "assistant_tool",
              interactionMode,
              status: "completed",
              details: {
                toolName: event.toolName || "",
                toolCallId: event.toolCallId || "",
                eventSource: "assistant_runtime",
              },
            });
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
      attachAssistantHints(streamingMessageIndex, response.uiHints);

      if (!analysisApplied && response.analysisResult?.clipped) {
        applyAnalysisResult(mapController, response.analysisResult);
      }
    } else {
      response = await sendInteractionMessage(appConfig.interactionUrl, payload);
      let lastAssistantMessageIndex = -1;

      for (const messageItem of response.messages || []) {
        const messageIndex = appendAssistantMessage(messageItem.role, messageItem.text);
        if (messageItem.role === "assistant") {
          lastAssistantMessageIndex = messageIndex;
        }
      }

      attachAssistantHints(lastAssistantMessageIndex, response.uiHints);
    }

    setAssistantStatus(response.uiHints?.providerMode || null, assistantConfig.providerConfigured);
    if (response.economicResult) {
      applyEconomicResult(response.economicResult, { interactionMode });
    } else if (response.reportContext?.economicResult) {
      applyEconomicResult(response.reportContext.economicResult, {
        interactionMode,
        recordEvent: false,
      });
    }
    applyAssistantUiActions(mapController, response.uiHints?.uiActions);

    if (response.uiHints?.mode === "reset") {
      resetAnalysis(mapController);
    } else if (!analysisApplied && response.analysisResult?.clipped) {
      applyAnalysisResult(mapController, response.analysisResult);
    } else if (response.uiHints?.needsClarification) {
      showNotice("Serve un chiarimento per continuare.", "warning");
    }
    const responseAnalysisId =
      response.analysisResult?.analysisId ||
      response.economicResult?.analysisId ||
      response.reportContext?.analysisId ||
      state.analysisId;
    recordExperiment({
      eventType: "chat_response",
      channel: interactionMode === "voice" ? "voice" : "web_chat",
      operation: response.uiHints?.mode || "conversational_request",
      interactionMode,
      durationMs: elapsedSince(interactionStartedAt),
      stepCount: response.analysisResult?.clipped ? 3 : 2,
      intent: response.uiHints?.mode || "",
      userText: trimmedMessage,
      userTranscript: interactionMode === "voice" ? trimmedMessage : "",
      assistantResponse: extractAssistantResponseText(response),
      details: {
        analysisId: responseAnalysisId,
        scenarioKey: response.economicResult?.scenarioKey,
        priceEurPerTon: response.economicResult?.priceEurPerTon,
        totalValueEur: response.economicResult?.totalValueEur,
        messageLength: trimmedMessage.length,
        providerMode: response.uiHints?.providerMode,
        needsClarification: Boolean(response.uiHints?.needsClarification),
        eventSource: "frontend",
      },
    });
    if (response.uiHints?.needsClarification || response.uiHints?.mode === "unknown") {
      recordExperiment({
        eventType: "unknown_request",
        channel: interactionMode === "voice" ? "voice" : "web_chat",
        operation: "conversational_request",
        interactionMode,
        status: "needs_clarification",
        intent: response.uiHints?.mode || "unknown",
        userText: trimmedMessage,
        userTranscript: interactionMode === "voice" ? trimmedMessage : "",
        assistantResponse: extractAssistantResponseText(response),
      });
    }
  } catch (error) {
    const failureStatus =
      error?.name === "AbortError" || /timeout/i.test(error?.message || "") ? "timeout" : "failed";
    for (const [toolCallId, toolName] of activeToolCalls) {
      recordExperiment({
        eventType: "tool_failed",
        channel: interactionMode === "voice" ? "voice" : "web_chat",
        operation: toolName || "assistant_tool",
        interactionMode,
        status: failureStatus,
        error: error.message || "assistant_tool_failed",
        details: {
          toolName: toolName || "",
          toolCallId: toolCallId || "",
          eventSource: "assistant_runtime",
          taskOutcome: failureStatus,
        },
      });
    }
    appendAssistantMessage(
      "assistant",
      error.message || "Errore durante la richiesta all'assistente."
    );
    recordExperiment({
      eventType: "error",
      channel: interactionMode === "voice" ? "voice" : "web_chat",
      operation: "conversational_request",
      interactionMode,
      durationMs: elapsedSince(interactionStartedAt),
      status: failureStatus,
      error: error.message || "assistant_interaction_failed",
      userText: trimmedMessage,
      userTranscript: interactionMode === "voice" ? trimmedMessage : "",
      details: {
        analysisId: state.analysisId,
        messageLength: trimmedMessage.length,
        eventSource: "frontend",
        taskOutcome: failureStatus,
      },
    });
    showNotice(error.message || "Errore durante la richiesta all'assistente.", "error");
  } finally {
    setAssistantBusy(false);
    updateActionStates(mapController);
  }
}

async function bootstrap() {
  syncChromeOffset();
  restoreAssistantPanelWidth();
  setStudySession(appConfig.study?.currentSession || null);

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
    recordExperiment({
      eventType: "selection_changed",
      channel: "web_map",
      operation: "area_selection",
      interactionMode: "map",
      stepCount: 1,
      details: {
        selectedMunicipalityCount,
        drawnFeatureCount,
      },
    });
  };

  const mapController = new MapController({
    mapConfig: appConfig.map,
    municipalitySource,
    municipalityBoundaries,
    categoryByCode,
    onSelectionChange: (selectionState) => refreshSelectionStatus(selectionState),
  });
  state.mapController = mapController;

  renderLegend();
  renderStatusPanel();
  renderMunicipalityList(mapController, () => refreshSelectionStatus(null, mapController));
  elements.assistantTitle.textContent = assistantConfig.title || "Assistente Carta Natura";
  setAssistantStatus(null, assistantConfig.providerConfigured);
  renderAssistantMessages();
  updateActionStates(mapController);
  initializeAssistantResize(mapController);
  initializeVoiceInput(mapController);
  buildStudyConsole();
  initializeConditionControl();
  initializeUiActionLogging();
  applyConditionPolicy();
  recordExperiment({
    eventType: "session_started",
    channel: "system",
    operation: "application_session",
    interactionMode: "system",
  });

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

  elements.openHistoryButton.addEventListener("click", () => {
    toggleHistoryPanel(mapController);
  });

  elements.closeHistoryButton.addEventListener("click", () => {
    closeHistoryPanel(mapController);
  });

  elements.refreshHistoryButton.addEventListener("click", () => {
    loadAnalysisHistory().catch((error) => {
      showNotice(error.message || "Storico non caricato.", "error");
    });
  });

  elements.compareHistoryButton.addEventListener("click", () => {
    compareSelectedHistory();
  });

  elements.clearHistoryButton.addEventListener("click", () => {
    clearHistory();
  });

  elements.analysisHistoryPanel.addEventListener("change", (event) => {
    const checkbox = event.target.closest("[data-history-select]");
    if (!checkbox) {
      return;
    }
    const analysisId = checkbox.dataset.historySelect;
    if (checkbox.checked) {
      state.analysisHistory.selectedIds.add(analysisId);
    } else {
      state.analysisHistory.selectedIds.delete(analysisId);
    }
    state.analysisHistory.comparison = null;
    state.analysisHistory.confirmClear = false;
    renderHistoryPanel();
  });

  elements.analysisHistoryPanel.addEventListener("click", (event) => {
    const renameButton = event.target.closest("[data-history-rename]");
    const renameSaveButton = event.target.closest("[data-history-rename-save]");
    const renameCancelButton = event.target.closest("[data-history-rename-cancel]");
    const deleteButton = event.target.closest("[data-history-delete]");
    const deleteConfirmButton = event.target.closest("[data-history-delete-confirm]");
    const deleteCancelButton = event.target.closest("[data-history-delete-cancel]");
    if (renameButton) {
      renameHistoryItem(renameButton.dataset.historyRename);
      return;
    }
    if (renameSaveButton) {
      saveHistoryRename(renameSaveButton.dataset.historyRenameSave);
      return;
    }
    if (renameCancelButton) {
      cancelHistoryRename(renameCancelButton.dataset.historyRenameCancel);
      return;
    }
    if (deleteButton) {
      deleteHistoryItem(deleteButton.dataset.historyDelete);
      return;
    }
    if (deleteConfirmButton) {
      confirmDeleteHistoryItem(deleteConfirmButton.dataset.historyDeleteConfirm);
      return;
    }
    if (deleteCancelButton) {
      cancelDeleteHistoryItem(deleteCancelButton.dataset.historyDeleteCancel);
    }
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

    elements.assistantMessages.addEventListener("click", (event) => {
      const suggestion = event.target.closest("[data-assistant-prompt]");
      if (!suggestion) {
        return;
      }

      const prompt = suggestion.dataset.assistantPrompt || "";
      elements.assistantInput.value = prompt;
      runAssistantInteraction(mapController, prompt);
    });
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

    if (elements.analysisHistoryPanel.classList.contains("is-open")) {
      closeHistoryPanel(mapController);
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
