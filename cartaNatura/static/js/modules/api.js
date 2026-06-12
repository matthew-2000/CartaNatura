function getCookie(name) {
  const cookieString = document.cookie;
  if (!cookieString) {
    return null;
  }

  for (const cookiePart of cookieString.split(";")) {
    const cookie = cookiePart.trim();
    if (cookie.startsWith(`${name}=`)) {
      return decodeURIComponent(cookie.slice(name.length + 1));
    }
  }

  return null;
}

let cachedAppConfig = null;

function getAppConfig() {
  if (cachedAppConfig !== null) {
    return cachedAppConfig;
  }

  const rawConfig = document.getElementById("app-config")?.textContent;
  if (!rawConfig) {
    cachedAppConfig = {};
    return cachedAppConfig;
  }

  try {
    cachedAppConfig = JSON.parse(rawConfig);
  } catch (error) {
    cachedAppConfig = {};
  }

  return cachedAppConfig;
}

function getCsrfToken() {
  return getCookie("csrftoken") || getAppConfig().csrfToken || "";
}

async function handleJsonResponse(response) {
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || "Richiesta non completata.");
    }

    return data;
  }

  await response.text();
  if (response.status === 403) {
    throw new Error("Richiesta rifiutata dal server. Ricarica la pagina e riprova.");
  }

  if (!response.ok) {
    throw new Error(`Richiesta non completata (${response.status}).`);
  }

  throw new Error("Il server ha restituito una risposta non valida.");
}

export async function fetchGeoJson(url) {
  let response = await fetch(url, {
    headers: {
      Accept: "application/json",
    },
    cache: "no-store",
  });

  if (response.status === 304) {
    const cacheBustedUrl = `${url}${url.includes("?") ? "&" : "?"}v=${Date.now()}`;
    response = await fetch(cacheBustedUrl, {
      headers: {
        Accept: "application/json",
      },
      cache: "reload",
    });
  }

  if (!response.ok) {
    throw new Error(`Dataset non caricato (${response.status}).`);
  }

  return response.json();
}

export async function requestSpatialAnalysis(apiUrl, payload) {
  const response = await fetch(apiUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCsrfToken(),
    },
    body: JSON.stringify(payload),
  });

  return handleJsonResponse(response);
}

export async function sendExperimentEvent(experimentLogUrl, payload) {
  if (!experimentLogUrl) {
    return null;
  }

  const response = await fetch(experimentLogUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCsrfToken(),
    },
    body: JSON.stringify(payload),
  });

  return handleJsonResponse(response);
}

export async function transcribeVoiceMessage(voiceTranscriptionUrl, audioBlob, metadata = {}) {
  const formData = new FormData();
  formData.append("audio", audioBlob, metadata.filename || "voice-message.webm");
  if (Number.isFinite(metadata.durationMs)) {
    formData.append("durationMs", String(Math.max(0, Math.round(metadata.durationMs))));
  }

  const response = await fetch(voiceTranscriptionUrl, {
    method: "POST",
    headers: {
      "X-CSRFToken": getCsrfToken(),
    },
    body: formData,
  });

  return handleJsonResponse(response);
}

export async function sendInteractionMessage(interactionUrl, payload) {
  const response = await fetch(interactionUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCsrfToken(),
    },
    body: JSON.stringify(payload),
  });

  return handleJsonResponse(response);
}

function parseSseFrame(frame) {
  let eventName = "message";
  const dataLines = [];

  for (const rawLine of frame.split("\n")) {
    const line = rawLine.trimEnd();
    if (!line || line.startsWith(":")) {
      continue;
    }

    if (line.startsWith("event:")) {
      eventName = line.slice(6).trim() || "message";
      continue;
    }

    if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
  }

  if (!dataLines.length) {
    return null;
  }

  return {
    eventName,
    payload: JSON.parse(dataLines.join("\n")),
  };
}

async function processSseBuffer(buffer, handlers, streamState) {
  let boundaryIndex = buffer.indexOf("\n\n");

  while (boundaryIndex !== -1) {
    const frame = buffer.slice(0, boundaryIndex);
    buffer = buffer.slice(boundaryIndex + 2);
    boundaryIndex = buffer.indexOf("\n\n");

    if (!frame.trim()) {
      continue;
    }

    const parsedFrame = parseSseFrame(frame);
    if (!parsedFrame) {
      continue;
    }

    const { eventName, payload } = parsedFrame;
    handlers.onEvent?.(eventName, payload);

    if (eventName === "status") {
      handlers.onStatus?.(payload);
    } else if (eventName === "tool_pending") {
      handlers.onToolPending?.(payload);
    } else if (eventName === "tool_start") {
      handlers.onToolStart?.(payload);
    } else if (eventName === "tool_result") {
      handlers.onToolResult?.(payload);
    } else if (eventName === "analysis_result") {
      handlers.onAnalysisResult?.(payload);
    } else if (eventName === "message_delta") {
      handlers.onMessageDelta?.(payload);
    } else if (eventName === "done") {
      streamState.donePayload = payload;
      handlers.onDone?.(payload);
    } else if (eventName === "error") {
      throw new Error(payload.message || "Errore durante lo streaming assistente.");
    }
  }

  return buffer;
}

export async function sendInteractionMessageStream(interactionUrl, payload, handlers = {}) {
  const response = await fetch(interactionUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCsrfToken(),
      Accept: "text/event-stream",
    },
    body: JSON.stringify(payload),
  });

  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("text/event-stream")) {
    return handleJsonResponse(response);
  }

  if (!response.ok) {
    return handleJsonResponse(response);
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error("Streaming non disponibile nel browser corrente.");
  }

  const decoder = new TextDecoder();
  const streamState = { donePayload: null };
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    buffer = await processSseBuffer(buffer, handlers, streamState);

    if (done) {
      break;
    }
  }

  if (buffer.trim()) {
    await processSseBuffer(`${buffer}\n\n`, handlers, streamState);
  }

  if (!streamState.donePayload) {
    throw new Error("Streaming completato senza evento finale.");
  }

  return streamState.donePayload.response || {};
}
