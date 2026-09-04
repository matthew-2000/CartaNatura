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
let resolveFeatureCategory;
let priceOptions;
let MapController;
let generatePdfReport;
let renderAnalysisHistoryList;
let renderAnalysisComparison;
let createWorkspaceUi;
let workspaceUi;
let experimentLogQueue = Promise.resolve();

const MediaRecorderApi = window.MediaRecorder || null;
const ALLOWED_ASSISTANT_UI_ACTIONS = new Set([
  "show_last_analysis",
  "open_report_panel",
  "show_legend",
  "focus_map_results",
]);
const TOOL_OPERATIONAL_VIEWS = new Map([
  ["analyze_municipalities", "report"],
  ["analyze_current_selection", "report"],
  ["calculate_economic_value", "report"],
  ["compare_economic_scenarios", "report"],
  ["get_last_analysis", "report"],
  ["prepare_report", "report"],
  ["compare_analyses", "comparison"],
  ["compare_recent_analyses", "comparison"],
  ["compare_saved_analyses", "comparison"],
  ["list_recent_analyses", "history"],
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
    workspaceUiModule,
  ] =
    await Promise.all([
      import(versionedPath("./modules/api.js")),
      import(versionedPath("./modules/analysis.js")),
      import(versionedPath("./modules/config.js")),
      import(versionedPath("./modules/map-controller.js")),
      import(versionedPath("./modules/pdf-export.js")),
      import(versionedPath("./modules/analysis-history.js")),
      import(versionedPath("./modules/workspace-ui.js")),
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
  ({ appConfig, assistantConfig, categories, resolveFeatureCategory, priceOptions } = configModule);
  ({ MapController } = mapControllerModule);
  ({ generatePdfReport } = pdfExportModule);
  ({ renderAnalysisHistoryList, renderAnalysisComparison } = analysisHistoryModule);
  ({ createWorkspaceUi } = workspaceUiModule);
}

const state = {
  analysisId: null,
  analysisCreatedAt: null,
  summary: null,
  clipped: null,
  intersectedMunicipalities: [],
  calculatedValue: 0,
  economicValueCalculated: false,
  selectedEconomicPrice: null,
  analysisContext: null,
  mapFilter: null,
  categorySort: "hectares",
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
  workspaceResizeHandle: document.getElementById("workspaceResizeHandle"),
  collapseWorkspaceButton: document.getElementById("collapseWorkspacePanel"),
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
  selectionMunicipalityCount: document.getElementById("selectionMunicipalityCount"),
  selectionGeometryCount: document.getElementById("selectionGeometryCount"),
  selectionRunAnalysis: document.getElementById("selectionRunAnalysis"),
  statusContent: document.getElementById("statusContent"),
  legendContent: document.getElementById("legendContent"),
  statusPanel: document.getElementById("mapStatusPanel"),
  legendPanel: document.getElementById("legendPanel"),
  toggleLegendPanelButton: document.getElementById("toggleLegendPanel"),
  map: document.getElementById("map"),
};

function syncChromeOffset() {
  workspaceUi.syncChromeOffset();
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatAnalysisDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Data non disponibile";
  }
  return date.toLocaleString("it-IT", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatReadableAnalysisId(value) {
  const clean = String(value || "").replace(/^analysis[_-]?/i, "").replaceAll(/[^a-z0-9]/gi, "");
  return clean ? `AN-${clean.slice(0, 6).toUpperCase()}` : "AN—";
}

function getAnalysisTerritoryLabel() {
  if (state.intersectedMunicipalities.length === 1) {
    return state.intersectedMunicipalities[0];
  }
  if (state.intersectedMunicipalities.length > 1) {
    const visible = state.intersectedMunicipalities.slice(0, 2).join(", ");
    const remainder = state.intersectedMunicipalities.length - 2;
    return remainder > 0 ? `${visible} +${remainder}` : visible;
  }
  if (state.analysisContext?.drawnFeatureCount) {
    return "Area disegnata in Campania";
  }
  return "Territorio analizzato";
}

function getAnalysisSelectionLabel() {
  const municipalities = state.analysisContext?.selectedMunicipalityCount || 0;
  const geometries = state.analysisContext?.drawnFeatureCount || 0;
  if (municipalities && geometries) {
    return `${municipalities} comuni + ${geometries} geometrie`;
  }
  if (municipalities) {
    return `${municipalities} ${municipalities === 1 ? "comune selezionato" : "comuni selezionati"}`;
  }
  if (geometries) {
    return `${geometries} ${geometries === 1 ? "geometria disegnata" : "geometrie disegnate"}`;
  }
  return `${state.intersectedMunicipalities.length} comuni interessati`;
}

function setBusy(mapController, busy) {
  elements.loadingOverlay.classList.toggle("visible", busy);
  elements.loadingOverlay.setAttribute("aria-hidden", String(!busy));
  elements.selectMunicipalityButton.disabled = busy;
  elements.runAnalysisButton.disabled = busy;
  elements.infoButton.disabled = busy;
  elements.openHistoryButton.disabled = busy;
  elements.appInfoButton.disabled = busy;
  const runAnalysisLabel = elements.runAnalysisButton.querySelector(".workflow-label");
  if (runAnalysisLabel) {
    runAnalysisLabel.textContent = busy ? "Analisi…" : "Analizza";
  }
  mapController.setInteractionDisabled(busy);
}

function restoreAssistantPanelWidth() {
  workspaceUi.restoreAssistantPanelWidth();
}

function getActivePanelName() {
  return workspaceUi.getActivePanelName();
}

function syncSidePanelLayout(mapController = null) {
  workspaceUi.syncLayout(mapController);
}

function initializeAssistantResize(mapController) {
  workspaceUi.initializeResize(mapController);
}

function expandOperationalPanel() {
  document.body.classList.remove("operational-panel-collapsed");
  elements.collapseWorkspaceButton?.setAttribute("aria-expanded", "true");
}

function toggleOperationalPanel(mapController = null) {
  const collapsed = document.body.classList.toggle("operational-panel-collapsed");
  elements.collapseWorkspaceButton?.setAttribute("aria-expanded", String(!collapsed));
  syncSidePanelLayout(mapController);
}

function openPopup(mapController, { source = "ui" } = {}) {
  expandOperationalPanel();
  closeMunicipalityPanel();
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
  closeAppInfo();
  elements.assistantPanel.classList.add("is-open");
  elements.assistantPanel.setAttribute("aria-hidden", "false");
  document.body.classList.add("assistant-panel-open");
  elements.openAssistantButton?.setAttribute("aria-expanded", "true");
  restoreAssistantPanelWidth();
  syncSidePanelLayout(mapController);
}

function closeAssistantPanel(mapController = null, { force = false } = {}) {
  if (!force && getActiveStudyCondition() === "conversational") return;
  elements.assistantPanel.classList.remove("is-open");
  elements.assistantPanel.setAttribute("aria-hidden", "true");
  document.body.classList.remove("assistant-panel-open");
  elements.openAssistantButton?.setAttribute("aria-expanded", "false");
  syncSidePanelLayout(mapController);
}

function openHistoryPanel(mapController = null) {
  expandOperationalPanel();
  closeMunicipalityPanel();
  closePopup();
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
  if (shouldOpen) expandOperationalPanel();
  closePopup();
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

function openSelectionPanel(mapController = null) {
  expandOperationalPanel();
  closePopup();
  closeHistoryPanel();
  closeAppInfo();
  elements.municipalityPanel.classList.add("visualizzaListaComuni");
  elements.selectMunicipalityButton?.setAttribute("aria-expanded", "true");
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
    busy: state.analysisHistory.busy,
  });
  elements.analysisHistoryComparison.innerHTML = renderAnalysisComparison(
    state.analysisHistory.comparison
  );
  elements.analysisHistoryPanel.classList.toggle(
    "is-comparing",
    Boolean(state.analysisHistory.comparison)
  );
  elements.compareHistoryButton.disabled =
    state.analysisHistory.busy || selectedIds.size < 2;
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
  const label = toggle.querySelector(".study-console-toggle-label");
  const badge = toggle.querySelector(".study-console-toggle-badge");
  if (label) {
    label.textContent = "Studio";
  }
  if (badge) {
    badge.textContent = condition ? condition.toUpperCase() : "";
    badge.hidden = !condition;
  }
  toggle.title = condition
    ? `Controllo sperimentale · ${condition}`
    : "Apri controllo sperimentale";
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
    closeAssistantPanel(state.mapController, { force: true });
  }

  elements.selectMunicipalityButton.disabled = conversationalActive;
  elements.openHistoryButton.disabled = conversationalActive;
  if (conversationalActive) {
    closeMunicipalityPanel(state.mapController);
    closeHistoryPanel(state.mapController);
    openAssistantPanel(state.mapController);
  }

  const hasInputs =
    state.mapController?.hasSelectedMunicipalities() || state.mapController?.hasDrawnAreas();
  elements.runAnalysisButton.disabled = conversationalActive || !hasInputs;

  const economicControls = elements.infoContainer?.querySelectorAll(
    "#testoValore, #butcalcolavalore, .analysis-filter-control"
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
      control.closest(".analysis-filter-control"))
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
    <button type="button" class="utility-action study-console-toggle" aria-expanded="false" aria-haspopup="dialog" aria-controls="studyConsoleBody" title="Apri controllo sperimentale">
      <svg aria-hidden="true" viewBox="0 0 24 24"><path d="M9 5h6M9 3h6a1 1 0 0 1 1 1v2H8V4a1 1 0 0 1 1-1Z"/><path d="M7 5H5.75A1.75 1.75 0 0 0 4 6.75v12.5C4 20.22 4.78 21 5.75 21h12.5c.97 0 1.75-.78 1.75-1.75V6.75C20 5.78 19.22 5 18.25 5H17"/><path d="M8 11h8M8 15h5"/></svg>
      <span class="study-console-toggle-label">Studio</span>
      <span class="study-console-toggle-badge" hidden></span>
    </button>
    <div id="studyConsoleBody" class="study-console-body" role="dialog" aria-label="Console operatore" aria-hidden="true">
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
        <button type="button" class="study-action is-primary" data-study-action="start-session">Avvia sessione</button>
        <button type="button" class="study-action" data-study-action="start-task">Inizia attività</button>
        <button type="button" class="study-action" data-study-action="complete-task">Completa</button>
        <button type="button" class="study-action" data-study-action="mark-error">Errore</button>
        <button type="button" class="study-action" data-study-action="mark-unknown">Non compresa</button>
        <button type="button" class="study-action" data-study-action="export-json">Esporta JSON</button>
        <button type="button" class="study-action" data-study-action="export-jsonl">Esporta JSONL</button>
        <a class="study-action study-admin-link" href="${escapeHtml(appConfig.study.adminUrl)}">Archivio sessioni</a>
        <button type="button" class="study-action is-danger" data-study-action="reset-session">Chiudi sessione</button>
      </div>
    </div>
  `;
  const headerTarget = elements.navbar?.querySelector(".utility-nav") || elements.navbar;
  (headerTarget || document.body).appendChild(panel);
  state.study.panel = panel;

  panel.querySelector(".study-console-toggle").addEventListener("click", () => {
    const collapsed = !panel.classList.contains("is-collapsed");
    panel.classList.toggle("is-collapsed", collapsed);
    panel.querySelector(".study-console-toggle").setAttribute("aria-expanded", String(!collapsed));
    panel.querySelector(".study-console-body").setAttribute("aria-hidden", String(collapsed));
  });

  panel.addEventListener("click", (event) => {
    event.stopPropagation();
    const action = event.target.closest("[data-study-action]")?.dataset.studyAction;
    if (!action) {
      return;
    }
    handleStudyAction(action);
  });

  document.addEventListener("click", (event) => {
    if (!panel.classList.contains("is-collapsed") && !panel.contains(event.target)) {
      panel.classList.add("is-collapsed");
      panel.querySelector(".study-console-toggle").setAttribute("aria-expanded", "false");
      panel.querySelector(".study-console-body").setAttribute("aria-hidden", "true");
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !panel.classList.contains("is-collapsed")) {
      panel.classList.add("is-collapsed");
      panel.querySelector(".study-console-toggle").setAttribute("aria-expanded", "false");
      panel.querySelector(".study-console-body").setAttribute("aria-hidden", "true");
      panel.querySelector(".study-console-toggle").focus();
    }
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
    syncStudyControls();
    updateStudyConditionIndicator();
    return;
  }
  status.textContent = message || (state.study.activeTask
    ? `${state.study.activeTask.taskId} · ${session.condition}`
    : `${session.participantId} · pronta`);
  status.classList.add("is-active");
  syncStudyControls();
  updateStudyConditionIndicator();
}

function syncStudyControls() {
  const panel = state.study.panel;
  if (!panel) {
    return;
  }
  const hasSession = Boolean(getStudySession());
  const hasActiveTask = Boolean(state.study.activeTask);
  panel.querySelector('[data-study-action="start-session"]').disabled = hasSession;
  panel.querySelector('[data-study-action="start-task"]').disabled = !hasSession || hasActiveTask;
  panel.querySelector('[data-study-action="complete-task"]').disabled = !hasActiveTask;
  panel.querySelector('[data-study-action="mark-error"]').disabled = !hasActiveTask;
  panel.querySelector('[data-study-action="mark-unknown"]').disabled = !hasActiveTask;
  panel.querySelector('[data-study-action="export-json"]').disabled = !hasSession;
  panel.querySelector('[data-study-action="export-jsonl"]').disabled = !hasSession;
  panel.querySelector('[data-study-action="reset-session"]').disabled = !hasSession;
  panel.querySelector("#studyParticipantId").disabled = hasSession;
  panel.querySelector("#studyCondition").disabled = hasSession;
  panel.querySelector("#studyTaskId").disabled = hasActiveTask;
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
      await markUnknownStudyTask();
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
  renderStudyStatus(
    status === "completed"
      ? "Attività completata"
      : extra.error === "manual_unknown_request"
        ? "Attività non compresa"
        : "Attività terminata con errore"
  );
}

async function markUnknownStudyTask() {
  if (!state.study.activeTask) {
    throw new Error("Nessuna attività in corso.");
  }
  await recordExperiment({
    eventType: "unknown_request",
    channel: "system",
    operation: "manual_mark",
    interactionMode: "system",
    taskId: state.study.activeTask.taskId,
    taskRunId: state.study.activeTask.taskRunId,
    status: "marked",
    error: "manual_unknown_request",
    stepCount: 1,
  });
  await finishStudyTask("task_failed", "failed", { error: "manual_unknown_request" });
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
  link.addEventListener("click", (event) => event.stopPropagation());
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

function voiceRecordingErrorMessage(error) {
  const errorName = String(error?.name || "");
  const errorMessage = String(error?.message || "");
  if (errorName === "NotAllowedError" || /permission|autorizz/i.test(errorMessage)) {
    return "Consenti l'accesso al microfono nel browser e riprova.";
  }
  if (errorName === "NotFoundError") {
    return "Nessun microfono disponibile.";
  }
  return "Input vocale non acquisito. Riprova o usa il testo.";
}

async function requestMicrophoneStream() {
  setVoiceStatus("In attesa dell'accesso al microfono...", "info");
  let timedOut = false;
  let timeoutId = null;
  const mediaRequest = navigator.mediaDevices.getUserMedia({ audio: true });
  mediaRequest.then((stream) => {
    if (timedOut) {
      stream.getTracks().forEach((track) => track.stop());
    }
  });
  const permissionTimeout = new Promise((resolve, reject) => {
    timeoutId = window.setTimeout(() => {
      timedOut = true;
      const error = new Error("Autorizzazione microfono non ricevuta.");
      error.name = "NotAllowedError";
      reject(error);
    }, 10000);
  });

  try {
    return await Promise.race([mediaRequest, permissionTimeout]);
  } finally {
    if (timeoutId) {
      window.clearTimeout(timeoutId);
    }
  }
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
      setVoiceStatus(voiceRecordingErrorMessage(error), "warning");
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
    audioStream = await requestMicrophoneStream();
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

function appendAssistantMessage(role, text, options = {}) {
  if (!text) {
    return -1;
  }

  state.assistantMessages.push({ role, text, ...options });
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

function routeStructuredAssistantResult(mapController, response, completedTools = new Set()) {
  if (response?.mapFilter) {
    applyAssistantMapFilter(mapController, response.mapFilter);
    return;
  }

  const comparison = response?.analysisResult;
  if (Array.isArray(comparison?.analyses)) {
    state.analysisHistory.comparison = comparison;
    renderHistoryPanel();
    openHistoryPanel(mapController);
    return;
  }

  if (
    response?.analysisResult?.clipped ||
    response?.economicResult ||
    response?.scenarioComparison ||
    response?.reportContext
  ) {
    renderInfoSummary();
    openPopup(mapController, { source: "assistant" });
    return;
  }

  if ([...completedTools].some((toolName) => TOOL_OPERATIONAL_VIEWS.get(toolName) === "history")) {
    openHistoryPanel(mapController);
  }
}

function extractAssistantResponseText(response) {
  const assistantMessage = (response.messages || []).find((message) => message.role === "assistant");
  return assistantMessage?.text || "";
}

function describeAssistantToolProgress(toolName, stage = "running") {
  const labels = {
    search_municipalities: "verifica dei comuni indicati",
    analyze_municipalities: "analisi GIS dei comuni",
    analyze_current_selection: "analisi GIS della selezione",
    calculate_economic_value: "calcolo del valore economico",
    compare_economic_scenarios: "confronto degli scenari economici",
    prepare_report: "preparazione del report esistente",
    get_last_analysis: "recupero dell'ultimo report",
    compare_recent_analyses: "confronto degli ultimi report",
    get_methodology: "recupero della metodologia",
    filter_last_analysis_categories: "filtro delle categorie sulla mappa",
    reset_analysis_context: "azzeramento della sessione",
  };
  const label = labels[toolName] || "strumento richiesto";

  if (stage === "pending") {
    return `L'assistente ha scelto lo strumento: ${label}...`;
  }

  if (stage === "completed") {
    return `Completato: ${label}.`;
  }

  return `Eseguo ${label}...`;
}

function renderAssistantMessages() {
  elements.assistantMessages.innerHTML = state.assistantMessages
    .map(
      (message) => `
        <article class="assistant-message assistant-message-${message.role}${message.streaming ? " is-streaming" : ""}${message.error ? " is-error" : ""}"${message.streaming ? ' aria-busy="true"' : ""}>
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
  if (!followUps.length) {
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
  return `
    <div class="assistant-message-hints">
      ${followUpButtons}
    </div>
  `;
}

function buildInteractionContext(mapController) {
  return {
    selectedMunicipalities: mapController.getSelectedMunicipalityNames(),
    mapExtent: mapController.getMapExtent(),
    selectionPayload: buildAnalysisPayload(mapController),
    displayedAnalysisId: state.analysisId,
  };
}

function applyAnalysisResult(mapController, analysisResult, analysisContext = null) {
  state.analysisId = analysisResult.analysisId || null;
  state.analysisCreatedAt = analysisResult.createdAt || new Date().toISOString();
  state.clipped = analysisResult.clipped;
  state.intersectedMunicipalities = analysisResult.intersectedMunicipalities || [];
  state.summary =
    analysisResult.summary ||
    summarizeClippedFeatures(analysisResult.clipped, categories, resolveFeatureCategory);
  state.calculatedValue = 0;
  state.economicValueCalculated = false;
  state.selectedEconomicPrice = priceOptions[0]?.value ?? null;
  state.mapFilter = null;
  state.categorySort = "hectares";
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

function applyAssistantMapFilter(mapController, mapFilter) {
  if (!state.clipped || !mapFilter || mapFilter.analysisId !== state.analysisId) {
    return false;
  }

  const selectedKeys = new Set(
    (mapFilter.categories || []).map((item) => String(item?.key || "")).filter(Boolean)
  );
  const sourceFeatures = Array.isArray(state.clipped.features) ? state.clipped.features : [];
  const filteredFeatures = mapFilter.showAll
    ? sourceFeatures
    : sourceFeatures.filter((feature) => {
        const category = resolveFeatureCategory(feature);
        return category && selectedKeys.has(category.key);
      });

  mapController.renderNature({ ...state.clipped, features: filteredFeatures });
  mapController.renderIntersectedMunicipalities(state.intersectedMunicipalities);
  state.mapFilter = mapFilter.showAll ? null : mapFilter;
  renderInfoSummary();
  closePopup(mapController);
  closeHistoryPanel(mapController);
  closeMunicipalityPanel(mapController);
  mapController.syncLayout();
  return true;
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
  const intersectedMunicipalityCount = state.intersectedMunicipalities.length;
  const resultText = state.summary?.hasSupportedVegetation
    ? `${intersectedMunicipalityCount} ${intersectedMunicipalityCount === 1 ? "comune" : "comuni"}, ${formatRoundedNumber(
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

function renderScenarioComparisonList(selectedPrice) {
  const rows = buildEconomicScenarioRows(state.summary, priceOptions, selectedPrice);
  if (!rows.length) {
    return "";
  }

  return `
    <details class="analysis-disclosure scenario-comparison-card">
      <summary>
        <span><strong>Confronta gli scenari</strong><small>${rows.length} prezzi su ${formatRoundedNumber(state.summary?.totalCo2 || 0)} tCO₂/anno</small></span>
        <span class="disclosure-action">Dettagli</span>
      </summary>
      <div class="scenario-list">
        ${rows
          .map(
            (row) => `
              <article class="scenario-row${row.selected ? " is-selected" : ""}">
                <div>
                  <strong>${escapeHtml(row.label)}</strong>
                  <small>${formatRoundedNumber(row.price)} €/tCO₂${row.description ? ` · ${escapeHtml(row.description)}` : ""}</small>
                </div>
                <div>
                  <strong>${formatCurrency(row.value)}</strong>
                  <small>${row.selected ? "Scenario applicato" : "Valore annuo"}</small>
                </div>
              </article>
            `
          )
          .join("")}
      </div>
    </details>
  `;
}

function updateScenarioComparison(selectedPrice) {
  const comparisonRoot = document.getElementById("scenarioComparison");
  if (!comparisonRoot || !state.summary) {
    return;
  }
  comparisonRoot.innerHTML = renderScenarioComparisonList(selectedPrice);
}

function renderCategoryBreakdown() {
  const items = [...(state.summary?.items || [])];
  if (state.categorySort === "label") {
    items.sort((left, right) => left.label.localeCompare(right.label, "it"));
  } else if (state.categorySort === "co2") {
    items.sort(
      (left, right) =>
        right.hectares * right.co2PerHectare - left.hectares * left.co2PerHectare
    );
  } else {
    items.sort((left, right) => right.hectares - left.hectares);
  }
  const maxHectares = Math.max(...items.map((item) => item.hectares), 1);

  return items
    .map((item) => {
      const categoryCo2 = item.hectares * item.co2PerHectare;
      return `
        <article class="analysis-category-row">
          <div class="analysis-category-heading">
            <span class="analysis-category-swatch" style="--category-color:${item.color}" aria-hidden="true"></span>
            <strong>${escapeHtml(item.label)}</strong>
            <span>${formatRoundedNumber(item.hectares)} ha</span>
          </div>
          <div class="analysis-category-track" aria-hidden="true"><span style="width:${Math.max((item.hectares / maxHectares) * 100, 4)}%; --category-color:${item.color}"></span></div>
          <div class="analysis-category-meta">
            <span>${formatRoundedNumber(item.co2PerHectare)} tCO₂/ha</span>
            <span>${formatRoundedNumber(categoryCo2)} tCO₂/anno</span>
          </div>
        </article>
      `;
    })
    .join("");
}

function renderAnalysisScopeState() {
  if (!state.mapFilter) {
    return `
      <div class="analysis-scope-strip">
        <span><small>Dati del report</small><strong>Analisi completa</strong></span>
        <span><small>Visualizzazione mappa</small><strong>Tutte le categorie</strong></span>
      </div>
    `;
  }
  const filterLabels = (state.mapFilter.categories || []).map((item) => item.label).filter(Boolean);
  const filterText = filterLabels.length ? filterLabels.join(", ") : "Categorie selezionate";
  const disabled = getActiveStudyCondition() === "conversational" ? "disabled" : "";
  return `
    <div class="analysis-scope-strip is-filtered">
      <span><small>Dati del report</small><strong>Analisi completa</strong></span>
      <span><small>Filtro solo mappa</small><strong title="${escapeHtml(filterText)}">${escapeHtml(filterText)}</strong></span>
      <button id="restoreAnalysisMap" class="analysis-filter-control" type="button" ${disabled}>Mostra tutte</button>
    </div>
    <p class="analysis-scope-note">I KPI e gli scenari restano riferiti all’analisi completa; il filtro modifica solo ciò che è visibile in mappa.</p>
  `;
}

function renderInfoSummary() {
  if (!state.summary) {
    elements.infoContainer.innerHTML = `
      <div class="analysis-empty-state">
        <span class="analysis-empty-symbol" aria-hidden="true">↗</span>
        <h3>Nessun report disponibile</h3>
        <p>Seleziona uno o più comuni, oppure disegna un'area sulla mappa, poi avvia l'analisi.</p>
      </div>
    `;
    return;
  }

  if (!state.summary.hasSupportedVegetation) {
    elements.infoContainer.innerHTML = `
      <div class="analysis-empty-state">
        <span class="analysis-empty-symbol" aria-hidden="true">—</span>
        <h3>Nessuna categoria forestale supportata</h3>
        <p>L'area analizzata non contiene categorie forestali supportate dal modello corrente.</p>
      </div>
    `;
    return;
  }

  const derivedMetrics = deriveSummaryMetrics(state.summary);
  const selectedPrice = state.selectedEconomicPrice ?? priceOptions[0]?.value;
  const selectedScenario = priceOptions.find((option) => Number(option.value) === Number(selectedPrice));
  const territoryTitle = getAnalysisTerritoryLabel();
  const municipalityTitle = state.intersectedMunicipalities.length
    ? state.intersectedMunicipalities.join(", ")
    : territoryTitle;

  elements.infoContainer.innerHTML = `
    <div class="summary-section analysis-summary">
      <header class="analysis-report-intro">
        <div>
          <span class="analysis-panel-kicker">Analisi territoriale</span>
          <h3 title="${escapeHtml(municipalityTitle)}">${escapeHtml(territoryTitle)}</h3>
          <p>${escapeHtml(getAnalysisSelectionLabel())}</p>
        </div>
        <span class="analysis-save-state"><span aria-hidden="true">✓</span> Salvata</span>
      </header>

      <div class="analysis-meta-line">
        <span title="${escapeHtml(state.analysisId || "")}">${escapeHtml(formatReadableAnalysisId(state.analysisId))}</span>
        <span>${escapeHtml(formatAnalysisDate(state.analysisCreatedAt))}</span>
      </div>

      ${renderAnalysisScopeState()}

      <section class="analysis-kpi-block" aria-label="Indicatori principali">
        <div class="analysis-kpi-featured">
          <article>
            <span>CO₂ sequestrata</span>
            <strong>${formatRoundedNumber(state.summary.totalCo2)}</strong>
            <small>tCO₂ / anno</small>
          </article>
          <article>
            <span>Superficie</span>
            <strong>${formatRoundedNumber(derivedMetrics.totalHectares)}</strong>
            <small>ettari analizzati</small>
          </article>
        </div>
        <div class="analysis-fact-row">
          <span><small>Categorie forestali</small><strong>${state.summary.items.length}</strong></span>
          <span><small>Prevalente</small><strong>${escapeHtml(derivedMetrics.topCategory?.label || "-")}</strong></span>
        </div>
      </section>

      <section class="analysis-valuation-card">
        <div class="analysis-section-header">
          <div><span class="analysis-panel-kicker">Scenario economico</span><h4>Valorizzazione annuale</h4></div>
          <span class="analysis-section-meta">${formatRoundedNumber(state.summary.totalCo2)} tCO₂/anno</span>
        </div>
        <div class="analysis-value-overview">
          <div>
            <small>Valore economico</small>
            <strong id="analysisEconomicValue">${state.economicValueCalculated ? formatCurrency(state.calculatedValue) : "Da calcolare"}</strong>
          </div>
          <div>
            <small>Scenario applicato</small>
            <strong id="analysisScenarioLabel">${escapeHtml(selectedScenario?.label || "Scenario")}</strong>
            <span id="analysisScenarioPrice">${formatRoundedNumber(selectedPrice)} €/tCO₂</span>
          </div>
        </div>
        <div class="value-row">
          <label for="testoValore"><span>Prezzo del carbonio</span><select id="testoValore">${renderPriceOptions()}</select></label>
          <button id="butcalcolavalore" type="button">Calcola valore</button>
        </div>
        <div id="valoreTotaleCalcolato" class="value-result"></div>
        <div id="scenarioComparison" class="scenario-comparison-root">
          ${renderScenarioComparisonList(selectedPrice)}
        </div>
      </section>

      <details class="analysis-disclosure analysis-category-section">
        <summary>
          <span><strong>Categorie forestali</strong><small>${state.summary.items.length} categorie · ${formatRoundedNumber(derivedMetrics.totalHectares)} ha</small></span>
          <span class="disclosure-action">Espandi</span>
        </summary>
        <div class="analysis-category-toolbar">
          <label for="analysisCategorySort">Ordina per</label>
          <select id="analysisCategorySort">
            <option value="hectares">Superficie</option>
            <option value="co2">CO₂ annua</option>
            <option value="label">Nome</option>
          </select>
        </div>
        <div id="analysisCategoryList" class="analysis-category-list">${renderCategoryBreakdown()}</div>
      </details>

      <footer class="analysis-report-actions">
        <div>
          <strong>Analisi disponibile nello storico</strong>
          <small>Puoi rinominarla o selezionarla per un confronto.</small>
        </div>
        <button id="focusAnalysisMap" type="button">
          <svg aria-hidden="true" viewBox="0 0 24 24"><path d="m4 6 5-2 6 2 5-2v14l-5 2-6-2-5 2Z"/><path d="M9 4v14M15 6v14"/></svg>
          Vedi mappa
        </button>
      </footer>
    </div>
  `;

  const priceSelect = document.getElementById("testoValore");
  const calculateButton = document.getElementById("butcalcolavalore");
  const categorySort = document.getElementById("analysisCategorySort");
  const focusMapButton = document.getElementById("focusAnalysisMap");
  const restoreMapButton = document.getElementById("restoreAnalysisMap");
  const updateEconomicOverview = (value) => {
    const scenario = priceOptions.find((option) => Number(option.value) === Number(value));
    document.getElementById("analysisScenarioLabel").textContent = scenario?.label || "Scenario";
    document.getElementById("analysisScenarioPrice").textContent = `${formatRoundedNumber(value)} €/tCO₂`;
    document.getElementById("analysisEconomicValue").textContent = state.economicValueCalculated
      ? formatCurrency(state.calculatedValue)
      : "Da calcolare";
  };
  priceSelect.value = String(state.selectedEconomicPrice ?? priceOptions[0]?.value ?? "");
  categorySort.value = state.categorySort;
  categorySort.addEventListener("change", () => {
    state.categorySort = categorySort.value;
    document.getElementById("analysisCategoryList").innerHTML = renderCategoryBreakdown();
  });
  focusMapButton.addEventListener("click", () => {
    closePopup(state.mapController);
    state.mapController?.syncLayout();
  });
  restoreMapButton?.addEventListener("click", () => {
    if (getActiveStudyCondition() === "conversational" || !state.clipped) {
      return;
    }
    state.mapController.renderNature(state.clipped);
    state.mapController.renderIntersectedMunicipalities(state.intersectedMunicipalities);
    state.mapFilter = null;
    renderInfoSummary();
    showNotice("Mappa ripristinata con tutte le categorie.", "success");
  });
  priceSelect.addEventListener("change", () => {
    if (getActiveStudyCondition() === "conversational") {
      applyConditionPolicy();
      return;
    }
    const selectedValue = Number(priceSelect.value || 0);
    state.selectedEconomicPrice = selectedValue;
    updateScenarioComparison(selectedValue);
    updateEconomicOverview(selectedValue);
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
    updateEconomicOverview(selectedValue);
    resultRoot.innerHTML = `
      <div class="analysis-value-total">
        <span><small>Valore annuo calcolato</small><strong>${formatCurrency(state.calculatedValue)}</strong></span>
        <span><small>Scenario</small><strong>${escapeHtml(priceOptions.find((option) => Number(option.value) === Number(selectedValue))?.label || "-")}</strong></span>
      </div>
      <div class="analysis-value-actions">
        <button id="butstampadettagli" type="button">
          <svg aria-hidden="true" viewBox="0 0 24 24"><path d="M7 3h7l4 4v14H7Z"/><path d="M14 3v5h5M9.5 13h5M9.5 16h5"/></svg>
          Genera PDF
        </button>
      </div>
    `;

    document.getElementById("butstampadettagli").addEventListener("click", async () => {
      const reportStartedAt = performance.now();
      const printButton = document.getElementById("butstampadettagli");
      const closeButton = elements.closePopupButton;
      calculateButtonRef.disabled = true;
      printButton.disabled = true;
      closeButton.disabled = true;
      resultRoot.setAttribute("aria-busy", "true");
      resultRoot.querySelectorAll(".pdf-ready, .pdf-status").forEach((element) => element.remove());
      resultRoot.insertAdjacentHTML(
        "beforeend",
        `<div class="pdf-status" role="status" aria-live="polite"><strong>Generazione PDF in corso…</strong><span>La mappa e i dati vengono impaginati.</span></div>`
      );

      try {
        const generatedPdf = await generatePdfReport({
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
        if (generatedPdf?.objectUrl) {
          resultRoot.insertAdjacentHTML(
            "beforeend",
            `<div class="pdf-ready">
              <span><strong>Report pronto</strong><small>4 pagine · PDF A4</small></span>
              <span class="pdf-ready-actions">
                <a class="pdf-download" href="${escapeHtml(generatedPdf.objectUrl)}" download="${escapeHtml(generatedPdf.filename || "carta-natura-report.pdf")}">Scarica PDF</a>
                <a class="pdf-preview" href="${escapeHtml(generatedPdf.objectUrl)}" target="_blank" rel="noopener">Anteprima</a>
              </span>
            </div>`
          );
          printButton.closest(".analysis-value-actions")?.setAttribute("hidden", "");
        }
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
        resultRoot.insertAdjacentHTML(
          "beforeend",
          `<div class="pdf-status is-error" role="alert"><strong>PDF non generato.</strong><span>${escapeHtml(error.message || "Riprova tra qualche istante.")}</span></div>`
        );
        showNotice(error.message || "Errore nella generazione del PDF.", "error");
      } finally {
        calculateButtonRef.disabled = false;
        printButton.disabled = false;
        closeButton.disabled = false;
        resultRoot.setAttribute("aria-busy", "false");
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
  state.analysisCreatedAt = null;
  state.summary = null;
  state.clipped = null;
  state.intersectedMunicipalities = [];
  state.calculatedValue = 0;
  state.economicValueCalculated = false;
  state.selectedEconomicPrice = null;
  state.analysisContext = null;
  state.mapFilter = null;
  state.categorySort = "hectares";
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
  const completedTools = new Set();

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
              setAssistantStreamingProgress(
                streamingMessageIndex,
                event.message || "Richiesta ricevuta..."
              );
            } else if (event.stage === "model_created") {
              setAssistantStreamingProgress(
                streamingMessageIndex,
                event.message || "L'assistente sta elaborando la richiesta..."
              );
            } else if (event.stage === "synthesizing_response") {
              setAssistantStreamingProgress(
                streamingMessageIndex,
                event.message || "Preparo la risposta finale..."
              );
            }
          },
          onToolPending: (event) => {
            setAssistantStreamingProgress(
              streamingMessageIndex,
              describeAssistantToolProgress(event.toolName, "pending")
            );
          },
          onToolStart: (event) => {
            setAssistantStreamingProgress(
              streamingMessageIndex,
              describeAssistantToolProgress(event.toolName, "running")
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
            completedTools.add(event.toolName);
            setAssistantStreamingProgress(
              streamingMessageIndex,
              describeAssistantToolProgress(event.toolName, "completed")
            );
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
              renderInfoSummary();
              openPopup(mapController, { source: "assistant" });
            } else if (Array.isArray(event.analysisResult?.analyses)) {
              state.analysisHistory.comparison = event.analysisResult;
              renderHistoryPanel();
              openHistoryPanel(mapController);
            }
            setAssistantStreamingProgress(
              streamingMessageIndex,
              "Risultato disponibile. L'assistente continua l'elaborazione..."
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

    // Apply the area before its valuation or filter, including non-streamed
    // compound requests. Reapplying it afterwards would erase those results.
    if (!analysisApplied && response.analysisResult?.clipped) {
      applyAnalysisResult(mapController, response.analysisResult);
      analysisApplied = true;
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
    routeStructuredAssistantResult(mapController, response, completedTools);

    if (["reset", "reset_session"].includes(response.uiHints?.mode)) {
      resetAnalysis(mapController);
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
      error.message || "Errore durante la richiesta all'assistente.",
      { error: true }
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
  workspaceUi = createWorkspaceUi({ elements, panelCopy: PANEL_COPY });
  syncChromeOffset();
  restoreAssistantPanelWidth();
  workspaceUi.restoreWorkspacePanelWidth();
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
    if (elements.selectionMunicipalityCount) {
      elements.selectionMunicipalityCount.textContent = String(selectedMunicipalityCount);
    }
    if (elements.selectionGeometryCount) {
      elements.selectionGeometryCount.textContent = String(drawnFeatureCount);
    }
    if (elements.selectionRunAnalysis) {
      elements.selectionRunAnalysis.disabled = selectedMunicipalityCount + drawnFeatureCount === 0;
    }
    if (selectionState && selectedMunicipalityCount + drawnFeatureCount > 0) {
      openSelectionPanel(mapControllerRef || mapController);
    }
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
    resolveFeatureCategory,
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
  if (assistantConfig.enabled && getActiveStudyCondition() !== "webgis") {
    openAssistantPanel(mapController);
  }
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

  elements.selectionRunAnalysis?.addEventListener("click", () => {
    runAnalysis(mapController);
  });

  elements.collapseWorkspaceButton?.addEventListener("click", () => {
    toggleOperationalPanel(mapController);
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
    const comparisonCloseButton = event.target.closest("[data-comparison-close]");
    const renameButton = event.target.closest("[data-history-rename]");
    const renameSaveButton = event.target.closest("[data-history-rename-save]");
    const renameCancelButton = event.target.closest("[data-history-rename-cancel]");
    const deleteButton = event.target.closest("[data-history-delete]");
    const deleteConfirmButton = event.target.closest("[data-history-delete-confirm]");
    const deleteCancelButton = event.target.closest("[data-history-delete-cancel]");
    if (comparisonCloseButton) {
      state.analysisHistory.comparison = null;
      renderHistoryPanel();
      return;
    }
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
    workspaceUi.restoreWorkspacePanelWidth();
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
