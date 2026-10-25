/**
 * TruthTrace Global Configuration
 * In local mode (empty API_BASE), all API calls use same-origin relative paths.
 * In GitHub Pages mode, API_BASE is injected by CI/CD workflow from vars.API_BASE_URL,
 * or falls back to DEFAULT_API_BASE.
 */
var DEFAULT_API_BASE = "https://truthtrace-api-l4cs.onrender.com";

window.TRUTHTRACE_CONFIG = {
  API_BASE: (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1" || window.location.hostname === "")
    ? ""
    : DEFAULT_API_BASE
};

/**
 * Returns full API URL for a given relative endpoint path.
 * If API_BASE is empty, returns clean path (same origin).
 */
function apiUrl(path) {
  if (!path) return "";
  if (path.startsWith("http://") || path.startsWith("https://") || path.startsWith("blob:") || path.startsWith("data:")) {
    return path;
  }
  const isLocal = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1" || window.location.hostname === "";
  const base = (window.TRUTHTRACE_CONFIG && window.TRUTHTRACE_CONFIG.API_BASE) || (isLocal ? "" : DEFAULT_API_BASE);
  const cleanBase = base.replace(/\/+$/, "");
  const cleanPath = path.startsWith("/") ? path : "/" + path;
  return cleanBase ? cleanBase + cleanPath : cleanPath;
}

/**
 * Helper fetch wrapper that automatically prepends apiUrl(path).
 */
function api(path, options) {
  return fetch(apiUrl(path), options);
}

// Expose globally
window.apiUrl = apiUrl;
window.api = api;
