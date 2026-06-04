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
  const response = await fetch(url, {
    headers: {
      Accept: "application/json",
    },
  });

  return handleJsonResponse(response);
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
