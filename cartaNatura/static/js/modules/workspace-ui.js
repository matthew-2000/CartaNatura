const ASSISTANT_PANEL_WIDTH_KEY = "cartaNatura.assistantPanelWidth";
const ASSISTANT_PANEL_MIN_WIDTH = 390;
const ASSISTANT_PANEL_MAX_WIDTH = 680;
const WORKSPACE_PANEL_WIDTH_KEY = "cartaNatura.workspacePanelWidth";
const WORKSPACE_PANEL_MIN_WIDTH = 320;
const WORKSPACE_PANEL_MAX_WIDTH = 520;

export function createWorkspaceUi({ elements, panelCopy }) {
  let currentMapController = null;

  function syncChromeOffset() {
    const navbarHeight = elements.navbar?.getBoundingClientRect().height ?? 0;
    document.documentElement.style.setProperty("--shell-offset", `${Math.ceil(navbarHeight)}px`);
  }

  function clampAssistantPanelWidth(width) {
    const viewportLimit = Math.max(
      ASSISTANT_PANEL_MIN_WIDTH,
      Math.min(ASSISTANT_PANEL_MAX_WIDTH, Math.floor(window.innerWidth * 0.46))
    );
    return Math.max(ASSISTANT_PANEL_MIN_WIDTH, Math.min(Number(width) || 0, viewportLimit));
  }

  function setAssistantPanelWidth(width, { persist = true, mapController = currentMapController } = {}) {
    const nextWidth = clampAssistantPanelWidth(width);
    document.documentElement.style.setProperty("--assistant-panel-width", `${nextWidth}px`);
    elements.assistantResizeHandle?.setAttribute("aria-valuenow", String(nextWidth));
    if (persist) {
      localStorage.setItem(ASSISTANT_PANEL_WIDTH_KEY, String(nextWidth));
    }
    syncLayout(mapController);
  }

  function restoreAssistantPanelWidth() {
    const storedWidth = Number(localStorage.getItem(ASSISTANT_PANEL_WIDTH_KEY));
    setAssistantPanelWidth(storedWidth || 420, { persist: false });
  }

  function clampWorkspacePanelWidth(width) {
    const viewportLimit = Math.max(
      WORKSPACE_PANEL_MIN_WIDTH,
      Math.min(WORKSPACE_PANEL_MAX_WIDTH, Math.floor(window.innerWidth * 0.38))
    );
    return Math.max(WORKSPACE_PANEL_MIN_WIDTH, Math.min(Number(width) || 0, viewportLimit));
  }

  function setWorkspacePanelWidth(width, { persist = true, mapController = currentMapController } = {}) {
    const nextWidth = clampWorkspacePanelWidth(width);
    document.documentElement.style.setProperty("--workspace-panel-width", `${nextWidth}px`);
    elements.workspaceResizeHandle?.setAttribute("aria-valuenow", String(nextWidth));
    if (persist) localStorage.setItem(WORKSPACE_PANEL_WIDTH_KEY, String(nextWidth));
    syncLayout(mapController);
  }

  function restoreWorkspacePanelWidth() {
    const storedWidth = Number(localStorage.getItem(WORKSPACE_PANEL_WIDTH_KEY));
    setWorkspacePanelWidth(storedWidth || 360, { persist: false });
  }

  function getActivePanelName() {
    if (elements.municipalityPanel.classList.contains("visualizzaListaComuni")) return "municipality";
    if (elements.popup.classList.contains("open-popup")) return "report";
    if (elements.analysisHistoryPanel.classList.contains("is-open")) return "history";
    return null;
  }

  function syncPanelChrome(activePanelName) {
    const copy = activePanelName ? panelCopy[activePanelName] : null;
    if (copy) {
      elements.workspacePanelTitle.textContent = copy.title;
      if (elements.workspacePanelDescription) elements.workspacePanelDescription.textContent = copy.description;
    }
    for (const button of document.querySelectorAll("[data-panel-nav]")) {
      const isAssistant = button.dataset.panelNav === "assistant";
      const isActive = isAssistant
        ? elements.assistantPanel.classList.contains("is-open")
        : button.dataset.panelNav === activePanelName;
      button.classList.toggle("is-active", isActive);
      button.setAttribute("aria-pressed", String(isActive));
    }
  }

  function syncLayout(mapController = currentMapController) {
    const activePanelName = getActivePanelName();
    document.body.classList.toggle("side-panel-open", Boolean(activePanelName));
    document.body.classList.toggle("municipality-workbench-open", activePanelName === "municipality");
    document.body.classList.toggle("report-workbench-open", activePanelName === "report");
    document.body.classList.toggle("history-workbench-open", activePanelName === "history");
    document.body.classList.toggle("assistant-workbench-open", elements.assistantPanel.classList.contains("is-open"));
    syncPanelChrome(activePanelName);
    if (mapController) {
      window.requestAnimationFrame(() => {
        mapController.syncLayout();
        window.setTimeout(() => mapController.syncLayout(), 230);
      });
    }
  }

  function initializeResize(mapController) {
    currentMapController = mapController;
    const handle = elements.assistantResizeHandle;
    if (!handle) return;
    let isDragging = false;

    const handlePointerMove = (event) => {
      if (isDragging) setAssistantPanelWidth(window.innerWidth - event.clientX, { mapController });
    };
    const stopDragging = () => {
      if (!isDragging) return;
      isDragging = false;
      document.body.classList.remove("assistant-resizing");
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", stopDragging);
      syncLayout(mapController);
    };

    handle.addEventListener("pointerdown", (event) => {
      isDragging = true;
      document.body.classList.add("assistant-resizing");
      handle.setPointerCapture?.(event.pointerId);
      window.addEventListener("pointermove", handlePointerMove);
      window.addEventListener("pointerup", stopDragging);
      event.preventDefault();
    });
    handle.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      const current = Number.parseInt(
        getComputedStyle(document.documentElement).getPropertyValue("--assistant-panel-width"), 10
      ) || 520;
      const step = event.shiftKey ? 48 : 24;
      const next = event.key === "Home"
        ? ASSISTANT_PANEL_MIN_WIDTH
        : event.key === "End"
          ? ASSISTANT_PANEL_MAX_WIDTH
          : current + (event.key === "ArrowLeft" ? step : -step);
      setAssistantPanelWidth(next, { mapController });
      event.preventDefault();
    });

    const workspaceHandle = elements.workspaceResizeHandle;
    if (!workspaceHandle) return;
    let workspaceDragging = false;
    const moveWorkspace = (event) => {
      if (!workspaceDragging) return;
      const assistantWidth = elements.assistantPanel.classList.contains("is-open")
        ? elements.assistantPanel.getBoundingClientRect().width
        : 0;
      setWorkspacePanelWidth(window.innerWidth - assistantWidth - event.clientX, { mapController });
    };
    const stopWorkspace = () => {
      if (!workspaceDragging) return;
      workspaceDragging = false;
      document.body.classList.remove("workspace-resizing");
      window.removeEventListener("pointermove", moveWorkspace);
      window.removeEventListener("pointerup", stopWorkspace);
      syncLayout(mapController);
    };
    workspaceHandle.addEventListener("pointerdown", (event) => {
      workspaceDragging = true;
      document.body.classList.remove("operational-panel-collapsed");
      document.body.classList.add("workspace-resizing");
      workspaceHandle.setPointerCapture?.(event.pointerId);
      window.addEventListener("pointermove", moveWorkspace);
      window.addEventListener("pointerup", stopWorkspace);
      event.preventDefault();
    });
    workspaceHandle.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      const current = Number.parseInt(
        getComputedStyle(document.documentElement).getPropertyValue("--workspace-panel-width"), 10
      ) || 360;
      const step = event.shiftKey ? 48 : 24;
      const next = event.key === "Home"
        ? WORKSPACE_PANEL_MIN_WIDTH
        : event.key === "End"
          ? WORKSPACE_PANEL_MAX_WIDTH
          : current + (event.key === "ArrowLeft" ? step : -step);
      setWorkspacePanelWidth(next, { mapController });
      event.preventDefault();
    });
  }

  return {
    getActivePanelName,
    initializeResize,
    restoreAssistantPanelWidth,
    restoreWorkspacePanelWidth,
    syncChromeOffset,
    syncLayout,
  };
}
