(function () {
  const KEY = "rackpulse_api_key";
  let authRequired = null;

  function getApiKey() {
    return sessionStorage.getItem(KEY) || "";
  }

  function setApiKey(value) {
    if (value) sessionStorage.setItem(KEY, value);
    else sessionStorage.removeItem(KEY);
  }

  async function isAuthRequired() {
    if (authRequired !== null) return authRequired;
    try {
      const res = await fetch("/api/health");
      if (!res.ok) return false;
      const data = await res.json();
      authRequired = !!data.auth_required;
      return authRequired;
    } catch {
      return false;
    }
  }

  async function ensureApiKey() {
    const existing = getApiKey();
    if (existing) return existing;
    if (!(await isAuthRequired())) return "";

    const key = window.prompt("Enter your RackPulse API key:");
    if (key) setApiKey(key.trim());
    return getApiKey();
  }

  const originalFetch = window.fetch.bind(window);
  window.fetch = async function (input, init = {}) {
    const url = typeof input === "string" ? input : input.url;
    if (url.startsWith("/api/") && url !== "/api/health") {
      await ensureApiKey();
      const headers = new Headers(init.headers || {});
      const apiKey = getApiKey();
      if (apiKey) headers.set("X-API-Key", apiKey);
      init = { ...init, headers };
    }
    const response = await originalFetch(input, init);
    if (response.status === 401 && url.startsWith("/api/")) {
      authRequired = true;
      setApiKey("");
      await ensureApiKey();
    }
    return response;
  };
})();
