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

async function handleJsonResponse(response) {
  const data = await response.json();

  if (!response.ok) {
    throw new Error(data.error || "Request failed.");
  }

  return data;
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
    throw new Error(`Dataset request failed (${response.status}).`);
  }

  return response.json();
}

export async function requestNatureClip(apiUrl, payload) {
  const response = await fetch(apiUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCookie("csrftoken") || "",
    },
    body: JSON.stringify(payload),
  });

  return handleJsonResponse(response);
}

export async function sendInteractionMessage(interactionUrl, payload) {
  const response = await fetch(interactionUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCookie("csrftoken") || "",
    },
    body: JSON.stringify(payload),
  });

  return handleJsonResponse(response);
}
