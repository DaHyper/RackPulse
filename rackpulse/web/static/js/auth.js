(function () {
  const KEY = "rackpulse_api_key";

  function getApiKey() {
    return sessionStorage.getItem(KEY) || "";
  }

  function setApiKey(value) {
    if (value) sessionStorage.setItem(KEY, value);
    else sessionStorage.removeItem(KEY);
  }

  async function ensureApiKey() {
    const existing = getApiKey();
    if (existing) return existing;

    const key = window.prompt(
      "Enter your RackPulse API key (required when auth is enabled).\n" +
        "Leave blank if auth is disabled on this server."
    );
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
      setApiKey("");
      await ensureApiKey();
    }
    return response;
  };
})();
