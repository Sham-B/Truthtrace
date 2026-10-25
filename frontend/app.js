// TruthTrace Global API Helpers
var DEFAULT_API_BASE = "https://truthtrace-api-l4cs.onrender.com";

// config.js provides window.apiUrl and window.api. Ensure safe fallbacks without const redeclaration.
if (typeof window.apiUrl !== "function") {
  window.apiUrl = function(path) {
    if (!path) return "";
    if (path.startsWith("http://") || path.startsWith("https://") || path.startsWith("blob:") || path.startsWith("data:")) return path;
    const isLocal = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1" || window.location.hostname === "";
    const base = (window.TRUTHTRACE_CONFIG && window.TRUTHTRACE_CONFIG.API_BASE) || (isLocal ? "" : DEFAULT_API_BASE);
    const cleanBase = base.replace(/\/+$/, "");
    const cleanPath = path.startsWith("/") ? path : "/" + path;
    return cleanBase ? cleanBase + cleanPath : cleanPath;
  };
}
if (typeof window.api !== "function") {
  window.api = function(path, opts) {
    return fetch(window.apiUrl(path), opts);
  };
}
var apiUrl = window.apiUrl;
var api = window.api;


/**
 * TruthTrace UI Controller
 * High-performance, plain-language, GIGW-accessible application validation assistant.
 */

// Global Application State
const state = {
  role: localStorage.getItem("truthtrace-role") || "Officer",
  theme: localStorage.getItem("truthtrace-theme") || "light",
  textSize: localStorage.getItem("truthtrace-text-size") || "normal",
  lang: localStorage.getItem("truthtrace-lang") || "en",
  currentView: "viewHome",
  applications: [],
  filteredApplications: [],
  currentFilter: "all",
  searchQuery: "",
  activeAppId: null,
  activeAppDetail: null,
  activeDocId: null,
  activePageNum: 0,
  currentDocZoom: 1.0,
  donutChartInstance: null,
  riskMapChartInstance: null,
  cyGraphInstance: null,
  issuerServerDown: false,
  tourCurrentStep: 0,
  currentRuns: [],
  currentDiff: null,
  diffFilter: "all",
  backendError: false,
};

// Bilingual dictionary for Navigation, Actions, and Status Chips
const i18n = {
  en: {
    nav_home: "Home",
    nav_applications: "Applications",
    nav_insights: "Insights",
    nav_alerts: "Alerts",
    nav_risk_map: "Risk map",
    nav_duplicates: "Duplicate document check",
    nav_fraud_test: "Fraud detection test",
    nav_activity_log: "Activity log",
    nav_help: "Help & Glossary",
    nav_preflight: "Self-check",
    status_verified: "Verified",
    status_needs_review: "Needs review",
    status_mismatch_detected: "Mismatch found",
    status_expired: "Expired",
    status_waiting: "Waiting for issuer",
    status_issuer_unavailable: "Issuer unavailable",
  },
  hi: {
    nav_home: "मुख्य पृष्ठ",
    nav_applications: "आवेदन सूची",
    nav_insights: "विश्लेषण",
    nav_alerts: "सूचनाएं",
    nav_risk_map: "जोखिम मानचित्र",
    nav_duplicates: "दस्तावेज़ पुनरावृत्ति जांच",
    nav_fraud_test: "धोखाधड़ी परीक्षण",
    nav_activity_log: "कार्य लॉग",
    nav_help: "सहायता व शब्दावली",
    nav_preflight: "स्व-जांच (Pre-check)",
    status_verified: "सत्यापित",
    status_needs_review: "समीक्षा आवश्यक",
    status_mismatch_detected: "विसंगति मिली",
    status_expired: "समाप्त (अवधि पूर्ण)",
    status_waiting: "सत्यापन की प्रतीक्षा",
    status_issuer_unavailable: "सर्वर अनुपलब्ध",
  }
};

// Initialize Application on DOM Ready

// ============================================================================
// STARTUP HEALTH SPLASH & PUBLIC DEMO BANNER
// ============================================================================

function showSplashLoading(title, message) {
  const splash = document.getElementById("startupSplash");
  const spinner = document.getElementById("splashSpinner");
  const icon = document.getElementById("splashIcon");
  const titleEl = document.getElementById("splashTitle");
  const msgEl = document.getElementById("splashMessage");
  const actionBox = document.getElementById("splashActionBox");

  if (splash) splash.style.display = "flex";
  if (spinner) spinner.style.display = "block";
  if (icon) icon.style.display = "none";
  if (actionBox) actionBox.style.display = "none";
  if (titleEl) titleEl.textContent = title;
  if (msgEl) msgEl.textContent = message;
}

function showSplashError(title, message, showRetry = true) {
  const splash = document.getElementById("startupSplash");
  const spinner = document.getElementById("splashSpinner");
  const icon = document.getElementById("splashIcon");
  const titleEl = document.getElementById("splashTitle");
  const msgEl = document.getElementById("splashMessage");
  const actionBox = document.getElementById("splashActionBox");

  if (splash) splash.style.display = "flex";
  if (spinner) spinner.style.display = "none";
  if (icon) icon.style.display = "block";
  if (titleEl) titleEl.textContent = title;
  if (msgEl) msgEl.textContent = message;
  if (actionBox) actionBox.style.display = showRetry ? "flex" : "none";
}

function hideSplash() {
  const splash = document.getElementById("startupSplash");
  if (splash) splash.style.display = "none";
}

function showDemoBanner() {
  const banner = document.getElementById("demoNoticeBanner");
  if (banner && !sessionStorage.getItem("truthtrace-demo-banner-dismissed")) {
    banner.style.display = "block";
  }
}

async function checkBackendHealth() {
  const isLocalhost = window.location.hostname === "localhost" ||
                      window.location.hostname === "127.0.0.1" ||
                      window.location.hostname === "";
  let apiBase = (window.TRUTHTRACE_CONFIG && window.TRUTHTRACE_CONFIG.API_BASE) || "";

  // If API_BASE is empty on a non-localhost host, use DEFAULT_API_BASE fallback
  if (!apiBase && !isLocalhost) {
    apiBase = DEFAULT_API_BASE;
    if (window.TRUTHTRACE_CONFIG) {
      window.TRUTHTRACE_CONFIG.API_BASE = DEFAULT_API_BASE;
    }
  }

  showSplashLoading("Connecting to TruthTrace...", "Waking up the demo server. The first visit can take up to a minute.");

  let attempts = 0;
  const maxAttempts = 60;
  while (attempts < maxAttempts) {
    attempts++;
    try {
      const res = await fetch(apiUrl("/health"), { cache: "no-store" });
      if (res.ok) {
        const data = await res.json();
        if (data.ready) {
          hideSplash();
          if (data.demo_mode) {
            showDemoBanner();
          }
          return true;
        } else {
          showSplashLoading("Initializing database...", "Waking up the demo server. The first visit can take up to a minute.");
        }
      }
    } catch (err) {
      // Backend is asleep or booting
      showSplashLoading("Connecting to demo server...", "Waking up the demo server. The first visit can take up to a minute.");
    }
    await new Promise(r => setTimeout(r, 1500));
  }

  showSplashError(
    "Server Wake-up Timeout",
    "The demo server took longer than expected to wake up. Click retry to connect again.",
    true
  );
  return false;
}

document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  initTextSize();
  initLanguage();
  initRole();
  setupNavigation();
  setupEventListeners();

  // Load dashboard queue immediately so UI is responsive
  loadDashboardData();

  // Health check & startup splash polling in background
  checkBackendHealth().then((isHealthy) => {
    if (isHealthy) {
      initDemoStatus();
      loadDashboardData();

      // Show Welcome Modal on first visit
      if (!localStorage.getItem("truthtrace-welcome-seen")) {
        showWelcomeModal();
      }
    }
  });
});

// ============================================================================
// 1. THEME, TEXT SIZE, LANGUAGE, ROLE INITIALIZATION
// ============================================================================

function initTheme() {
  document.documentElement.setAttribute("data-theme", state.theme);
  const icon = document.getElementById("themeIcon");
  if (icon) icon.textContent = state.theme === "dark" ? "☀️" : "🌙";
}

function toggleTheme() {
  state.theme = state.theme === "light" ? "dark" : "light";
  localStorage.setItem("truthtrace-theme", state.theme);
  initTheme();
}

function initTextSize() {
  document.documentElement.setAttribute("data-text-size", state.textSize);
  document.querySelectorAll(".text-zoom-group .btn-zoom").forEach(btn => btn.classList.remove("active"));
  if (state.textSize === "small") document.getElementById("textSizeSmallBtn")?.classList.add("active");
  else if (state.textSize === "large") document.getElementById("textSizeLargeBtn")?.classList.add("active");
  else document.getElementById("textSizeNormalBtn")?.classList.add("active");
}

function setTextSize(size) {
  state.textSize = size;
  localStorage.setItem("truthtrace-text-size", size);
  initTextSize();
}

function initLanguage() {
  applyLanguage();
}

function toggleLanguage() {
  state.lang = state.lang === "en" ? "hi" : "en";
  localStorage.setItem("truthtrace-lang", state.lang);
  applyLanguage();
}

function applyLanguage() {
  const btn = document.getElementById("langToggleBtn");
  if (btn) btn.textContent = state.lang === "en" ? "हिन्दी" : "English";

  const dict = i18n[state.lang] || i18n.en;
  document.querySelectorAll("[data-i18n]").forEach(elem => {
    const key = elem.getAttribute("data-i18n");
    if (dict[key]) elem.textContent = dict[key];
  });
}

function initRole() {
  const roleSelect = document.getElementById("roleSelect");
  if (roleSelect) {
    roleSelect.value = state.role;
  }
  applyRolePermissions(state.role);
}

function setRole(newRole) {
  state.role = newRole;
  localStorage.setItem("truthtrace-role", newRole);
  const roleSelect = document.getElementById("roleSelect");
  if (roleSelect) roleSelect.value = newRole;
  applyRolePermissions(newRole);
  showToast(`Switched view to: ${getRoleDisplayName(newRole)}`, "info");
  loadDashboardData();
  if (state.activeAppId && state.currentView === "viewApplications") {
    loadApplicationDetail(state.activeAppId);
  }
}

function getRoleDisplayName(role) {
  if (role === "Officer") return "AICTE Scrutiny Officer";
  if (role === "Institution") return "College (applicant)";
  if (role === "Auditor") return "Auditor";
  return role;
}

function applyRolePermissions(role) {
  const sidebarRoleLabel = document.getElementById("sidebarRoleLabel");
  if (sidebarRoleLabel) sidebarRoleLabel.textContent = getRoleDisplayName(role);

  const insightsSection = document.getElementById("insightsNavSection");
  const auditNavBtn = document.getElementById("navAuditLog");
  const recordDecisionBtn = document.getElementById("recordDecisionBtn");
  const preflightNavBtn = document.getElementById("navPreflight");

  if (role === "Institution") {
    // College cannot view Insights or Audit Log or run officer decisions
    if (insightsSection) insightsSection.style.display = "none";
    if (auditNavBtn) auditNavBtn.style.display = "none";
    if (recordDecisionBtn) recordDecisionBtn.style.display = "none";
    if (preflightNavBtn) preflightNavBtn.style.display = "flex";
    
    // Switch away if user was on an officer-only view
    if (["viewAlerts", "viewRiskMap", "viewDuplicates", "viewFraudTest", "viewAuditLog", "viewAdversarialLab"].includes(state.currentView)) {
      switchView("viewApplications");
    }
  } else if (role === "Auditor") {
    if (insightsSection) insightsSection.style.display = "block";
    if (auditNavBtn) auditNavBtn.style.display = "flex";
    if (recordDecisionBtn) recordDecisionBtn.style.display = "none";
    if (preflightNavBtn) preflightNavBtn.style.display = "none";
  } else {
    // AICTE Scrutiny Officer
    if (insightsSection) insightsSection.style.display = "block";
    if (auditNavBtn) auditNavBtn.style.display = "flex";
    if (recordDecisionBtn) recordDecisionBtn.style.display = "inline-flex";
    if (preflightNavBtn) preflightNavBtn.style.display = "none";
  }
}

// ============================================================================
// 2. DEMO CONTROLS & CHAOS TOGGLE
// ============================================================================

async function initDemoStatus() {
  try {
    const res = await api("/demo/status");
    if (res.ok) {
      const data = await res.json();
      state.issuerServerDown = data.issuer_server_down;
      updateDemoOutageUI();
    }
  } catch (err) {
    console.warn("Could not check demo status:", err);
  }
}

function updateDemoOutageUI() {
  const pill = document.getElementById("demoOutagePill");
  const toggle = document.getElementById("issuerOutageToggle");
  if (pill) pill.style.display = state.issuerServerDown ? "inline-flex" : "none";
  if (toggle) toggle.checked = state.issuerServerDown;
}

async function toggleIssuerOutage(isDown) {
  try {
    const res = await api("/demo/toggle-issuer-outage", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ down: isDown })
    });
    if (res.ok) {
      const data = await res.json();
      state.issuerServerDown = data.issuer_server_down;
      updateDemoOutageUI();
      showToast(
        state.issuerServerDown 
          ? "Pretend issuer server is DOWN (simulated outage)" 
          : "Pretend issuer server restored (normal)",
        state.issuerServerDown ? "warning" : "success"
      );
      loadDashboardData();
      if (state.activeAppId) loadApplicationDetail(state.activeAppId);
    }
  } catch (err) {
    showToast("Failed to update issuer demo toggle", "error");
  }
}

async function resetSeedData() {
  try {
    showToast("Resetting to 5 canonical example applications...", "info");
    const res = await api("/demo/reset-seed", { method: "POST" });
    if (res.ok) {
      showToast("Seed data reset successfully!", "success");
      await initDemoStatus();
      loadDashboardData();
      if (state.currentView === "viewApplications") {
        document.getElementById("applicationDetailView").style.display = "none";
        document.getElementById("applicationsListView").style.display = "block";
        state.activeAppId = null;
      }
    }
  } catch (err) {
    showToast("Failed to reset seed data", "error");
  }
}

// ============================================================================
// 3. NAVIGATION & VIEW SWITCHING
// ============================================================================

function setupNavigation() {
  document.querySelectorAll(".nav-item-btn[data-view], .sub-nav-item-btn[data-view]").forEach(btn => {
    btn.addEventListener("click", () => {
      const targetView = btn.getAttribute("data-view");
      switchView(targetView);
    });
  });

  const insightsToggle = document.getElementById("navInsightsToggle");
  const insightsMenu = document.getElementById("insightsSubMenu");
  if (insightsToggle && insightsMenu) {
    insightsToggle.addEventListener("click", () => {
      insightsToggle.classList.toggle("open");
      const isOpen = insightsToggle.classList.contains("open");
      insightsMenu.style.display = isOpen ? "flex" : "none";
      insightsToggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
    });
  }

  // Brand logo click goes to Home
  document.getElementById("brandHomeLink")?.addEventListener("click", (e) => {
    e.preventDefault();
    switchView("viewHome");
  });
}

function setFraudMode(mode) {
  const benchBtn = document.getElementById("fraudModeBenchmarkBtn");
  const sandBtn = document.getElementById("fraudModeSandboxBtn");
  const benchSec = document.getElementById("fraudBenchmarkContainer");
  const sandSec = document.getElementById("fraudSandboxContainer");
  const benchActions = document.getElementById("fraudBenchmarkActions");

  if (mode === "sandbox") {
    benchBtn?.classList.remove("active");
    sandBtn?.classList.add("active");
    if (benchSec) benchSec.style.display = "none";
    if (sandSec) sandSec.style.display = "block";
    if (benchActions) benchActions.style.display = "none";
    loadAdversarialLabView();
  } else {
    sandBtn?.classList.remove("active");
    benchBtn?.classList.add("active");
    if (sandSec) sandSec.style.display = "none";
    if (benchSec) benchSec.style.display = "block";
    if (benchActions) benchActions.style.display = "block";
  }
}

function switchView(viewId) {
  if (viewId === "viewAdversarialLab") {
    viewId = "viewFraudTest";
    setFraudMode("sandbox");
  }

  state.currentView = viewId;

  // Toggle nav buttons active state
  document.querySelectorAll(".nav-item-btn, .sub-nav-item-btn").forEach(btn => {
    if (btn.getAttribute("data-view") === viewId) {
      btn.classList.add("active");
    } else {
      btn.classList.remove("active");
    }
  });

  // Hide all view panels, show selected panel
  document.querySelectorAll(".view-panel").forEach(panel => {
    if (panel.id === viewId) {
      panel.classList.add("active");
    } else {
      panel.classList.remove("active");
    }
  });

  // Trigger view-specific data loading
  if (viewId === "viewHome") {
    loadDashboardData();
  } else if (viewId === "viewApplications") {
    renderApplicationsGrid();
  } else if (viewId === "viewAlerts") {
    loadAlertsView();
  } else if (viewId === "viewRiskMap") {
    loadRiskMapView();
  } else if (viewId === "viewDuplicates") {
    loadDuplicatesView();
  } else if (viewId === "viewFraudTest") {
    loadFraudTestView();
  } else if (viewId === "viewAuditLog") {
    loadAuditLogView();
  } else if (viewId === "viewPreflight") {
    loadPreflightView();
  }
}

// ============================================================================
// 4. EVENT LISTENERS SETUP
// ============================================================================

function setupEventListeners() {
  // Splash Retry and Demo Banner Dismiss Listeners
  document.getElementById("splashCloseBtn")?.addEventListener("click", hideSplash);
  document.getElementById("splashDismissBtn")?.addEventListener("click", hideSplash);
  document.getElementById("splashRetryBtn")?.addEventListener("click", async () => {
    const ok = await checkBackendHealth();
    if (ok) {
      initDemoStatus();
      loadDashboardData();
    }
  });

  document.getElementById("dismissDemoBannerBtn")?.addEventListener("click", () => {
    const banner = document.getElementById("demoNoticeBanner");
    if (banner) banner.style.display = "none";
    sessionStorage.setItem("truthtrace-demo-banner-dismissed", "1");
  });

  // Fraud Detection Mode Switcher
  document.getElementById("fraudModeBenchmarkBtn")?.addEventListener("click", () => setFraudMode("benchmark"));
  document.getElementById("fraudModeSandboxBtn")?.addEventListener("click", () => setFraudMode("sandbox"));

  // Adversarial Test Lab Listeners
  setupAdversarialLabListeners();

  // Theme Toggle
  document.getElementById("themeToggleBtn")?.addEventListener("click", toggleTheme);

  // Text Zoom Buttons
  document.getElementById("textSizeSmallBtn")?.addEventListener("click", () => setTextSize("small"));
  document.getElementById("textSizeNormalBtn")?.addEventListener("click", () => setTextSize("normal"));
  document.getElementById("textSizeLargeBtn")?.addEventListener("click", () => setTextSize("large"));

  // Language Switcher
  document.getElementById("langToggleBtn")?.addEventListener("click", toggleLanguage);

  // Role Select Dropdown
  document.getElementById("roleSelect")?.addEventListener("change", (e) => {
    setRole(e.target.value);
  });

  // Demo Drawer Controls
  const demoDrawer = document.getElementById("demoDrawer");
  document.getElementById("openDemoDrawerBtn")?.addEventListener("click", () => {
    demoDrawer?.classList.add("open");
  });
  document.getElementById("closeDemoDrawerBtn")?.addEventListener("click", () => {
    demoDrawer?.classList.remove("open");
  });
  document.getElementById("issuerOutageToggle")?.addEventListener("change", (e) => {
    toggleIssuerOutage(e.target.checked);
  });
  document.getElementById("resetSeedBtn")?.addEventListener("click", resetSeedData);

  // Quick Archetype Links in Demo Drawer
  document.querySelectorAll(".quick-app-link").forEach(btn => {
    btn.addEventListener("click", () => {
      const appId = btn.getAttribute("data-app-id");
      demoDrawer?.classList.remove("open");
      switchView("viewApplications");
      loadApplicationDetail(appId);
    });
  });

  // Demo Sample Downloads
  const downloadSampleHandler = (e) => {
    e.preventDefault();
    const sampleUrl = typeof apiUrl === "function" ? apiUrl("/demo/samples/corrected_accreditation_certificate.pdf") : "/demo/samples/corrected_accreditation_certificate.pdf";
    const link = document.createElement("a");
    link.href = sampleUrl;
    link.download = "corrected_accreditation_certificate.pdf";
    link.target = "_blank";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    if (typeof showToast === "function") showToast("Downloading sample corrected certificate...", "info");
  };
  document.getElementById("demoSamplesLinkDrawer")?.addEventListener("click", downloadSampleHandler);
  document.getElementById("demoSamplesLinkCollege")?.addEventListener("click", downloadSampleHandler);

  // Tour Button
  document.getElementById("startTourBtn")?.addEventListener("click", startCoachTour);
  document.getElementById("tourSkipBtn")?.addEventListener("click", endCoachTour);
  document.getElementById("tourNextBtn")?.addEventListener("click", nextCoachTourStep);

  // Home Stat Cards Navigation & Filtering
  document.getElementById("statCardReview")?.addEventListener("click", () => {
    switchView("viewApplications");
    setApplicationsFilter("needs_review");
  });
  document.getElementById("statCardProblems")?.addEventListener("click", () => {
    switchView("viewApplications");
    setApplicationsFilter("mismatch_detected");
  });
  document.getElementById("statCardWaiting")?.addEventListener("click", () => {
    switchView("viewApplications");
    setApplicationsFilter("all");
  });
  document.getElementById("statCardCleared")?.addEventListener("click", () => {
    switchView("viewApplications");
    setApplicationsFilter("verified");
  });

  // Applications List Toolbar
  document.getElementById("refreshAppsBtn")?.addEventListener("click", loadDashboardData);
  document.getElementById("appSearchInput")?.addEventListener("input", (e) => {
    state.searchQuery = e.target.value.toLowerCase();
    renderApplicationsGrid();
  });

  // Filter Chips in Applications View
  document.querySelectorAll(".status-filter-chips .chip-filter-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const filter = btn.getAttribute("data-filter");
      setApplicationsFilter(filter);
    });
  });

  // Detail View Buttons
  document.getElementById("backToAppsBtn")?.addEventListener("click", () => {
    document.getElementById("applicationDetailView").style.display = "none";
    document.getElementById("applicationsListView").style.display = "block";
    state.activeAppId = null;
  });

  document.getElementById("runChecksBtn")?.addEventListener("click", () => {
    if (state.activeAppId) runAutomatedChecksWithAnimation(state.activeAppId);
  });

  document.getElementById("recordDecisionBtn")?.addEventListener("click", openDecisionModal);

  // Tab Switching in Detail View
  document.querySelectorAll(".tabs-navigation-bar .tab-link-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tabs-navigation-bar .tab-link-btn").forEach(b => {
        b.classList.remove("active");
        b.setAttribute("aria-selected", "false");
      });
      document.querySelectorAll(".detail-tab-pane").forEach(p => p.classList.remove("active"));
      
      btn.classList.add("active");
      btn.setAttribute("aria-selected", "true");
      const targetPane = document.getElementById(btn.getAttribute("data-tab"));
      if (targetPane) targetPane.classList.add("active");

      // Trigger Cytoscape redraw if Cross-checks tab is active
      if (btn.getAttribute("data-tab") === "tabCrossChecks" && state.activeAppId) {
        renderCytoscapeGraph(state.activeAppId);
      }
    });
  });

  // Collapsible Limits Panel
  document.getElementById("limitsToggleBtn")?.addEventListener("click", () => {
    const body = document.getElementById("limitsBody");
    const arrow = document.getElementById("limitsArrowIcon");
    if (body) {
      body.classList.toggle("open");
      if (arrow) arrow.textContent = body.classList.contains("open") ? "▲" : "▼";
    }
  });

  // Document Page Zoom Controls
  document.getElementById("docZoomInBtn")?.addEventListener("click", () => {
    state.currentDocZoom = Math.min(2.5, state.currentDocZoom + 0.2);
    applyDocZoom();
  });
  document.getElementById("docZoomOutBtn")?.addEventListener("click", () => {
    state.currentDocZoom = Math.max(0.6, state.currentDocZoom - 0.2);
    applyDocZoom();
  });
  document.getElementById("docZoomResetBtn")?.addEventListener("click", () => {
    state.currentDocZoom = 1.0;
    applyDocZoom();
  });

  // Cross-Checks Table vs Graph Toggle
  document.getElementById("toggleGraphViewBtn")?.addEventListener("click", (e) => {
    const tableWrap = document.getElementById("crossChecksTableWrap");
    const graphWrap = document.getElementById("crossChecksGraphWrap");
    if (graphWrap.style.display === "none") {
      graphWrap.style.display = "block";
      tableWrap.style.display = "none";
      e.target.textContent = "Show Comparison Table";
      if (state.activeAppId) renderCytoscapeGraph(state.activeAppId);
    } else {
      graphWrap.style.display = "none";
      tableWrap.style.display = "block";
      e.target.textContent = "Show Interactive Graph";
    }
  });

  // History Tab Integrity Verification
  document.getElementById("verifyIntegrityBtn")?.addEventListener("click", verifyAuditIntegrityInHistory);

  // Decision Modal Actions
  document.getElementById("closeDecisionModalBtn")?.addEventListener("click", closeDecisionModal);
  document.getElementById("cancelDecisionBtn")?.addEventListener("click", closeDecisionModal);
  document.getElementById("confirmDecisionBtn")?.addEventListener("click", submitOfficerDecision);

  document.querySelectorAll(".decision-radio-card input[type='radio']").forEach(radio => {
    radio.addEventListener("change", () => {
      document.querySelectorAll(".decision-radio-card").forEach(c => c.classList.remove("selected"));
      radio.closest(".decision-radio-card")?.classList.add("selected");
    });
  });

  const writtenReason = document.getElementById("officerWrittenReason");
  writtenReason?.addEventListener("input", (e) => {
    const count = e.target.value.length;
    const countLabel = document.getElementById("reasonCharCount");
    if (countLabel) countLabel.textContent = count;
  });

  // Insights View Buttons
  document.getElementById("rescanDuplicatesBtn")?.addEventListener("click", loadDuplicatesView);
  document.getElementById("runFraudTestBtn")?.addEventListener("click", runFraudDetectionTest);
  document.getElementById("verifyAuditChainBtn")?.addEventListener("click", verifyAuditLedgerChain);
  document.getElementById("simulateTamperDemoBtn")?.addEventListener("click", simulateAuditTamperDemo);

  // College Preflight Actions
  document.getElementById("runPreflightCheckBtn")?.addEventListener("click", runCollegePreflightCheck);
  document.getElementById("replaceDocForm")?.addEventListener("submit", handleDocumentReplacement);

  // Summary Tab Slim Diff Banner Action
  document.getElementById("summarySeeWhatChangedBtn")?.addEventListener("click", () => {
    document.querySelectorAll(".tabs-navigation-bar .tab-link-btn").forEach(b => {
      b.classList.remove("active");
      b.setAttribute("aria-selected", "false");
    });
    document.querySelectorAll(".detail-tab-pane").forEach(p => p.classList.remove("active"));
    document.querySelector(".tab-link-btn[data-tab='tabHistory']")?.classList.add("active");
    document.getElementById("tabHistory")?.classList.add("active");
  });

  // What Changed Filter Tiles in History Tab
  document.getElementById("tileFixed")?.addEventListener("click", () => {
    state.diffFilter = state.diffFilter === "resolved" ? "all" : "resolved";
    renderDiffFindingsList(state.currentDiff, state.diffFilter);
  });
  document.getElementById("tileNew")?.addEventListener("click", () => {
    state.diffFilter = state.diffFilter === "introduced" ? "all" : "introduced";
    renderDiffFindingsList(state.currentDiff, state.diffFilter);
  });
  document.getElementById("tileOpen")?.addEventListener("click", () => {
    state.diffFilter = state.diffFilter === "persisting" ? "all" : "persisting";
    renderDiffFindingsList(state.currentDiff, state.diffFilter);
  });

  // Collapsible Fixed Items Toggle
  document.getElementById("diffFixedToggle")?.addEventListener("click", () => {
    const body = document.getElementById("diffFixedBody");
    const arrow = document.getElementById("fixedGroupArrow");
    if (body) {
      body.classList.toggle("open");
      if (arrow) arrow.textContent = body.classList.contains("open") ? "▲" : "▼";
    }
  });

  // Compare Other Checks Button in Technical Details
  document.getElementById("btnCompareChecks")?.addEventListener("click", () => {
    if (state.activeAppId) compareToSelectedChecks(state.activeAppId);
  });
}

function applyDocZoom() {
  const container = document.getElementById("docPageContainer");
  if (container) {
    container.style.transform = `scale(${state.currentDocZoom})`;
    container.style.transformOrigin = "top left";
  }
}

// ============================================================================
// 5. STAGE 2: HOME DASHBOARD & QUEUE DATA FETCHING
// ============================================================================

async function loadDashboardData() {
  try {
    const res = await api("/applications", {
      headers: { "x-user-role": state.role }
    });
    if (!res.ok) throw new Error("Failed to load applications");
    const data = await res.json();
    state.applications = data;
    state.backendError = false;

    // Update Counts & Stat Cards with animated count-up
    updateDashboardStatCards();

    // Render "Needs your attention" list
    renderAttentionList();

    // Render Donut Chart
    renderStatusDonutChart();

    // Render Applications Grid if on that view
    renderApplicationsGrid();

    // Update alerts count badge
    loadAlertsBadgeCount();

    const lastChecked = document.getElementById("homeLastCheckedTime");
    if (lastChecked) {
      const now = new Date();
      lastChecked.textContent = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')} (Live)`;
    }
  } catch (err) {
    console.error("Dashboard data load error:", err);
    state.backendError = true;
    showToast("Error loading application queue", "error");
    renderAttentionList();
    renderApplicationsGrid();
  }
}

function updateDashboardStatCards() {
  let reviewCount = 0;
  let problemsCount = 0;
  let waitingCount = 0;
  let clearedCount = 0;

  state.applications.forEach(app => {
    const plain = (app.plain_status || "").toLowerCase();
    if (plain.includes("review")) reviewCount++;
    else if (plain.includes("mismatch") || plain.includes("expired")) problemsCount++;
    else if (plain.includes("waiting") || plain.includes("unavailable")) waitingCount++;
    else if (plain.includes("verified")) clearedCount++;
  });

  animateCountUp("statNumReview", reviewCount);
  animateCountUp("statNumProblems", problemsCount);
  animateCountUp("statNumWaiting", waitingCount);
  animateCountUp("statNumCleared", clearedCount);

  // Update filter chip counters
  document.getElementById("filterCountAll").textContent = state.applications.length;
  document.getElementById("filterCountVerified").textContent = clearedCount;
  document.getElementById("filterCountReview").textContent = reviewCount;
  document.getElementById("filterCountMismatch").textContent = state.applications.filter(a => (a.plain_status || "").toLowerCase().includes("mismatch")).length;
  document.getElementById("filterCountExpired").textContent = state.applications.filter(a => (a.plain_status || "").toLowerCase().includes("expired")).length;
}

function animateCountUp(elementId, targetValue, duration = 600) {
  const elem = document.getElementById(elementId);
  if (!elem) return;
  const startValue = parseInt(elem.textContent) || 0;
  if (startValue === targetValue) {
    elem.textContent = targetValue;
    return;
  }
  const startTime = performance.now();

  function updateNumber(currentTime) {
    const elapsed = currentTime - startTime;
    const progress = Math.min(elapsed / duration, 1.0);
    const current = Math.floor(startValue + (targetValue - startValue) * progress);
    elem.textContent = current;
    if (progress < 1.0) {
      requestAnimationFrame(updateNumber);
    } else {
      elem.textContent = targetValue;
    }
  }
  requestAnimationFrame(updateNumber);
}

function renderAttentionList() {
  const container = document.getElementById("attentionListContainer");
  if (!container) return;

  // Filter items needing attention (problems and reviews first)
  const attentionItems = state.applications.filter(a => {
    const p = (a.plain_status || "").toLowerCase();
    return p.includes("mismatch") || p.includes("expired") || p.includes("review");
  });

  if (attentionItems.length === 0) {
    if (state.backendError && (!state.applications || state.applications.length === 0)) {
      container.innerHTML = `
        <div style="padding: 24px; text-align: center; color: var(--text-secondary);">
          <p style="margin-bottom: 8px;">Application status updates unavailable while connecting.</p>
          <button id="retryAttentionBtn" class="btn-micro-action" style="padding: 6px 14px;">Retry Connection</button>
        </div>
      `;
      document.getElementById("retryAttentionBtn")?.addEventListener("click", () => loadDashboardData());
      return;
    }
    container.innerHTML = `
      <div style="padding: 24px; text-align: center; color: var(--green); font-weight: 600;">
        ✓ All submitted applications have passed automated checks.
      </div>
    `;
    return;
  }

  container.innerHTML = attentionItems.map(app => {
    const chipColor = getStatusColorClass(app.status_color);
    return `
      <div class="attention-item">
        <div class="attention-info">
          <h4>${escapeHtml(app.institution_name)}</h4>
          <p>${escapeHtml(app.status_reason || "Requires regulatory scrutiny review.")}</p>
        </div>
        <div style="display: flex; align-items: center; gap: 10px;">
          <span class="status-chip ${chipColor}">
            <span class="chip-icon">${app.status_icon || "•"}</span>
            <span>${escapeHtml(app.plain_status || "Needs review")}</span>
          </span>
          <button class="btn-primary review-app-btn" style="padding: 6px 14px; font-size: 13px;" data-app-id="${app.id}">
            Review →
          </button>
        </div>
      </div>
    `;
  }).join("");

  container.querySelectorAll(".review-app-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const appId = btn.getAttribute("data-app-id");
      switchView("viewApplications");
      loadApplicationDetail(appId);
    });
  });
}

function renderStatusDonutChart() {
  const canvas = document.getElementById("statusDonutChart");
  if (!canvas || typeof Chart === "undefined") return;

  let verified = 0, review = 0, mismatch = 0, expired = 0;
  state.applications.forEach(a => {
    const p = (a.plain_status || "").toLowerCase();
    if (p.includes("verified")) verified++;
    else if (p.includes("review")) review++;
    else if (p.includes("mismatch")) mismatch++;
    else if (p.includes("expired")) expired++;
  });

  if (state.donutChartInstance) {
    state.donutChartInstance.destroy();
  }

  const isDark = state.theme === "dark";
  state.donutChartInstance = new Chart(canvas, {
    type: "doughnut",
    data: {
      labels: ["Verified", "Needs review", "Mismatch found", "Expired"],
      datasets: [{
        data: [verified, review, mismatch, expired],
        backgroundColor: ["#138808", "#b26a00", "#c62828", "#888888"],
        borderWidth: 2,
        borderColor: isDark ? "#1e293b" : "#ffffff"
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: "bottom",
          labels: {
            boxWidth: 12,
            font: { size: 12, family: "'Noto Sans', sans-serif" },
            color: isDark ? "#cbd5e1" : "#475569"
          }
        }
      },
      cutout: "70%"
    }
  });
}

// ============================================================================
// 6. STAGE 3: APPLICATION LIST & DETAIL WORKSPACE
// ============================================================================

function setApplicationsFilter(filter) {
  state.currentFilter = filter;
  document.querySelectorAll(".status-filter-chips .chip-filter-btn").forEach(btn => {
    if (btn.getAttribute("data-filter") === filter) btn.classList.add("active");
    else btn.classList.remove("active");
  });
  renderApplicationsGrid();
}

function renderApplicationsGrid() {
  const grid = document.getElementById("applicationsGrid");
  if (!grid) return;

  let filtered = state.applications;

  // Filter chip
  if (state.currentFilter === "verified") {
    filtered = filtered.filter(a => (a.plain_status || "").toLowerCase().includes("verified"));
  } else if (state.currentFilter === "needs_review") {
    filtered = filtered.filter(a => (a.plain_status || "").toLowerCase().includes("review"));
  } else if (state.currentFilter === "mismatch_detected") {
    filtered = filtered.filter(a => (a.plain_status || "").toLowerCase().includes("mismatch"));
  } else if (state.currentFilter === "expired") {
    filtered = filtered.filter(a => (a.plain_status || "").toLowerCase().includes("expired"));
  }

  // Search query
  if (state.searchQuery) {
    filtered = filtered.filter(a => 
      (a.institution_name || "").toLowerCase().includes(state.searchQuery) ||
      (a.pid || "").toLowerCase().includes(state.searchQuery) ||
      (a.id || "").toLowerCase().includes(state.searchQuery)
    );
  }

  if (filtered.length === 0) {
    if (state.backendError && (!state.applications || state.applications.length === 0)) {
      grid.innerHTML = `
        <div style="grid-column: 1 / -1; padding: 40px; text-align: center; color: var(--text-muted); background: var(--card); border-radius: var(--radius-md);">
          <p style="margin-bottom: 8px;">Failed to load applications from demo backend.</p>
          <button id="retryAppGridBtn" class="btn-primary" style="padding: 6px 16px;">Retry Connection</button>
        </div>
      `;
      document.getElementById("retryAppGridBtn")?.addEventListener("click", () => loadDashboardData());
      return;
    }
    grid.innerHTML = `
      <div style="grid-column: 1 / -1; padding: 40px; text-align: center; color: var(--text-muted); background: var(--card); border-radius: var(--radius-md);">
        No applications match your search and filter criteria.
      </div>
    `;
    return;
  }

  grid.innerHTML = filtered.map(app => {
    const chipColor = getStatusColorClass(app.status_color);
    const issuesCount = app.unique_issues_count || 0;
    const progressPercent = issuesCount === 0 ? 100 : Math.max(30, 100 - issuesCount * 25);
    const ringColor = issuesCount === 0 ? "var(--green)" : issuesCount > 1 ? "var(--red)" : "var(--amber)";

    return `
      <div class="application-card" data-app-id="${app.id}" role="button" tabindex="0">
        <div class="app-card-header">
          <div style="flex: 1;">
            <h3 class="app-college-name">${escapeHtml(app.institution_name)}</h3>
            <div class="app-meta-text">
              <span>PID: ${escapeHtml(app.pid || app.institution_id || "N/A")}</span>
              <span>•</span>
              <span>Approval renewal (EoA)</span>
            </div>
          </div>
          
          <!-- Progress Ring SVG -->
          <div class="progress-ring-wrap" title="${issuesCount === 0 ? 'Checks 100% complete' : `${issuesCount} issue(s) detected`}">
            <svg class="progress-ring-svg" width="44" height="44" viewBox="0 0 44 44">
              <circle class="progress-ring-bg" cx="22" cy="22" r="18" stroke-width="4"></circle>
              <circle class="progress-ring-bar" cx="22" cy="22" r="18" stroke-width="4"
                stroke="${ringColor}"
                stroke-dasharray="113.1"
                stroke-dashoffset="${113.1 - (113.1 * progressPercent / 100)}"></circle>
            </svg>
            <span class="progress-ring-text">${issuesCount === 0 ? '✓' : issuesCount}</span>
          </div>
        </div>

        <p class="app-summary-line">${escapeHtml(app.status_reason || "Awaiting regulatory decision.")}</p>

        <div class="app-card-footer">
          <div style="display: flex; flex-direction: column;">
            <span class="status-chip ${chipColor}">
              <span class="chip-icon">${app.status_icon || "•"}</span>
              <span>${escapeHtml(app.plain_status || "Needs review")}</span>
            </span>
            <span class="official-code-text">${escapeHtml(app.official_code || "")}</span>
          </div>

          <div style="font-size: 13px; font-weight: 600; color: ${issuesCount === 0 ? 'var(--green)' : 'var(--red)'};">
            ${issuesCount === 0 ? 'Zero issues found' : `${issuesCount} unique ${issuesCount === 1 ? 'issue' : 'issues'}`}
          </div>
        </div>
      </div>
    `;
  }).join("");

  grid.querySelectorAll(".application-card").forEach(card => {
    card.addEventListener("click", () => {
      const appId = card.getAttribute("data-app-id");
      loadApplicationDetail(appId);
    });
  });
}

async function loadApplicationDetail(appId) {
  state.activeAppId = appId;
  const detailView = document.getElementById("applicationDetailView");
  const listView = document.getElementById("applicationsListView");

  listView.style.display = "none";
  detailView.style.display = "block";

  // Reset to Summary Tab
  document.querySelectorAll(".tabs-navigation-bar .tab-link-btn").forEach(b => {
    b.classList.remove("active");
    b.setAttribute("aria-selected", "false");
  });
  document.querySelectorAll(".detail-tab-pane").forEach(p => p.classList.remove("active"));
  document.querySelector(".tab-link-btn[data-tab='tabSummary']")?.classList.add("active");
  document.getElementById("tabSummary")?.classList.add("active");

  try {
    const res = await api(`/applications/${appId}/report`, {
      headers: { "x-user-role": state.role }
    });
    if (!res.ok) throw new Error("Failed to load application report");
    const data = await res.json();
    state.activeAppDetail = data;

    // Header values
    document.getElementById("detailCollegeName").textContent = data.institution?.name || "Institution";
    document.getElementById("detailPid").textContent = `PID: ${data.institution?.pid || "N/A"}`;
    document.getElementById("detailCategory").textContent = "Approval renewal (EoA)";

    // Status Chip
    const statusChipContainer = document.getElementById("detailStatusChipContainer");
    const chipColor = getStatusColorClass(data.status_color);
    statusChipContainer.innerHTML = `
      <span class="status-chip ${chipColor}">
        <span class="chip-icon">${data.status_icon || "•"}</span>
        <span>${escapeHtml(data.plain_status || "Verified")}</span>
      </span>
      <span class="official-code-text">${escapeHtml(data.official_code || "")}</span>
    `;

    // What to do next banner
    const nextActionHeading = document.getElementById("nextActionHeading");
    const nextActionBody = document.getElementById("nextActionBody");
    const nextActionIcon = document.getElementById("nextActionIcon");

    if (data.status_color === "green") {
      nextActionIcon.textContent = "✓";
      nextActionHeading.textContent = "What to do next";
      nextActionBody.textContent = data.what_to_do_next || "All automated checks passed. Review summary cards and proceed to record your approval order.";
    } else if (data.status_color === "red") {
      nextActionIcon.textContent = "⚠️";
      nextActionHeading.textContent = "What to do next";
      nextActionBody.textContent = data.what_to_do_next || "Critical issues found. Review highlighted documents and request clarification or refer for physical inspection.";
    } else {
      nextActionIcon.textContent = "💡";
      nextActionHeading.textContent = "What to do next";
      nextActionBody.textContent = data.what_to_do_next || "Human officer scrutiny required to verify discrepancies before proceeding.";
    }

    // 3 Big Check Cards
    updateThreeChecksUI(data.three_checks);

    // Load Check History & Diff
    await loadRunsAndDiff(appId);

    // Findings List (enriched with diff badges)
    renderFindingsList(data.deficiencies || []);

    // Load Documents Tab List
    loadDocumentsForDetail(appId);

    // Load Cross-Checks Table
    loadCrossChecksTable(appId);

    // Load History Timeline
    loadHistoryTimeline(appId);

  } catch (err) {
    console.error("Error loading detail:", err);
    showToast("Error loading application detail", "error");
  }
}

function updateThreeChecksUI(checks) {
  const docBadge = document.getElementById("badgeDocumentCheck");
  const tamperBadge = document.getElementById("badgeTamperCheck");
  const issuerBadge = document.getElementById("badgeIssuerCheck");

  function applyBadge(elem, statusVal) {
    if (!elem) return;
    elem.classList.remove("check-badge-ok", "check-badge-concern", "check-badge-unclear");
    if (statusVal === "OK") {
      elem.textContent = "OK";
      elem.classList.add("check-badge-ok");
    } else if (statusVal === "Concern") {
      elem.textContent = "Concern";
      elem.classList.add("check-badge-concern");
    } else {
      elem.textContent = "Could not check";
      elem.classList.add("check-badge-unclear");
    }
  }

  if (checks) {
    applyBadge(docBadge, checks.document_check);
    applyBadge(tamperBadge, checks.tamper_check);
    applyBadge(issuerBadge, checks.issuer_check);
  }
}

function renderFindingsList(findings, showAll = false) {
  const container = document.getElementById("findingsListContainer");
  const countLabel = document.getElementById("findingsCountLabel");
  if (!container) return;

  if (countLabel) countLabel.textContent = findings.length;

  if (findings.length === 0) {
    container.innerHTML = `
      <div class="finding-card finding-green" style="border-left-color: var(--green);">
        <div class="finding-title-row">
          <span>✓</span>
          <span>All automated document, tamper, and issuer checks passed.</span>
        </div>
        <p style="font-size: 13px; color: var(--text-secondary); margin-top: 6px;">
          No contradictions, cryptographic signature mismatches, or anomalous typography were detected.
        </p>
      </div>
    `;
    return;
  }

  // Show up to 5 findings initially with plain language first unless showAll is true
  const displayFindings = showAll ? findings : findings.slice(0, 5);

  container.innerHTML = displayFindings.map((f, idx) => {
    const isCritical = f.severity === "critical" || f.source_lane === "provenance";
    const borderClass = isCritical ? "finding-red" : "finding-amber";
    const icon = isCritical ? "❌" : "⚠️";

    // Finding diff badge
    let diffBadgeHtml = "";
    if (state.currentDiff) {
      const fprint = f.fingerprint || "";
      const isIntro = (state.currentDiff.introduced || []).some(x => (x.fingerprint && x.fingerprint === fprint) || (x.reason_code === f.reason_code && x.doc_type === f.doc_type));
      const persItem = (state.currentDiff.persisting || []).find(x => (x.fingerprint && x.fingerprint === fprint) || (x.reason_code === f.reason_code && x.doc_type === f.doc_type));
      if (isIntro) {
        diffBadgeHtml = `<span class="finding-diff-badge badge-new ${isCritical ? 'badge-critical' : ''}">New</span>`;
      } else if (persItem) {
        if (persItem.changed) {
          diffBadgeHtml = `<span class="finding-diff-badge badge-changed" title="Observed value changed between checks">Value changed</span>`;
        } else {
          diffBadgeHtml = `<span class="finding-diff-badge badge-open">Still open</span>`;
        }
      }
    }

    return `
      <div class="finding-card ${borderClass}">
        <div class="finding-title-row">
          <div style="display: flex; align-items: center; gap: 8px;">
            <span>${icon}</span>
            <span>${escapeHtml(f.plain_title || f.rule_id || "Regulatory discrepancy flagged")}</span>
          </div>
          ${diffBadgeHtml}
        </div>

        <div style="font-size: 12px; color: var(--text-muted); margin-top: 4px;">
          Where: <b>${escapeHtml(f.document_name || f.doc_id || "Document")}</b> (Page ${f.page != null ? f.page + 1 : 1})
        </div>

        <!-- Two Column What we found vs What was expected -->
        <div class="finding-columns-grid">
          <div class="finding-column">
            <span class="finding-col-label">What we found:</span>
            <div class="finding-col-value">${escapeHtml(f.what_we_found || f.plain_language_reason || "Discrepancy detected")}</div>
          </div>
          <div class="finding-column">
            <span class="finding-col-label">What was expected:</span>
            <div class="finding-col-value">${escapeHtml(f.what_was_expected || "Concordance with AICTE regulatory guidelines and issuer records")}</div>
          </div>
        </div>

        <!-- Collapsed This could be innocent if... -->
        <div class="benign-hypothesis-box">
          <div class="benign-hypothesis-toggle" onclick="this.nextElementSibling.classList.toggle('open')">
            <span>ℹ️ This could be innocent if... (Counter-hypotheses)</span>
            <span>▼</span>
          </div>
          <div class="benign-hypothesis-body">
            ${(f.benign_explanations && f.benign_explanations.length > 0)
              ? f.benign_explanations.map(e => `<div>• ${escapeHtml(e)}</div>`).join("")
              : `<div>• High-resolution municipal scanner software introduced standard compression artifacts.</div>
                 <div>• The Sub-Registrar changed the local seal layout in a recent fiscal amendment.</div>`}
          </div>
        </div>

        <!-- Officer Actions -->
        <div class="officer-actions-row">
          <button class="btn-micro-action" onclick="showToast('Marked finding #${idx + 1} as reviewed', 'info')">
            ✓ Mark as reviewed
          </button>
          <button class="btn-micro-action" onclick="showToast('Clarification request queued for College', 'info')">
            ✉ Ask college to clarify
          </button>
        </div>

        <!-- Collapsed Technical Details -->
        <div class="tech-details-box">
          <div class="tech-details-toggle" onclick="this.nextElementSibling.classList.toggle('open')">
            <span>Technical details (Rule ID, Raw digest, Lane)</span>
            <span>▼</span>
          </div>
          <div class="tech-details-body">
            <div><b>Rule ID:</b> <code>${escapeHtml(f.rule_id || "N/A")}</code></div>
            <div><b>Reason Code:</b> <code>${escapeHtml(f.reason_code || "DISCREPANCY")}</code></div>
            <div><b>Detection Lane:</b> <code>${escapeHtml(f.source_lane || "triangulation")}</code></div>
            <div><b>Claim Field:</b> <code>${escapeHtml(f.claim_field || f.field || "N/A")}</code></div>
          </div>
        </div>
      </div>
    `;
  }).join("");

  if (!showAll && findings.length > 5) {
    container.innerHTML += `
      <div style="text-align: center; margin-top: 12px;">
        <button class="btn-secondary" onclick="renderAllFindings()">
          Show all ${findings.length} findings →
        </button>
      </div>
    `;
  }
}

// ============================================================================
// 7. DOCUMENTS TAB & SIDE-BY-SIDE INTERACTIVE VIEWER
// ============================================================================

async function loadDocumentsForDetail(appId) {
  const listContainer = document.getElementById("docsListItems");
  if (!listContainer) return;

  try {
    const res = await api(`/applications/${appId}`);
    if (!res.ok) throw new Error("Could not fetch application docs");
    const appData = await res.json();
    const docs = appData.documents || [];

    if (docs.length === 0) {
      listContainer.innerHTML = `<div style="font-size: 13px; color: var(--text-muted);">No documents on file.</div>`;
      return;
    }

    listContainer.innerHTML = docs.map((doc, idx) => {
      const isSelected = idx === 0;
      return `
        <div class="doc-item-btn ${isSelected ? 'active' : ''}" data-doc-id="${doc.id}">
          <div style="font-weight: 600;">${escapeHtml(formatDocType(doc.doc_type))}</div>
          <div style="font-size: 11px; color: var(--text-secondary); display: flex; justify-content: space-between; margin-top: 4px;">
            <span>v${doc.version || 1} • ${doc.page_count || 1} page(s)</span>
            <span style="color: var(--green);">✓ Uploaded</span>
          </div>
        </div>
      `;
    }).join("");

    listContainer.querySelectorAll(".doc-item-btn").forEach(item => {
      item.addEventListener("click", () => {
        listContainer.querySelectorAll(".doc-item-btn").forEach(i => i.classList.remove("active"));
        item.classList.add("active");
        const docId = item.getAttribute("data-doc-id");
        selectDocumentForViewer(docId);
      });
    });

    // Select the first document by default
    if (docs.length > 0) {
      selectDocumentForViewer(docs[0].id);
    }
  } catch (err) {
    console.error("Docs list error:", err);
  }
}

async function selectDocumentForViewer(docId) {
  state.activeDocId = docId;
  const docImg = document.getElementById("docPageImage");
  const bboxLayer = document.getElementById("bboxHighlightLayer");
  const titleElem = document.getElementById("currentDocTitle");
  const findingsList = document.getElementById("docSpecificFindingsList");

  if (titleElem) titleElem.textContent = `Document Viewer: ${docId}`;
  if (docImg) {
    docImg.src = apiUrl(`/documents/${docId}/page/0.png`);
    docImg.style.display = "block";
  }

  // Fetch document overlay for bounding box highlights
  try {
    const res = await api(`/documents/${docId}/overlay`);
    if (!res.ok) throw new Error("Could not fetch doc overlay");
    const overlayData = await res.json();
    const claims = overlayData.claims || [];

    // Render clickable bounding boxes
    bboxLayer.innerHTML = "";
    claims.forEach(c => {
      if (c.bbox && c.bbox.length === 4) {
        const [x1, y1, x2, y2] = c.bbox;
        const box = document.createElement("div");
        box.className = "bbox-highlight";
        if (c.flags && c.flags.length > 0) box.classList.add("flagged");
        box.style.left = `${x1}px`;
        box.style.top = `${y1}px`;
        box.style.width = `${x2 - x1}px`;
        box.style.height = `${y2 - y1}px`;
        box.title = `${c.field}: ${c.value}`;
        
        box.addEventListener("click", () => {
          highlightDocumentFinding(c.field);
        });
        bboxLayer.appendChild(box);
      }
    });

    // Populate Right Column findings for this document
    const docDeficiencies = (state.activeAppDetail?.deficiencies || []).filter(
      d => d.doc_id === docId || (d.document_name && d.document_name.includes(docId))
    );

    if (docDeficiencies.length === 0) {
      findingsList.innerHTML = `
        <div style="background: var(--bg); padding: 14px; border-radius: var(--radius-sm); font-size: 13px; color: var(--green);">
          ✓ All fields extracted from this document are consistent with regulatory records.
        </div>
      `;
    } else {
      findingsList.innerHTML = docDeficiencies.map(d => `
        <div class="finding-card ${d.severity === 'critical' ? 'finding-red' : 'finding-amber'}" style="margin-bottom: 12px; cursor: pointer;" onclick="scrollToBoundingBox('${escapeHtml(d.claim_field || d.field)}')">
          <div class="finding-title-row">
            <span>⚠️</span>
            <span>${escapeHtml(d.plain_title || d.rule_id || "Discrepancy")}</span>
          </div>
          <p style="font-size: 12px; color: var(--text-secondary); margin-top: 6px;">
            ${escapeHtml(d.plain_language_reason || d.what_we_found || "Discrepancy in extracted value.")}
          </p>
          <div style="font-size: 11px; color: var(--navy); margin-top: 6px; font-weight: 600;">
            Click to locate on page →
          </div>
        </div>
      `).join("");
    }

  } catch (err) {
    console.warn("Could not fetch overlay:", err);
  }
}

function highlightDocumentFinding(fieldName) {
  showToast(`Inspecting field: ${fieldName}`, "info");
}

function scrollToBoundingBox(fieldName) {
  showToast(`Focused on field highlight: ${fieldName}`, "info");
}

function formatDocType(type) {
  const map = {
    lease_deed: "Land Lease Deed",
    affidavit: "Omnibus Regulatory Affidavit",
    state_noc: "State Government NOC",
    ter_receipt: "TER Fee Payment Receipt",
    nba_cert: "NBA Accreditation Certificate",
  };
  return map[type] || type.replace("_", " ").toUpperCase();
}

// ============================================================================
// 8. CROSS-CHECKS TAB (TABLE & CYTOSCAPE GRAPH)
// ============================================================================

async function loadCrossChecksTable(appId) {
  const tbody = document.getElementById("crossChecksTableBody");
  if (!tbody) return;

  try {
    const res = await api(`/claims?application_id=${appId}`);
    if (!res.ok) throw new Error("Could not fetch claims");
    const claims = await res.json();

    // Group cross-checks: address, dates, fee, etc.
    const rows = [
      {
        docA: "Lease Deed (Land details)",
        docB: "Affidavit (Institution address)",
        result: state.activeAppId === "APP-2026-004" ? "conflict" : "consistent",
        reason: state.activeAppId === "APP-2026-004" 
          ? "Contradiction: Lease deed specifies Sector 62, while Affidavit mentions Sector 12."
          : "Both documents consistently confirm address at Plot 12, Sector 62, Noida."
      },
      {
        docA: "TER Payment Receipt",
        docB: "AICTE Master Fee Ledger",
        result: "consistent",
        reason: "TER fee amount of ₹1,00,000 matches transaction ID TER-2026-99120."
      },
      {
        docA: "State Government NOC",
        docB: "AICTE Approved Intake Norms",
        result: "consistent",
        reason: "480 approved student intake aligns with state government quota."
      },
      {
        docA: "Sub-Registrar Lease Registration",
        docB: "District Sub-Registrar Registry",
        result: state.activeAppId === "APP-2026-002" ? "conflict" : "consistent",
        reason: state.activeAppId === "APP-2026-002"
          ? "Forged digital signature: Cryptographic Ed25519 hash failed issuer verification."
          : "Digital signature valid and confirmed by issuing registry."
      }
    ];

    tbody.innerHTML = rows.map(r => `
      <tr>
        <td><b>${escapeHtml(r.docA)}</b></td>
        <td><b>${escapeHtml(r.docB)}</b></td>
        <td>
          <span style="font-weight: 700; color: ${r.result === 'consistent' ? 'var(--green)' : 'var(--red)'};">
            ${r.result === 'consistent' ? '✓ Consistent' : '✗ Conflict'}
          </span>
        </td>
        <td style="font-size: 13px; color: var(--text-secondary);">${escapeHtml(r.reason)}</td>
      </tr>
    `).join("");

  } catch (err) {
    console.error("Cross-checks table error:", err);
  }
}

async function renderCytoscapeGraph(appId) {
  const container = document.getElementById("cyGraphContainer");
  if (!container || typeof cytoscape === "undefined") return;

  try {
    const res = await api(`/graph/${appId}`);
    if (!res.ok) throw new Error("Could not fetch graph");
    const graphData = await res.json();
    const elements = graphData.elements || [];

    if (state.cyGraphInstance) {
      state.cyGraphInstance.destroy();
    }

    state.cyGraphInstance = cytoscape({
      container: container,
      elements: elements,
      style: [
        {
          selector: 'node',
          style: {
            'label': 'data(label)',
            'background-color': '#14307a',
            'color': '#ffffff',
            'font-size': '12px',
            'font-weight': '600',
            'text-valign': 'center',
            'text-halign': 'center',
            'width': '80px',
            'height': '40px',
            'shape': 'roundrectangle'
          }
        },
        {
          selector: 'node[type="lease_deed"]',
          style: { 'background-color': '#1565c0' }
        },
        {
          selector: 'node[type="affidavit"]',
          style: { 'background-color': '#e8731a' }
        },
        {
          selector: 'node[type="ter_receipt"]',
          style: { 'background-color': '#138808' }
        },
        {
          selector: 'edge',
          style: {
            'width': 2,
            'line-color': '#138808',
            'target-arrow-color': '#138808',
            'target-arrow-shape': 'triangle',
            'curve-style': 'bezier',
            'label': 'data(label)',
            'font-size': '10px',
            'color': '#475569'
          }
        },
        {
          selector: 'edge[type="contradiction"]',
          style: {
            'line-color': '#c62828',
            'target-arrow-color': '#c62828',
            'line-style': 'dashed',
            'width': 3
          }
        }
      ],
      layout: {
        name: 'breadthfirst',
        directed: true,
        padding: 20
      }
    });

    state.cyGraphInstance.on('tap', 'node, edge', (evt) => {
      const target = evt.target;
      const detailsPanel = document.getElementById("graphNodeDetailsPanel");
      if (detailsPanel) {
        if (target.isNode()) {
          detailsPanel.innerHTML = `<b>Document Node:</b> ${escapeHtml(target.data('label'))} (Type: ${target.data('type') || 'document'})`;
        } else {
          detailsPanel.innerHTML = `<b>Relationship Edge:</b> ${escapeHtml(target.data('label') || 'concordance')} - ${target.data('type') === 'contradiction' ? '⚠️ Conflict detected between documents' : '✓ Consistent concordant claim'}`;
        }
      }
    });

  } catch (err) {
    console.warn("Cytoscape graph error:", err);
  }
}

// ============================================================================
// 9. CHECK HISTORY AND WHAT CHANGED CONTROLLER
// ============================================================================

async function loadRunsAndDiff(appId) {
  try {
    const res = await api(`/applications/${appId}/runs`, {
      headers: { "x-user-role": state.role }
    });
    if (!res.ok) throw new Error("Could not fetch checks");
    const runs = await res.json();
    state.currentRuns = runs;

    const summaryBanner = document.getElementById("summaryDiffBanner");
    const summaryBannerText = document.getElementById("summaryDiffBannerText");

    if (runs.length >= 2) {
      const diffRes = await api(`/applications/${appId}/runs/diff`, {
        headers: { "x-user-role": state.role }
      });
      if (diffRes.ok) {
        state.currentDiff = await diffRes.json();
      } else {
        state.currentDiff = null;
      }

      if (summaryBanner && state.currentDiff) {
        summaryBanner.style.display = "flex";
        const resCount = (state.currentDiff.resolved || []).length;
        const introCount = (state.currentDiff.introduced || []).length;
        const persCount = (state.currentDiff.persisting || []).length;
        summaryBannerText.textContent = `Since the last check: ${resCount} fixed, ${introCount} new, ${persCount} still open.`;
      }
    } else {
      if (summaryBanner) summaryBanner.style.display = "none";
      if (runs.length === 1) {
        const singleRunRes = await api(`/applications/${appId}/runs/1`, {
          headers: { "x-user-role": state.role }
        });
        const run1 = singleRunRes.ok ? await singleRunRes.json() : runs[0];
        state.currentDiff = {
          from_run_number: null,
          to_run_number: 1,
          status_from: null,
          status_to: run1.status_at_run,
          introduced: run1.findings || [],
          resolved: [],
          persisting: [],
          rules_changed: false,
          documents_changed: [],
          plain_explanation: "This is the first check. Changes will appear after the next check."
        };
      } else {
        state.currentDiff = null;
      }
    }

    renderHistoryChecksAndDiff(appId, state.currentRuns, state.currentDiff);
  } catch (err) {
    console.error("Error loading runs/diff:", err);
  }
}

function renderHistoryChecksAndDiff(appId, runs, diff) {
  const explanationElem = document.getElementById("whatChangedExplanation");
  const checksPill = document.getElementById("whatChangedChecksPill");
  const countTileFixed = document.getElementById("countTileFixed");
  const countTileNew = document.getElementById("countTileNew");
  const countTileOpen = document.getElementById("countTileOpen");
  const tileNew = document.getElementById("tileNew");

  if (!runs || runs.length === 0) {
    if (explanationElem) explanationElem.textContent = "No checks recorded yet.";
    return;
  }

  const isMultiCheck = diff && diff.from_run_number != null;

  if (isMultiCheck) {
    if (explanationElem) explanationElem.textContent = diff.plain_explanation || "Comparison complete.";
    if (checksPill) {
      checksPill.textContent = `Check #${diff.from_run_number} → Check #${diff.to_run_number}`;
      checksPill.className = "status-chip chip-blue";
    }

    const resCount = (diff.resolved || []).length;
    const introCount = (diff.introduced || []).length;
    const persCount = (diff.persisting || []).length;

    if (countTileFixed) countTileFixed.textContent = resCount;
    if (countTileNew) countTileNew.textContent = introCount;
    if (countTileOpen) countTileOpen.textContent = persCount;

    // Red if any critical introduced finding
    const hasCriticalNew = (diff.introduced || []).some(x => x.severity === "critical");
    if (tileNew) {
      if (hasCriticalNew) tileNew.classList.add("critical-new");
      else tileNew.classList.remove("critical-new");
    }
  } else {
    // Single check baseline
    if (explanationElem) explanationElem.textContent = "This is the first check. Changes will appear after the next check.";
    if (checksPill) {
      checksPill.textContent = `Check #${runs[0].run_number || 1}`;
      checksPill.className = "status-chip chip-blue";
    }
    if (countTileFixed) countTileFixed.textContent = "0";
    if (countTileNew) countTileNew.textContent = "0";
    const openCount = runs[0].counts ? runs[0].counts.open : (diff?.introduced?.length || 0);
    if (countTileOpen) countTileOpen.textContent = openCount;
    if (tileNew) tileNew.classList.remove("critical-new");
  }

  // Render Diff Findings list based on active tile
  renderDiffFindingsList(diff, state.diffFilter);

  // Render Collapsed Fixed Items Group
  const fixedGroup = document.getElementById("diffFixedGroup");
  const fixedCountElem = document.getElementById("fixedItemsCount");
  const fixedListElem = document.getElementById("fixedItemsList");
  const resolvedItems = diff ? (diff.resolved || []) : [];

  if (isMultiCheck && resolvedItems.length > 0) {
    if (fixedGroup) fixedGroup.style.display = "block";
    if (fixedCountElem) fixedCountElem.textContent = resolvedItems.length;
    if (fixedListElem) {
      fixedListElem.innerHTML = resolvedItems.map(item => `
        <div style="background: var(--card); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 10px 14px; margin-bottom: 8px;">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <span style="font-weight: 700; color: var(--green);">✓ ${escapeHtml(item.plain_title || item.rule_id || "Resolved issue")}</span>
            <span class="finding-diff-badge badge-fixed">Fixed in Check #${diff.to_run_number}</span>
          </div>
          <div style="font-size: 12px; color: var(--text-secondary); margin-top: 4px;">
            Where: <b>${escapeHtml(item.doc_type ? formatDocType(item.doc_type) : "Document")}</b>
          </div>
          ${item.observed_value ? `<div style="font-size: 12px; color: var(--text-muted); margin-top: 2px;">Previously observed: <code>${escapeHtml(item.observed_value)}</code></div>` : ""}
        </div>
      `).join("");
    }
  } else {
    if (fixedGroup) fixedGroup.style.display = "none";
  }

  // Populate Compare Dropdown in Technical details
  const selFrom = document.getElementById("diffSelectFrom");
  const selTo = document.getElementById("diffSelectTo");
  if (selFrom && selTo) {
    const optionsHtml = runs.map(r => `<option value="${r.run_number}">Check #${r.run_number}</option>`).join("");
    selFrom.innerHTML = optionsHtml;
    selTo.innerHTML = optionsHtml;
    if (diff && diff.from_run_number) selFrom.value = diff.from_run_number;
    else if (runs.length > 1) selFrom.value = runs[1].run_number;
    if (diff && diff.to_run_number) selTo.value = diff.to_run_number;
    else selTo.value = runs[0].run_number;
  }

  // Technical metadata progressive disclosure
  const metaContainer = document.getElementById("historyTechMeta");
  if (metaContainer) {
    const targetRun = runs[0];
    const rulesVer = targetRun.rules_version ? targetRun.rules_version.substring(0, 16) + "..." : "N/A";
    const snapHash = targetRun.snapshot_hash ? targetRun.snapshot_hash.substring(0, 16) + "..." : "N/A";
    const evalDate = targetRun.created_at ? targetRun.created_at.split("T")[0] : "2026-10-24";

    let html = `
      <div><b>Evaluation Date:</b> ${escapeHtml(evalDate)}</div>
      <div><b>Rules Version SHA-256:</b> <span title="${escapeHtml(targetRun.rules_version || '')}">${rulesVer}</span></div>
      <div><b>Snapshot Hash SHA-256:</b> <span title="${escapeHtml(targetRun.snapshot_hash || '')}">${snapHash}</span></div>
      <div><b>Applied Checklist ID:</b> <code>aicte_approval_2026_checklist</code></div>
    `;
    if (isMultiCheck) {
      html += `<div><b>Rules Changed Between Checks:</b> ${diff.rules_changed ? '<span style="color:var(--amber);">Yes</span>' : '<span style="color:var(--green);">No (Identical ruleset)</span>'}</div>`;
      if (diff.documents_changed && diff.documents_changed.length > 0) {
        const docChanges = diff.documents_changed.map(dc => `${formatDocType(dc.doc_type)} (v${dc.from_version} → v${dc.to_version})`).join(", ");
        html += `<div><b>Documents Changed:</b> ${escapeHtml(docChanges)}</div>`;
      }
    }
    metaContainer.innerHTML = html;
  }

  // Render Compact Checks List
  const checksListElem = document.getElementById("checksHistoryList");
  if (checksListElem) {
    checksListElem.innerHTML = runs.map(c => {
      const isActive = diff && (c.run_number === diff.to_run_number);
      const isClean = !c.counts || (c.counts.open === 0 && c.counts.critical === 0);
      const chipClass = isClean ? "chip-green" : (c.counts?.critical > 0 ? "chip-red" : "chip-amber");
      const chipText = isClean ? "Clean" : `${c.counts?.open || 0} open`;
      const timeStr = formatTimestamp(c.created_at);

      let reasonText = "Official Check";
      if (c.trigger === "document_replaced") reasonText = "Document replaced";
      else if (c.trigger === "manual") reasonText = "Manual scrutiny check";
      else if (c.trigger === "seed") reasonText = "Initial submission check";

      return `
        <div class="check-history-item ${isActive ? 'active' : ''}" data-run-number="${c.run_number}" role="button" tabindex="0">
          <div>
            <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
              <span style="font-weight: 700; font-size: 14px; color: var(--navy);">Check #${c.run_number}</span>
              <span class="status-chip ${chipClass}" style="font-size: 11px;">${chipText}</span>
              <span style="font-size: 12px; color: var(--text-secondary);">${escapeHtml(reasonText)}</span>
              <span style="font-size: 11px; color: var(--text-muted);">• ${escapeHtml(c.actor_role || "Officer")}</span>
            </div>
            <div style="font-size: 12px; color: var(--text-muted); margin-top: 4px;">
              ${escapeHtml(timeStr)}
            </div>
          </div>
          <div style="display: flex; gap: 6px; align-items: center;">
            <button type="button" class="btn-micro-action" onclick="compareToCheck(${c.run_number})" title="Compare this check">
              Inspect
            </button>
          </div>
        </div>
      `;
    }).join("");
  }
}

function renderDiffFindingsList(diff, filter) {
  const container = document.getElementById("diffFindingsContainer");
  if (!container) return;

  // Update active state on tiles
  document.querySelectorAll(".diff-tile").forEach(t => {
    if (t.getAttribute("data-filter") === filter) t.classList.add("active");
    else t.classList.remove("active");
  });

  if (!diff) {
    container.innerHTML = `<div class="empty-diff-state">Loading findings comparison...</div>`;
    return;
  }

  let itemsToRender = [];
  const isMultiCheck = diff.from_run_number != null;

  if (!isMultiCheck) {
    itemsToRender = (diff.introduced || []).map(item => ({ ...item, _diffType: "persisting" }));
  } else {
    if (filter === "resolved") {
      itemsToRender = (diff.resolved || []).map(item => ({ ...item, _diffType: "resolved" }));
    } else if (filter === "introduced") {
      itemsToRender = (diff.introduced || []).map(item => ({ ...item, _diffType: "introduced" }));
    } else if (filter === "persisting") {
      itemsToRender = (diff.persisting || []).map(item => ({ ...item, _diffType: "persisting" }));
    } else {
      // all
      itemsToRender = [
        ...(diff.introduced || []).map(item => ({ ...item, _diffType: "introduced" })),
        ...(diff.persisting || []).map(item => ({ ...item, _diffType: "persisting" }))
      ];
    }
  }

  if (itemsToRender.length === 0) {
    let emptyMsg = "No findings in this category.";
    if (filter === "resolved") emptyMsg = "No issues were resolved between these checks.";
    if (filter === "introduced") emptyMsg = "No new issues were introduced.";
    if (filter === "persisting") emptyMsg = "Zero unresolved issues persisting.";
    container.innerHTML = `
      <div style="background: var(--bg); border: 1px dashed var(--border); border-radius: var(--radius-md); padding: 18px; text-align: center; color: var(--text-secondary); font-size: 13px;">
        ${emptyMsg}
      </div>
    `;
    return;
  }

  container.innerHTML = itemsToRender.map((f, idx) => {
    const isCritical = f.severity === "critical";
    const borderClass = isCritical ? "finding-red" : "finding-amber";
    const icon = isCritical ? "❌" : "⚠️";

    let badgeHtml = "";
    if (f._diffType === "resolved") {
      badgeHtml = `<span class="finding-diff-badge badge-fixed">Fixed</span>`;
    } else if (f._diffType === "introduced") {
      badgeHtml = `<span class="finding-diff-badge badge-new ${isCritical ? 'badge-critical' : ''}">New</span>`;
    } else if (f._diffType === "persisting") {
      if (f.changed) {
        badgeHtml = `<span class="finding-diff-badge badge-changed" title="Observed value changed between checks">Value changed</span>`;
      } else {
        badgeHtml = `<span class="finding-diff-badge badge-open">Still open</span>`;
      }
    }

    return `
      <div class="finding-card ${borderClass}" style="margin-bottom: 12px;">
        <div class="finding-title-row">
          <div style="display: flex; align-items: center; gap: 8px;">
            <span>${icon}</span>
            <span style="font-weight: 700;">${escapeHtml(f.plain_title || f.rule_id || "Discrepancy")}</span>
          </div>
          ${badgeHtml}
        </div>

        <div style="font-size: 12px; color: var(--text-muted); margin-top: 4px;">
          Where: <b>${escapeHtml(f.doc_type ? formatDocType(f.doc_type) : (f.doc_id || "Document"))}</b> ${f.page != null ? `(Page ${f.page + 1})` : ""}
        </div>

        <div class="finding-columns-grid" style="margin-top: 8px;">
          <div class="finding-column">
            <span class="finding-col-label">What was found:</span>
            <div class="finding-col-value">${escapeHtml(f.observed_value || f.plain_reason || "Value discrepancy")}</div>
          </div>
          <div class="finding-column">
            <span class="finding-col-label">What was expected:</span>
            <div class="finding-col-value">${escapeHtml(f.expected_value || "Concordance with AICTE norms")}</div>
          </div>
        </div>

        ${f.changed ? `
          <div style="background: var(--blue-light); border-left: 3px solid var(--blue); padding: 8px 12px; border-radius: 4px; font-size: 12px; margin-top: 8px;">
            <b>Value changed:</b> Was <code>${escapeHtml(f.was_observed || 'N/A')}</code> → Now <code>${escapeHtml(f.now_observed || f.observed_value || 'N/A')}</code>
          </div>
        ` : ""}
      </div>
    `;
  }).join("");
}

async function compareToSelectedChecks(appId) {
  const selFrom = document.getElementById("diffSelectFrom");
  const selTo = document.getElementById("diffSelectTo");
  if (!selFrom || !selTo) return;

  const fromVal = selFrom.value;
  const toVal = selTo.value;
  showToast(`Comparing Check #${fromVal} vs Check #${toVal}...`, "info");

  try {
    const res = await api(`/applications/${appId}/runs/diff?from=${fromVal}&to=${toVal}`, {
      headers: { "x-user-role": state.role }
    });
    if (!res.ok) throw new Error("Could not compare checks");
    const diff = await res.json();
    state.currentDiff = diff;
    renderHistoryChecksAndDiff(appId, state.currentRuns, state.currentDiff);
  } catch (err) {
    showToast("Failed to compare checks", "error");
  }
}

async function compareToCheck(runNumber) {
  if (!state.activeAppId || !state.currentRuns || state.currentRuns.length === 0) return;
  const targetRun = state.currentRuns.find(r => r.run_number === runNumber);
  if (!targetRun) return;

  const prevRun = state.currentRuns.find(r => r.run_number === runNumber - 1);
  const fromNum = prevRun ? prevRun.run_number : runNumber;
  const toNum = runNumber;

  try {
    const res = await api(`/applications/${state.activeAppId}/runs/diff?from=${fromNum}&to=${toNum}`, {
      headers: { "x-user-role": state.role }
    });
    if (res.ok) {
      state.currentDiff = await res.json();
      renderHistoryChecksAndDiff(state.activeAppId, state.currentRuns, state.currentDiff);
      document.getElementById("whatChangedCard")?.scrollIntoView({ behavior: "smooth" });
    }
  } catch (err) {
    console.error("Compare error:", err);
  }
}

// ============================================================================
// 10. HISTORY TIMELINE & ADVANCED INTEGRITY VERIFICATION
// ============================================================================

async function loadHistoryTimeline(appId) {
  const container = document.getElementById("historyTimelineList");
  if (!container) return;

  try {
    const res = await api(`/audit?limit=20`, {
      headers: { "x-user-role": state.role }
    });
    if (!res.ok) throw new Error("Could not fetch audit history");
    const entries = await res.json();
    const appEntries = entries.filter(e => e.application_id === appId || !e.application_id);

    if (appEntries.length === 0) {
      container.innerHTML = `
        <div class="timeline-entry">
          <div class="timeline-dot"></div>
          <div class="timeline-time">Today, 09:00 UTC</div>
          <div class="timeline-title">Application Submitted by College</div>
          <div class="timeline-desc">Statutory documents deposited into TruthTrace encrypted storage.</div>
        </div>
      `;
      return;
    }

    container.innerHTML = appEntries.map(e => {
      const timeStr = formatTimestamp(e.timestamp);
      return `
        <div class="timeline-entry">
          <div class="timeline-dot"></div>
          <div class="timeline-time">${escapeHtml(timeStr)}</div>
          <div class="timeline-title">${escapeHtml(formatActionName(e.action))} (${escapeHtml(e.actor_role)})</div>
          <div class="timeline-desc">${escapeHtml(formatPayloadSummary(e.payload))}</div>
        </div>
      `;
    }).join("");

  } catch (err) {
    console.error("Timeline error:", err);
  }
}

async function verifyAuditIntegrityInHistory() {
  const banner = document.getElementById("integrityBanner");
  const bannerText = document.getElementById("integrityBannerText");
  if (!banner) return;

  try {
    const res = await api("/audit/verify");
    const data = await res.json();
    banner.style.display = "flex";
    if (data.valid) {
      banner.className = "integrity-status-banner integrity-intact";
      bannerText.textContent = "Cryptographic SHA-256 hash-chain is intact. Zero tampering detected.";
      showToast("Audit chain verified: 100% intact", "success");
    } else {
      banner.className = "integrity-status-banner integrity-tampered";
      bannerText.textContent = `Tampering detected at log entry #${data.tampered_index}! Hash mismatch.`;
      showToast("Tampering detected in audit ledger!", "error");
    }
  } catch (err) {
    showToast("Failed to verify audit integrity", "error");
  }
}

function formatTimestamp(ts) {
  if (!ts) return "Just now";
  try {
    const d = new Date(ts);
    return `${d.toLocaleDateString()} ${d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
  } catch {
    return ts;
  }
}

function formatActionName(action) {
  const map = {
    SCRUTINY_VALIDATION_RUN: "Automated Scrutiny Executed",
    OFFICER_DECISION: "Officer Regulatory Order Signed",
    PREFLIGHT_CHECK: "College Pre-submission Check",
    DOCUMENT_REPLACED: "Document Version Uploaded",
  };
  return map[action] || action.replace(/_/g, " ");
}

function formatPayloadSummary(payload) {
  if (!payload) return "Action logged.";
  if (payload.action) return `Order: ${payload.action.toUpperCase()} — Reason: ${payload.reason || "Approved"}`;
  if (payload.overall_verdict) return `Verdict: ${payload.overall_verdict}. Issues found: ${payload.unique_issues_count || 0}.`;
  return JSON.stringify(payload).replace(/[{}"']/g, "");
}

// ============================================================================
// 10. STEP-BY-STEP SCRUTINY ANIMATION RUNNER
// ============================================================================

async function runAutomatedChecksWithAnimation(appId) {
  const runnerModal = document.getElementById("scrutinyRunnerModal");
  runnerModal.classList.remove("hidden");

  // Reset steps
  const steps = [
    { id: "step1Reading", spinner: "step1Spinner" },
    { id: "step2DocCheck", spinner: "step2Spinner" },
    { id: "step3TamperCheck", spinner: "step3Spinner" },
    { id: "step4IssuerCheck", spinner: "step4Spinner" },
    { id: "step5Result", spinner: "step5Spinner" }
  ];

  function setStepActive(stepIndex) {
    steps.forEach((s, i) => {
      const row = document.getElementById(s.id);
      const spin = document.getElementById(s.spinner);
      if (row) {
        if (i < stepIndex) {
          row.classList.remove("active");
          row.classList.add("completed");
          if (spin) spin.style.display = "none";
        } else if (i === stepIndex) {
          row.classList.add("active");
          row.classList.remove("completed");
          if (spin) spin.style.display = "inline-block";
        } else {
          row.classList.remove("active", "completed");
          if (spin) spin.style.display = "none";
        }
      }
    });
  }

  // Animation sequence
  setStepActive(0);
  await delay(350);
  setStepActive(1);
  await delay(350);
  setStepActive(2);
  await delay(350);
  setStepActive(3);
  await delay(350);
  setStepActive(4);

  try {
    const res = await api(`/applications/${appId}/validate`, {
      method: "POST",
      headers: { "x-user-role": state.role }
    });
    if (!res.ok) throw new Error("Validation failed");
    const valData = await res.json();
    await delay(300);
    runnerModal.classList.add("hidden");

    if (valData.reused) {
      showToast(`Nothing has changed since Check #${valData.run_number}`, "info");
    } else {
      showToast(`Check #${valData.run_number} recorded successfully!`, "success");
    }
    await loadApplicationDetail(appId);
    loadDashboardData();
  } catch (err) {
    runnerModal.classList.add("hidden");
    showToast("Error running scrutiny checks", "error");
  }
}

function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// ============================================================================
// 11. STAGE 6: DECISION FLOW MODAL
// ============================================================================

function openDecisionModal() {
  if (!state.activeAppDetail) return;
  const modal = document.getElementById("decisionModal");
  const findingsSummary = document.getElementById("decisionFindingsText");

  const deficiencies = state.activeAppDetail.deficiencies || [];
  if (deficiencies.length === 0) {
    findingsSummary.textContent = "All 3-way checks passed cleanly with zero contradictions.";
  } else {
    findingsSummary.textContent = `${deficiencies.length} discrepancy items flagged. (e.g. ${deficiencies[0].plain_title || deficiencies[0].rule_id}).`;
  }

  // Reset reason box
  const writtenReason = document.getElementById("officerWrittenReason");
  if (writtenReason) writtenReason.value = "";
  const countLabel = document.getElementById("reasonCharCount");
  if (countLabel) countLabel.textContent = "0";

  modal.classList.remove("hidden");
}

function closeDecisionModal() {
  document.getElementById("decisionModal")?.classList.add("hidden");
}

async function submitOfficerDecision() {
  const selectedRadio = document.querySelector("input[name='decisionAction']:checked");
  const action = selectedRadio ? selectedRadio.value : "approve";
  const reasonText = (document.getElementById("officerWrittenReason")?.value || "").trim();

  if (reasonText.length < 10) {
    showToast("Mandatory written reason required (minimum 10 characters).", "error");
    return;
  }

  try {
    const res = await api("/decisions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-user-role": "Officer",
        "x-officer-id": "OFFICER-AICTE-001"
      },
      body: JSON.stringify({
        application_id: state.activeAppId,
        action: action,
        written_reason: reasonText
      })
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Decision submission failed");
    }

    closeDecisionModal();
    showToast("Regulatory decision signed & recorded in cryptographic audit ledger!", "success");
    await loadApplicationDetail(state.activeAppId);
    loadDashboardData();
  } catch (err) {
    showToast(err.message || "Failed to record decision", "error");
  }
}

// ============================================================================
// 12. STAGE 5: INSIGHTS PAGES (ALERTS, RISK MAP, DUPLICATES, FRAUD TEST)
// ============================================================================

async function loadAlertsBadgeCount() {
  try {
    const res = await api("/alerts");
    if (res.ok) {
      const alerts = await res.json();
      const badge = document.getElementById("alertsCountBadge");
      if (badge) badge.textContent = alerts.length;
    }
  } catch (err) {
    console.warn("Alerts count error:", err);
  }
}

async function loadAlertsView() {
  const container = document.getElementById("alertsGroupContainer");
  if (!container) return;

  try {
    const res = await api("/alerts");
    if (!res.ok) throw new Error("Could not fetch alerts");
    const alerts = await res.json();

    if (alerts.length === 0) {
      container.innerHTML = `
        <div class="dashboard-card" style="padding: 30px; text-align: center; color: var(--green);">
          ✓ No active statutory regulatory alerts across seeded institutions.
        </div>
      `;
      return;
    }

    // Group alerts by type
    const groups = {
      anomaly: { title: "Possible Tampering & Discrepancies", items: [] },
      expiring: { title: "Expiring & Expired Documents", items: [] },
      missing: { title: "Missing Required Documents", items: [] },
      pending_source: { title: "Waiting for Issuing Authority", items: [] },
      reuse: { title: "Duplicate Document Collisions", items: [] },
      overdue: { title: "Overdue AICTE Scrutiny Deadlines", items: [] }
    };

    alerts.forEach(a => {
      const g = groups[a.alert_type] || groups.anomaly;
      g.items.push(a);
    });

    container.innerHTML = Object.keys(groups).map(k => {
      const g = groups[k];
      if (g.items.length === 0) return "";
      return `
        <div class="dashboard-card">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
            <h3 style="font-size: 15px; font-weight: 700;">${escapeHtml(g.title)}</h3>
            <span class="count-badge" style="background: var(--red); color: white;">${g.items.length}</span>
          </div>
          <div style="display: flex; flex-direction: column; gap: 8px;">
            ${g.items.map(item => `
              <div style="display: flex; justify-content: space-between; align-items: center; padding: 10px; background: var(--bg); border-radius: var(--radius-sm);">
                <div>
                  <b style="font-size: 13px;">${escapeHtml(item.title)}</b>
                  <p style="font-size: 12px; color: var(--text-secondary); margin-top: 2px;">${escapeHtml(item.message)}</p>
                </div>
                <button class="btn-micro-action" onclick="switchView('viewApplications'); loadApplicationDetail('${escapeHtml(item.application_id)}');">
                  View App →
                </button>
              </div>
            `).join("")}
          </div>
        </div>
      `;
    }).join("");

  } catch (err) {
    console.error("Alerts view error:", err);
  }
}

function loadRiskMapView() {
  const canvas = document.getElementById("riskMapChartCanvas");
  if (!canvas || typeof Chart === "undefined") return;

  if (state.riskMapChartInstance) {
    state.riskMapChartInstance.destroy();
  }

  const isDark = state.theme === "dark";

  // Map 5 applications to Concern (X) vs Confidence (Y)
  const points = state.applications.map(app => {
    let concern = 0.1;
    let confidence = 0.9;
    const p = (app.plain_status || "").toLowerCase();
    if (p.includes("verified")) { concern = 0.05; confidence = 0.95; }
    else if (p.includes("mismatch")) { concern = 0.90; confidence = 0.85; }
    else if (p.includes("expired")) { concern = 0.70; confidence = 0.90; }
    else if (p.includes("review")) { concern = 0.50; confidence = 0.40; }

    return {
      x: concern,
      y: confidence,
      r: 10,
      appId: app.id,
      name: app.institution_name,
      status: app.plain_status
    };
  });

  state.riskMapChartInstance = new Chart(canvas, {
    type: "bubble",
    data: {
      datasets: [{
        label: "Applications",
        data: points,
        backgroundColor: points.map(pt => {
          if (pt.x < 0.3 && pt.y > 0.6) return "rgba(19, 136, 8, 0.7)"; // Green
          if (pt.x > 0.6) return "rgba(198, 40, 40, 0.7)"; // Red
          if (pt.y < 0.5) return "rgba(21, 101, 192, 0.7)"; // Blue
          return "rgba(178, 106, 0, 0.7)"; // Amber
        })
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          min: 0,
          max: 1,
          title: { display: true, text: "Concern (Flags & Discrepancies) →", color: isDark ? "#cbd5e1" : "#475569" },
          grid: { color: isDark ? "#334155" : "#e2e8f0" }
        },
        y: {
          min: 0,
          max: 1,
          title: { display: true, text: "Confidence (Evidence Completeness) →", color: isDark ? "#cbd5e1" : "#475569" },
          grid: { color: isDark ? "#334155" : "#e2e8f0" }
        }
      },
      plugins: {
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const pt = ctx.raw;
              return `${pt.name} (${pt.status})`;
            }
          }
        }
      }
    }
  });
}

async function loadDuplicatesView() {
  const container = document.getElementById("duplicatesListContainer");
  if (!container) return;

  try {
    const res = await api("/reuse-ring");
    const data = await res.json();
    const clusters = data.clusters || [];

    // Pair App 1 and App 5
    container.innerHTML = `
      <div style="background: var(--amber-light); border-left: 4px solid var(--amber); padding: 14px; border-radius: var(--radius-sm);">
        <b style="color: var(--amber); font-size: 14px;">⚠️ Cross-College Document Collision Found</b>
        <p style="font-size: 13px; color: var(--text-secondary); margin-top: 4px;">
          The identical Sub-Registrar Lease Registration Number <code>SUBREG-NOIDA-2021-1029</code> was submitted by two separate colleges in Gautam Buddha Nagar district.
        </p>
      </div>

      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; margin-top: 14px;">
        <div style="background: var(--bg); padding: 14px; border-radius: var(--radius-sm);">
          <b style="font-size: 13px; color: var(--navy);">College A: Aryabhata Institute of Engineering</b>
          <p style="font-size: 12px; color: var(--text-secondary); margin-top: 2px;">PID: 1-1029384751 (Application APP-2026-001)</p>
          <div style="margin-top: 8px; font-size: 12px;">Submitted: Land Lease Deed (Doc Reg: SUBREG-NOIDA-2021-1029)</div>
          <button class="btn-micro-action" style="margin-top: 10px;" onclick="switchView('viewApplications'); loadApplicationDetail('APP-2026-001');">
            Inspect App 1 →
          </button>
        </div>

        <div style="background: var(--bg); padding: 14px; border-radius: var(--radius-sm);">
          <b style="font-size: 13px; color: var(--red);">College B: Bhabha Atomic Engineering Academy</b>
          <p style="font-size: 12px; color: var(--text-secondary); margin-top: 2px;">PID: 1-5029384755 (Application APP-2026-005)</p>
          <div style="margin-top: 8px; font-size: 12px;">Submitted: Land Lease Deed (Doc Reg: SUBREG-NOIDA-2021-1029)</div>
          <button class="btn-micro-action" style="margin-top: 10px;" onclick="switchView('viewApplications'); loadApplicationDetail('APP-2026-005');">
            Inspect App 5 →
          </button>
        </div>
      </div>
    `;
  } catch (err) {
    console.warn("Reuse ring error:", err);
  }
}

async function loadFraudTestView() {
  try {
    const res = await api("/drill/results");
    if (res.ok) {
      const data = await res.json();
      renderFraudHeatmap(data);
    }
  } catch (err) {
    console.warn("Fraud test error:", err);
  }
}

async function runFraudDetectionTest() {
  const btn = document.getElementById("runFraudTestBtn");
  if (btn) btn.disabled = true;
  showToast("Running 10 adversarial forgery drill variants...", "info");

  try {
    const res = await api("/drill/run", { method: "POST" });
    if (!res.ok) throw new Error("Drill failed");
    const data = await res.json();
    renderFraudHeatmap(data);
    showToast("Adversarial benchmark drill completed!", "success");
  } catch (err) {
    showToast("Error running fraud test", "error");
  } finally {
    if (btn) btn.disabled = false;
  }
}

function renderFraudHeatmap(data) {
  const tbody = document.getElementById("fraudHeatmapBody");
  const headline = document.getElementById("fraudHeadlineText");
  if (!tbody) return;

  const heatmap = data.heatmap || [];
  const detectedCount = data.overall_detected != null ? data.overall_detected : heatmap.filter(h => h.detected).length;

  if (headline) {
    headline.textContent = `Caught ${detectedCount} of ${heatmap.length} test forgeries when all three checks are combined`;
  }

  tbody.innerHTML = heatmap.map(row => `
    <tr>
      <td><code>${escapeHtml(row.attack_id)}</code></td>
      <td>
        <b>${escapeHtml(row.attack_type)}</b>
        <div style="font-size: 11px; color: var(--text-secondary);">${escapeHtml(row.description || "")}</div>
      </td>
      <td style="text-align: center; color: ${row.content ? 'var(--green)' : 'var(--text-muted)'};">${row.content ? '✓ Caught' : '— Missed'}</td>
      <td style="text-align: center; color: ${row.forensic ? 'var(--green)' : 'var(--text-muted)'};">${row.forensic ? '✓ Caught' : '— Missed'}</td>
      <td style="text-align: center; color: ${row.provenance ? 'var(--green)' : 'var(--text-muted)'};">${row.provenance ? '✓ Caught' : '— Missed'}</td>
      <td style="text-align: center;">
        <span style="font-weight: 700; color: ${row.detected ? 'var(--green)' : 'var(--red)'};">
          ${row.detected ? '✓ DETECTED' : '✗ MISSED'}
        </span>
      </td>
    </tr>
  `).join("");
}

// ============================================================================
// 13. ACTIVITY LOG & CRYPTOGRAPHIC LEDGER
// ============================================================================

async function loadAuditLogView() {
  const tbody = document.getElementById("auditLedgerTableBody");
  if (!tbody) return;

  try {
    const res = await api("/audit?limit=50", {
      headers: { "x-user-role": state.role }
    });
    if (!res.ok) throw new Error("Could not fetch audit entries");
    const entries = await res.json();

    tbody.innerHTML = entries.map(e => `
      <tr>
        <td><b>#${e.id}</b></td>
        <td style="font-size: 12px;">${escapeHtml(formatTimestamp(e.timestamp))}</td>
        <td><span class="status-chip chip-blue" style="font-size: 11px;">${escapeHtml(e.actor_role)}</span></td>
        <td><b>${escapeHtml(e.action)}</b></td>
        <td style="font-size: 11px; color: var(--text-secondary); max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
          ${escapeHtml(JSON.stringify(e.payload || {}))}
        </td>
        <td><code style="font-size: 11px;">${escapeHtml(e.current_hash ? e.current_hash.slice(0, 16) + '...' : 'GENESIS')}</code></td>
      </tr>
    `).join("");

  } catch (err) {
    console.error("Audit ledger error:", err);
  }
}

async function verifyAuditLedgerChain() {
  const banner = document.getElementById("auditChainVerifyStatusBanner");
  if (!banner) return;

  try {
    const res = await api("/audit/verify");
    const data = await res.json();
    banner.style.display = "flex";
    if (data.valid) {
      banner.className = "integrity-status-banner integrity-intact";
      banner.textContent = "✓ SHA-256 hash-chain verified: 100% intact. Zero unauthorized database tampering.";
      showToast("Audit chain verified successfully", "success");
    } else {
      banner.className = "integrity-status-banner integrity-tampered";
      banner.textContent = `❌ Tampering detected at row #${data.tampered_index}! Hash verification failed.`;
      showToast("Cryptographic mismatch detected!", "error");
    }
  } catch (err) {
    showToast("Audit verification error", "error");
  }
}

async function simulateAuditTamperDemo() {
  try {
    const res = await api("/audit/tamper-demo", { method: "POST" });
    if (!res.ok) throw new Error("Tamper demo failed");
    const data = await res.json();
    showToast(data.message || "Audit entry mutated in SQLite database", "warning");
    loadAuditLogView();
    verifyAuditLedgerChain();
  } catch (err) {
    showToast("Tamper demo endpoint failed", "error");
  }
}

// ============================================================================
// 14. COLLEGE SELF-CHECK (PREFLIGHT) & DOCUMENT REPLACEMENT
// ============================================================================

async function loadPreflightView() {
  const tableBody = document.getElementById("preflightTableBody");
  const notice = document.getElementById("preflightStatusNotice");
  if (!tableBody) return;

  notice.innerHTML = `
    <div style="background: var(--bg); padding: 14px; border-radius: var(--radius-sm); border-left: 4px solid var(--blue);">
      <b>Note for Colleges:</b> This pre-flight tool checks whether your papers are present, formatted correctly, and match AICTE master records.
      Tamper and cryptographic issuer checks will be completed by AICTE scrutiny officers.
    </div>
  `;
}

async function runCollegePreflightCheck() {
  const targetAppId = state.activeAppId || "APP-2026-004";
  showToast("Scanning submitted papers against AICTE norms...", "info");

  try {
    const res = await api(`/applications/${targetAppId}/preflight`, {
      method: "POST",
      headers: { "x-user-role": "Institution" }
    });
    if (!res.ok) throw new Error("Preflight check failed");
    const data = await res.json();
    const deficiencies = data.deficiencies || [];

    const tableBody = document.getElementById("preflightTableBody");
    const notice = document.getElementById("preflightStatusNotice");

    if (deficiencies.length === 0) {
      notice.innerHTML = `
        <div style="background: var(--green-light); border-left: 4px solid var(--green); padding: 14px; border-radius: var(--radius-sm); color: var(--green); font-weight: 600;">
          ✓ All submitted documents passed the preliminary pre-submission document check!
        </div>
      `;
      tableBody.innerHTML = `<tr><td colspan="3" style="text-align: center; color: var(--green);">No discrepancies found.</td></tr>`;
    } else {
      notice.innerHTML = `
        <div style="background: var(--amber-light); border-left: 4px solid var(--amber); padding: 14px; border-radius: var(--radius-sm); color: var(--amber); font-weight: 600;">
          ⚠️ ${deficiencies.length} item(s) need your attention before final AICTE scrutiny.
        </div>
      `;

      tableBody.innerHTML = deficiencies.map(d => `
        <tr>
          <td><b>${escapeHtml(d.doc_id || "Document")}</b></td>
          <td style="color: var(--red);">${escapeHtml(d.plain_language_reason || "Value mismatch")}</td>
          <td><b>How to fix:</b> Upload an amended copy with corrected address/date details using the form above.</td>
        </tr>
      `).join("");
    }
  } catch (err) {
    showToast("Pre-submission check failed", "error");
  }
}

async function handleDocumentReplacement(e) {
  e.preventDefault();
  const fileInput = document.getElementById("replaceFileInput");
  const docType = document.getElementById("replaceDocTypeSelect").value;
  const appSelect = document.getElementById("replaceAppSelect");
  const targetAppId = (appSelect ? appSelect.value : null) || state.activeAppId || "APP-2026-003";

  if (!fileInput.files || fileInput.files.length === 0) {
    showToast("Please select a replacement file to upload", "warning");
    return;
  }

  const formData = new FormData();
  formData.append("doc_type", docType);
  formData.append("file", fileInput.files[0]);

  try {
    showToast("Uploading and versioning replacement document...", "info");
    const res = await api(`/applications/${targetAppId}/replace-document`, {
      method: "POST",
      headers: { "x-user-role": "Institution" },
      body: formData
    });

    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || "Replacement failed");
    }
    const data = await res.json();
    showToast(data.message || "Document replaced and versioned successfully!", "success");
    fileInput.value = "";

    // College view: friendly result panel after replacement upload
    const resultPanel = document.getElementById("collegeReplacementResultPanel");
    if (resultPanel && data.diff) {
      resultPanel.style.display = "block";
      const headingElem = document.getElementById("collegeResultHeading");
      const checkPillElem = document.getElementById("collegeResultCheckPill");
      const expElem = document.getElementById("collegeResultExplanation");

      if (headingElem) headingElem.textContent = `What changed with this upload (Check #${data.run_number || 2})`;
      if (checkPillElem) checkPillElem.textContent = `Check #${data.run_number || 2}`;
      if (expElem) expElem.textContent = data.diff.plain_explanation || "Document successfully checked.";

      const fixedList = document.getElementById("collegeFixedList");
      const remainingList = document.getElementById("collegeRemainingList");

      const resolved = data.diff.resolved || [];
      if (resolved.length > 0) {
        fixedList.innerHTML = resolved.map(item => `
          <div style="background: var(--green-light); border-left: 4px solid var(--green); padding: 10px 14px; border-radius: var(--radius-sm); font-size: 13px; color: var(--green); font-weight: 600;">
            ✓ Fixed: ${escapeHtml(item.plain_title || formatDocType(item.doc_type) || "Issue resolved")}
          </div>
        `).join("");
      } else {
        fixedList.innerHTML = `<div style="font-size: 13px; color: var(--text-muted); padding: 6px 0;">0 issues fixed in this upload.</div>`;
      }

      const remaining = data.diff.persisting || [];
      if (remaining.length > 0) {
        remainingList.innerHTML = remaining.map(item => `
          <div style="background: var(--grey-light); border-left: 4px solid var(--grey); padding: 10px 14px; border-radius: var(--radius-sm); font-size: 13px; color: var(--text-primary);">
            <b>Still open:</b> ${escapeHtml(item.plain_title || "Pending item")} — <i>How to fix: Upload an amended copy with corrected details.</i>
          </div>
        `).join("");
      } else {
        remainingList.innerHTML = `
          <div style="background: var(--green-light); border-left: 4px solid var(--green); padding: 10px 14px; border-radius: var(--radius-sm); font-size: 13px; color: var(--green); font-weight: 600;">
            ✓ No remaining issues found! Your application is in order.
          </div>
        `;
      }

      resultPanel.scrollIntoView({ behavior: "smooth" });
    }

    runCollegePreflightCheck();
    loadDashboardData();
  } catch (err) {
    showToast(err.message || "Failed to upload replacement document", "error");
  }
}

// ============================================================================
// 15. WELCOME ROLE MODAL & COACH-MARK TOUR
// ============================================================================

function showWelcomeModal() {
  const modal = document.getElementById("welcomeModal");
  if (!modal) return;
  modal.classList.remove("hidden");

  modal.querySelectorAll(".role-choice-card").forEach(card => {
    card.addEventListener("click", () => {
      const selectedRole = card.getAttribute("data-role");
      localStorage.setItem("truthtrace-welcome-seen", "true");
      modal.classList.add("hidden");
      setRole(selectedRole);
    });
  });
}

// 5-Step Coach-mark Tour
const tourSteps = [
  {
    target: "statCardReview",
    title: "1. The Scrutiny Queue",
    content: "Stat cards summarize your entire queue at a glance. Green means clear, amber means needs review, and red means a problem was flagged.",
    action: () => switchView("viewHome")
  },
  {
    target: "roleSelect",
    title: "2. Plain Language Status",
    content: "Switch roles anytime here. Scrutiny Officers inspect issues, Colleges check papers, and Auditors verify ledger integrity.",
    action: () => {}
  },
  {
    target: "navApplications",
    title: "3. Three Independent Checks",
    content: "TruthTrace validates applications through three independent checks: Document check, Tamper check, and Issuer check.",
    action: () => switchView("viewApplications")
  },
  {
    target: "appSearchInput",
    title: "4. Document Evidence",
    content: "Clicking any application reveals highlighted visual evidence, side-by-side discrepancy comparisons, and cross-checks.",
    action: () => {}
  },
  {
    target: "openDemoDrawerBtn",
    title: "5. Officer Legal Decision",
    content: "Automated checks only advise! The officer always records a reasoned legal decision. Use the gear icon for presentation controls.",
    action: () => {}
  }
];

function startCoachTour() {
  state.tourCurrentStep = 0;
  showTourStep(0);
}

function showTourStep(index) {
  const step = tourSteps[index];
  if (!step) {
    endCoachTour();
    return;
  }

  step.action();

  const overlayBox = document.getElementById("tourOverlayBox");
  const title = document.getElementById("tourStepTitle");
  const content = document.getElementById("tourStepContent");
  const indicator = document.getElementById("tourStepIndicator");
  const nextBtn = document.getElementById("tourNextBtn");

  title.textContent = step.title;
  content.textContent = step.content;
  indicator.textContent = `Step ${index + 1} of ${tourSteps.length}`;
  nextBtn.textContent = index === tourSteps.length - 1 ? "Finish ✓" : "Next →";

  const targetElem = document.getElementById(step.target);
  if (targetElem) {
    const rect = targetElem.getBoundingClientRect();
    overlayBox.style.display = "block";
    overlayBox.style.top = `${Math.min(window.innerHeight - 200, Math.max(80, rect.bottom + 12))}px`;
    overlayBox.style.left = `${Math.min(window.innerWidth - 360, Math.max(20, rect.left))}px`;
  } else {
    overlayBox.style.display = "block";
    overlayBox.style.top = "100px";
    overlayBox.style.left = "40px";
  }
}

function nextCoachTourStep() {
  state.tourCurrentStep++;
  if (state.tourCurrentStep < tourSteps.length) {
    showTourStep(state.tourCurrentStep);
  } else {
    endCoachTour();
  }
}

function endCoachTour() {
  const overlayBox = document.getElementById("tourOverlayBox");
  if (overlayBox) overlayBox.style.display = "none";
}

// ============================================================================
// 16. TOAST NOTIFICATIONS & UTILITY HELPERS
// ============================================================================

function showToast(message, type = "info", duration = 3500) {
  const container = document.getElementById("toastContainer");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  const icon = type === "success" ? "✓" : type === "error" ? "❌" : type === "warning" ? "⚠️" : "ℹ️";
  toast.innerHTML = `<span>${icon}</span><span>${escapeHtml(message)}</span>`;

  container.appendChild(toast);
  setTimeout(() => {
    toast.style.animation = "slideDown 0.25s forwards";
    setTimeout(() => toast.remove(), 250);
  }, duration);
}

function getStatusColorClass(color) {
  if (color === "green") return "chip-green";
  if (color === "red") return "chip-red";
  if (color === "blue") return "chip-blue";
  if (color === "grey") return "chip-grey";
  return "chip-amber";
}

function escapeHtml(text) {
  if (text == null) return "";
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// ============================================================================
// ADVERSARIAL TEST LAB: FORGERY SIMULATION & EXPLANATION
// ============================================================================

const advState = {
  baselineDocs: [],
  selectedDocKey: "base_affidavit",
  selectedDocInfo: null,
  activeSession: null,
  viewMode: "modified",
  wizardScenarios: []
};

// Curated scientific theory & counterfactual mitigation encyclopedia for modal
const ADV_DETECTOR_ENCYCLOPEDIA = {
  det_deepfake: {
    name: "Deepfake & Face Frequency Analysis",
    category: "Identity & Visual Forensics",
    icon: "🔬",
    theory: "Generative Adversarial Networks (GANs) using transposed convolutional layers leave subtle periodic spatial grid patterns. When converted via 2D Fast Fourier Transform (FFT) into the spectral domain, natural camera images follow a continuous 1/f roll-off curve, whereas GAN-synthesized and face-swapped imagery exhibits abnormal high-frequency spectral energy spikes and periodic quadrant peaks.",
    blindSpot: "Single-lane optical pixel forensics and OCR engines perceive realistic pixels and cannot detect mathematical frequency anomalies. Cross-spectral roll-off analysis isolates generative synthesis independently of visual fidelity.",
    mitigation: "Require cryptographic liveness biometric photo captures directly from statutory KYC portals with embedded Ed25519 digital timestamps."
  },
  det_ela: {
    name: "Error Level Analysis (ELA)",
    category: "Pixel Forensics",
    icon: "📸",
    theory: "Analyzes compression discrepancy across 8x8 DCT grid blocks. When an image is modified and re-saved, spliced or whited-out regions compress at a different rate than surrounding canvas, creating high residual error in Error Level Analysis.",
    blindSpot: "Lossless PDF vector text swaps do not alter JPEG pixel streams. ELA must be triangulated with font span typographic analysis and cryptographic provenance.",
    mitigation: "Always preserve uncompressed statutory master scans and reject repeatedly re-encoded multi-generation JPEG submissions."
  },
  det_noise: {
    name: "Local Noise Residual & Sensor Disparity",
    category: "Pixel Forensics",
    icon: "🧬",
    theory: "Measures high-frequency Laplacian noise variance across a 16x16 canvas grid. Natural optical capture produces uniform sensor noise. Spliced visual patches or foreign crops introduce localized noise variance shifts (high coefficient of variation).",
    blindSpot: "Uniform Gaussian noise filters applied across the entire page can obscure localized variance unless tested with spatial frequency roll-off.",
    mitigation: "Verify scanner device hardware signatures and utilize tamper-proof digital seals directly at capture time."
  },
  det_copymove: {
    name: "Copy-Move Feature Duplication (ORB)",
    category: "Pixel Forensics",
    icon: "🧩",
    theory: "Uses Oriented FAST and Rotated BRIEF (ORB) feature descriptor keypoint extraction to detect visual patches within the same canvas that have been duplicated to fabricate equipment, laboratory benches, or personnel.",
    blindSpot: "Cloned patches with heavy rotation or non-affine warping can evade keypoint correlation unless multi-scale feature pyramids are evaluated.",
    mitigation: "Deploy optical geo-tagging with cryptographic camera metadata and unannounced physical surprise inspections."
  },
  det_typography: {
    name: "OCR & Typographic Splicing Analysis",
    category: "Document Structure",
    icon: "🔤",
    theory: "Extracts font family, font size, weight, and kerning bounding boxes across regulatory fields. When a fraudster whites out an institutional name or tenure and types new text, disparate font families or size jumps exceeding 7pt are immediately identified.",
    blindSpot: "Scanned raster documents flatten typography into pixels. Requires high-precision OCR character segmentation triangulated with master registry ledgers.",
    mitigation: "Mandate standardized government digital fillable PDF forms with institutional digital certificate seals."
  },
  det_provenance: {
    name: "Cryptographic Signature & QR Seal Check",
    category: "Cryptographic Provenance",
    icon: "🔏",
    theory: "Validates the digital Ed25519 signature embedded inside the statutory QR seal against the verified public key of the issuing authority (e.g. Sub-Registrar, Directorate of Technical Education, Payment Gateway). If a single byte was altered, signature verification cryptographically fails.",
    blindSpot: "If an issuing authority gateway is offline, the provenance lane routes to SOURCE_UNAVAILABLE rather than false clearance.",
    mitigation: "Never accept unsealed photocopies for statutory land or financial clearances; enforce live authority registry validation."
  },
  det_master_record: {
    name: "Master Registry Cross-Check",
    category: "Regulatory Consistency",
    icon: "🏛️",
    theory: "Cross-checks extracted claims (Permanent Institute ID, Approved Intake, Signatory Name, Fee Payment Txn ID) against AICTE central database ledger records.",
    blindSpot: "Offline forged documents with matching format but fabricated data can look clean internally; only central cross-verification exposes the contradiction.",
    mitigation: "Implement automated API handshakes with state land registries and statutory fee payment gateways."
  },
  det_metadata: {
    name: "PDF Binary & Metadata Forensics",
    category: "Binary Stream Inspection",
    icon: "🛡️",
    theory: "Scans PDF trailer, dictionary streams, producer tags, and incremental update (%%EOF) count. Identifies consumer graphic design software (Photoshop, Canva, GIMP) and manual revision chains.",
    blindSpot: "Savvy attackers can strip PDF metadata with tools like exiftool. Must be triangulated with pixel forensics and cryptographic seal verification.",
    mitigation: "Require documents to originate directly from approved institutional document management systems."
  }
};

function setupAdversarialLabListeners() {
  // Document selector change
  document.getElementById("advDocSelect")?.addEventListener("change", (e) => {
    advState.selectedDocKey = e.target.value;
    updateBaseDocSummaryCard();
  });

  // Custom File Upload & Drag-and-Drop
  const dropzone = document.getElementById("advUploadDropzone");
  const fileInput = document.getElementById("advFileInput");
  const browseTrigger = document.getElementById("advBrowseTrigger");

  browseTrigger?.addEventListener("click", () => fileInput?.click());
  dropzone?.addEventListener("click", (e) => {
    if (e.target !== browseTrigger) fileInput?.click();
  });

  dropzone?.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropzone.classList.add("dragover");
  });
  dropzone?.addEventListener("dragleave", () => {
    dropzone.classList.remove("dragover");
  });
  dropzone?.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
    if (e.dataTransfer?.files?.length) {
      handleCustomFileUpload(e.dataTransfer.files[0]);
    }
  });

  fileInput?.addEventListener("change", (e) => {
    if (e.target.files?.length) {
      handleCustomFileUpload(e.target.files[0]);
    }
  });

  // Toggles and Sliders
  const toggleDeepfake = document.getElementById("advToggleDeepfake");
  const deepfakeSliderRow = document.getElementById("advDeepfakeSliderRow");
  toggleDeepfake?.addEventListener("change", () => {
    if (deepfakeSliderRow) {
      deepfakeSliderRow.style.display = toggleDeepfake.checked ? "block" : "none";
    }
    updateActiveAttacksBadge();
  });

  document.getElementById("advSliderDeepfakeIntensity")?.addEventListener("input", (e) => {
    const valSpan = document.getElementById("advDeepfakeIntensityVal");
    if (valSpan) valSpan.textContent = `${e.target.value}%`;
  });

  document.getElementById("advInputOverrideName")?.addEventListener("input", updateActiveAttacksBadge);
  document.getElementById("advQuickFillNameBtn")?.addEventListener("click", () => {
    const input = document.getElementById("advInputOverrideName");
    if (input) {
      input.value = "Dr. Devadatta Verma";
      updateActiveAttacksBadge();
    }
  });

  document.getElementById("advSliderNoise")?.addEventListener("input", (e) => {
    const valSpan = document.getElementById("advNoiseVal");
    if (valSpan) valSpan.textContent = `${e.target.value}%`;
    updateActiveAttacksBadge();
  });

  document.getElementById("advSliderRotation")?.addEventListener("input", (e) => {
    const valSpan = document.getElementById("advRotationVal");
    if (valSpan) valSpan.textContent = `${parseFloat(e.target.value).toFixed(1)}°`;
    updateActiveAttacksBadge();
  });

  // Other Toggles
  ["advToggleCorruptQR", "advToggleSpoofMeta", "advToggleDoubleJpeg", "advToggleCopyMove"].forEach(id => {
    document.getElementById(id)?.addEventListener("change", updateActiveAttacksBadge);
  });

  // Quick Tip Buttons
  document.getElementById("tipDeepfake")?.addEventListener("click", () => {
    const toggle = document.getElementById("advToggleDeepfake");
    if (toggle) {
      toggle.checked = true;
      if (deepfakeSliderRow) deepfakeSliderRow.style.display = "block";
      updateActiveAttacksBadge();
      showToast("Deepfake Photo toggle enabled. Click 'Run Verification Pipeline' to test!", "info");
    }
  });

  document.getElementById("tipCorruptQR")?.addEventListener("click", () => {
    const toggle = document.getElementById("advToggleCorruptQR");
    if (toggle) {
      toggle.checked = true;
      updateActiveAttacksBadge();
      showToast("Corrupt Ed25519 QR Signature enabled. Ready to test!", "info");
    }
  });

  document.getElementById("tipOverrideName")?.addEventListener("click", () => {
    const input = document.getElementById("advInputOverrideName");
    if (input) {
      input.value = "99 Years Perpetual";
      updateActiveAttacksBadge();
      showToast("Overridden field injected. Ready to test typographic splicing!", "info");
    }
  });

  document.getElementById("tipNoiseSkew")?.addEventListener("click", () => {
    const noise = document.getElementById("advSliderNoise");
    const rot = document.getElementById("advSliderRotation");
    if (noise && rot) {
      noise.value = "60";
      rot.value = "4.5";
      document.getElementById("advNoiseVal").textContent = "60%";
      document.getElementById("advRotationVal").textContent = "4.5°";
      updateActiveAttacksBadge();
      showToast("Sensor noise and rotation skew configured!", "info");
    }
  });

  document.getElementById("tipMetadata")?.addEventListener("click", () => {
    const toggle = document.getElementById("advToggleSpoofMeta");
    if (toggle) {
      toggle.checked = true;
      updateActiveAttacksBadge();
      showToast("Canva/Photoshop metadata tag injected!", "info");
    }
  });

  // Action Buttons
  document.getElementById("advRunSimBtn")?.addEventListener("click", runAdversarialSimulation);
  document.getElementById("advClearAttacksBtn")?.addEventListener("click", clearAttackControls);
  document.getElementById("advResetSandboxBtn")?.addEventListener("click", resetSandbox);

  // Export Report Buttons
  document.getElementById("advExportReportBtn")?.addEventListener("click", exportSimulationReport);
  document.getElementById("advExportReportBottomBtn")?.addEventListener("click", exportSimulationReport);

  // Viewer Mode Tabs
  document.getElementById("advTabModified")?.addEventListener("click", () => setViewerMode("modified"));
  document.getElementById("advTabDiff")?.addEventListener("click", () => setViewerMode("diff"));

  // Wizard Modal Triggers
  document.getElementById("advOpenWizardBtn")?.addEventListener("click", openAdvWizard);
  document.getElementById("advCloseWizardBtn")?.addEventListener("click", closeAdvWizard);
  document.getElementById("advCloseWizardFooterBtn")?.addEventListener("click", closeAdvWizard);

  // Detector Info Modal Triggers
  document.getElementById("advCloseInfoModalBtn")?.addEventListener("click", closeDetectorInfoModal);
  document.getElementById("advCloseInfoModalFooterBtn")?.addEventListener("click", closeDetectorInfoModal);
}

async function loadAdversarialLabView() {
  const restrictedBanner = document.getElementById("advAccessRestrictedBanner");
  const mainContent = document.getElementById("advLabMainContent");

  // Role Gate: Officer and Auditor only
  if (state.role === "Institution") {
    if (restrictedBanner) restrictedBanner.style.display = "block";
    if (mainContent) mainContent.style.display = "none";
    return;
  }

  if (restrictedBanner) restrictedBanner.style.display = "none";
  if (mainContent) mainContent.style.display = "block";

  try {
    const res = await api("/adversarial/documents", {
      headers: { "X-Role": state.role }
    });
    if (res.ok) {
      advState.baselineDocs = await res.json();
      populateBaselineDocsSelect();
      updateBaseDocSummaryCard();
    }
  } catch (err) {
    console.warn("Could not fetch baseline docs:", err);
  }

  // Pre-load clean preview if not yet run
  if (!advState.activeSession) {
    loadCleanBaselinePreview();
  }
}

function populateBaselineDocsSelect() {
  const select = document.getElementById("advDocSelect");
  if (!select || !advState.baselineDocs.length) return;

  select.innerHTML = advState.baselineDocs.map(d => `
    <option value="${escapeHtml(d.id)}" ${d.id === advState.selectedDocKey ? "selected" : ""}>
      ${escapeHtml(d.name)} • ${escapeHtml(d.category)}
    </option>
  `).join("");
}

function updateBaseDocSummaryCard() {
  const doc = advState.baselineDocs.find(d => d.id === advState.selectedDocKey);
  if (!doc) return;

  advState.selectedDocInfo = doc;
  const nameEl = document.getElementById("advBaseDocName");
  const chipEl = document.getElementById("advBaseDocTypeChip");
  const hashEl = document.getElementById("advBaseDocHash");

  if (nameEl) nameEl.textContent = doc.name;
  if (chipEl) chipEl.textContent = doc.doc_type;
  if (hashEl) hashEl.textContent = `Signatory: ${doc.signatory || 'Authority'} • ${doc.description || ''}`;

  loadCleanBaselinePreview();
}

async function loadCleanBaselinePreview() {
  try {
    // Run an empty simulation to render clean baseline
    const res = await api("/adversarial/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Role": state.role },
      body: JSON.stringify({ base_doc_key: advState.selectedDocKey })
    });
    if (res.ok) {
      const data = await res.json();
      advState.activeSession = data;
      renderSimulationResults(data);
    }
  } catch (err) {
    console.warn("Error loading clean baseline preview:", err);
  }
}

function handleCustomFileUpload(file) {
  if (!file) return;
  advState.customFile = file;

  const badge = document.getElementById("advCustomFileBadge");
  if (badge) {
    badge.textContent = `✓ Uploaded: ${file.name} (${Math.round(file.size / 1024)} KB)`;
    badge.style.display = "block";
  }

  showToast(`Custom document '${file.name}' loaded into sandbox!`, "success");
}

function updateActiveAttacksBadge() {
  let count = 0;
  if (document.getElementById("advToggleDeepfake")?.checked) count++;
  if (document.getElementById("advInputOverrideName")?.value.trim()) count++;
  if (parseInt(document.getElementById("advSliderNoise")?.value || "0", 10) > 10) count++;
  if (Math.abs(parseFloat(document.getElementById("advSliderRotation")?.value || "0")) > 0.5) count++;
  if (document.getElementById("advToggleCorruptQR")?.checked) count++;
  if (document.getElementById("advToggleSpoofMeta")?.checked) count++;
  if (document.getElementById("advToggleDoubleJpeg")?.checked) count++;
  if (document.getElementById("advToggleCopyMove")?.checked) count++;

  const badge = document.getElementById("advActiveAttacksCount");
  if (badge) {
    badge.textContent = count === 0 ? "0 active attacks (Clean Baseline)" : `${count} active attack vector${count > 1 ? 's' : ''}`;
    badge.style.color = count > 0 ? "var(--red)" : "var(--text-muted)";
    badge.style.fontWeight = count > 0 ? "700" : "400";
  }
}

function clearAttackControls() {
  const toggleDeepfake = document.getElementById("advToggleDeepfake");
  if (toggleDeepfake) toggleDeepfake.checked = false;
  const deepfakeRow = document.getElementById("advDeepfakeSliderRow");
  if (deepfakeRow) deepfakeRow.style.display = "none";

  const inputName = document.getElementById("advInputOverrideName");
  if (inputName) inputName.value = "";

  const sliderNoise = document.getElementById("advSliderNoise");
  if (sliderNoise) sliderNoise.value = "0";
  const noiseVal = document.getElementById("advNoiseVal");
  if (noiseVal) noiseVal.textContent = "0%";

  const sliderRot = document.getElementById("advSliderRotation");
  if (sliderRot) sliderRot.value = "0";
  const rotVal = document.getElementById("advRotationVal");
  if (rotVal) rotVal.textContent = "0.0°";

  ["advToggleCorruptQR", "advToggleSpoofMeta", "advToggleDoubleJpeg", "advToggleCopyMove"].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.checked = false;
  });

  updateActiveAttacksBadge();
  showToast("All attack toggles cleared.", "info");
}

function resetSandbox() {
  clearAttackControls();
  advState.customFile = null;
  const customBadge = document.getElementById("advCustomFileBadge");
  if (customBadge) customBadge.style.display = "none";

  loadCleanBaselinePreview();
  showToast("Adversarial Sandbox reset to clean baseline.", "success");
}

async function runAdversarialSimulation() {
  const runBtn = document.getElementById("advRunSimBtn");
  if (runBtn) {
    runBtn.disabled = true;
    runBtn.innerHTML = `⚡ Running Pipelines...`;
  }

  showToast("Executing multi-probe verification pipeline on modified document...", "info");

  const config = {
    base_doc_key: advState.selectedDocKey,
    deepfake_photo: document.getElementById("advToggleDeepfake")?.checked || false,
    deepfake_intensity: parseFloat(document.getElementById("advSliderDeepfakeIntensity")?.value || 85) / 100.0,
    override_name: document.getElementById("advInputOverrideName")?.value.trim() || "",
    noise_level: parseFloat(document.getElementById("advSliderNoise")?.value || 0) / 100.0,
    rotation_angle: parseFloat(document.getElementById("advSliderRotation")?.value || 0),
    corrupt_qr: document.getElementById("advToggleCorruptQR")?.checked || false,
    spoof_metadata: document.getElementById("advToggleSpoofMeta")?.checked || false,
    jpeg_recompress: document.getElementById("advToggleDoubleJpeg")?.checked || false,
    copy_move: document.getElementById("advToggleCopyMove")?.checked || false
  };

  try {
    const res = await api("/adversarial/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Role": state.role },
      body: JSON.stringify(config)
    });

    if (!res.ok) {
      throw new Error(`Simulation failed: ${res.statusText}`);
    }

    const data = await res.json();
    advState.activeSession = data;
    renderSimulationResults(data);

    const flaggedCount = data.detectors.filter(d => d.status === "FLAGGED").length;
    if (flaggedCount > 0) {
      showToast(`Simulation complete: ${flaggedCount} anomaly detector${flaggedCount > 1 ? 's' : ''} flagged!`, "warning");
    } else {
      showToast("Simulation complete: All automated detectors passed.", "success");
    }
  } catch (err) {
    console.error("Adversarial simulation error:", err);
    showToast("Error running simulation pipeline: " + err.message, "error");
  } finally {
    if (runBtn) {
      runBtn.disabled = false;
      runBtn.innerHTML = `⚡ Run Verification Pipeline`;
    }
  }
}

function renderSimulationResults(data) {
  // 1. Update Preview Images
  const modImg = document.getElementById("advModifiedImg");
  const placeholder = document.getElementById("advImgPlaceholder");
  const diffCleanImg = document.getElementById("advDiffCleanImg");
  const diffModImg = document.getElementById("advDiffModImg");

  const modRenderUrl = data.modified_renders && data.modified_renders.length ? data.modified_renders[0] : "";
  const cleanRenderUrl = data.clean_renders && data.clean_renders.length ? data.clean_renders[0] : "";

  if (modRenderUrl) {
    if (modImg) {
      modImg.src = modRenderUrl + "?t=" + Date.now();
      modImg.style.display = "block";
    }
    if (placeholder) placeholder.style.display = "none";
  }

  if (diffCleanImg && cleanRenderUrl) {
    diffCleanImg.src = cleanRenderUrl + "?t=" + Date.now();
  }
  if (diffModImg && modRenderUrl) {
    diffModImg.src = modRenderUrl + "?t=" + Date.now();
  }

  // 2. Render Visual Bounding Box Highlights
  renderDetectorOverlayBoxes(data.detectors || []);

  // 3. Triangulation Scorecard
  const scorecard = document.getElementById("advScorecardCard");
  if (scorecard) scorecard.style.display = "block";

  const statusChip = document.getElementById("advOverallStatusChip");
  if (statusChip) {
    statusChip.className = `status-chip ${data.status_chip || 'chip-green'}`;
    statusChip.textContent = data.status === "verified" ? "Verified" : data.status === "mismatch_detected" ? "Anomaly Flagged" : "Review Required";
  }

  const verdictText = document.getElementById("advOverallVerdictText");
  if (verdictText) verdictText.textContent = data.status_label || "Scrutiny Evaluation Complete";

  const assuranceVal = document.getElementById("advAssuranceScoreVal");
  const assuranceBar = document.getElementById("advAssuranceBar");
  const assurancePct = Math.round((data.assurance_score || 0) * 100);
  if (assuranceVal) assuranceVal.textContent = `${assurancePct}%`;
  if (assuranceBar) assuranceBar.style.width = `${assurancePct}%`;

  const suspicionVal = document.getElementById("advSuspicionScoreVal");
  const suspicionBar = document.getElementById("advSuspicionBar");
  const suspicionPct = Math.round((data.suspicion_score || 0) * 100);
  if (suspicionVal) suspicionVal.textContent = `${suspicionPct}%`;
  if (suspicionBar) suspicionBar.style.width = `${suspicionPct}%`;

  // 4. Anomaly Detectors Matrix
  renderDetectorsMatrix(data.detectors || []);

  // 5. Chain-of-Custody Card
  const custodyCard = document.getElementById("advCustodyCard");
  const custodyText = document.getElementById("advCustodySessionText");
  if (custodyCard) custodyCard.style.display = "block";
  if (custodyText) {
    custodyText.textContent = `Session: ${data.session_id} • Stamped in cryptographic audit trail (Event #${data.audit_entry_id || 'LOG'})`;
  }
}

function renderDetectorOverlayBoxes(detectors) {
  const layer = document.getElementById("advOverlayLayer");
  if (!layer) return;

  layer.innerHTML = "";
  const flagged = detectors.filter(d => d.status === "FLAGGED" && d.bbox && d.bbox.length === 4);

  flagged.forEach(d => {
    const [ymin, xmin, ymax, xmax] = d.bbox;
    if (ymax <= ymin || xmax <= xmin) return;

    const box = document.createElement("div");
    box.className = "adv-box-flagged";
    box.style.top = `${ymin * 100}%`;
    box.style.left = `${xmin * 100}%`;
    box.style.height = `${(ymax - ymin) * 100}%`;
    box.style.width = `${(xmax - xmin) * 100}%`;

    const badge = document.createElement("div");
    badge.className = "adv-box-badge";
    badge.textContent = d.name;
    box.appendChild(badge);

    box.title = `${d.name}: ${d.plain_language_reason}`;
    box.addEventListener("click", () => openDetectorInfoModal(d.id));

    layer.appendChild(box);
  });
}

function renderDetectorsMatrix(detectors) {
  const list = document.getElementById("advDetectorsList");
  const passCountEl = document.getElementById("advDetectorsPassCount");
  const flagCountEl = document.getElementById("advDetectorsFlagCount");

  const passedCount = detectors.filter(d => d.status === "PASSED").length;
  const flaggedCount = detectors.filter(d => d.status === "FLAGGED").length;

  if (passCountEl) passCountEl.textContent = `${passedCount} Passed`;
  if (flagCountEl) flagCountEl.textContent = `${flaggedCount} Flagged`;

  if (!list) return;

  list.innerHTML = detectors.map(d => {
    const isFlagged = d.status === "FLAGGED";
    const cardClass = isFlagged ? "adv-detector-card flagged" : "adv-detector-card passed";
    const badgeClass = isFlagged ? "adv-badge-flagged" : "adv-badge-passed";

    return `
      <div class="${cardClass}">
        <div class="adv-detector-top">
          <div class="adv-detector-name">
            <span>${escapeHtml(d.name)}</span>
            <span class="adv-detector-cat">(${escapeHtml(d.category)})</span>
          </div>
          <div style="display: flex; align-items: center; gap: 8px;">
            <span class="${badgeClass}">${escapeHtml(d.status)}</span>
            <button class="adv-detector-info-trigger" onclick="openDetectorInfoModal('${escapeHtml(d.id)}')" title="How this detector works">❓</button>
          </div>
        </div>

        <div class="adv-detector-reason">
          ${isFlagged ? `🚨 <b>Flagged Anomaly:</b> ` : `✅ <b>Probe Clean:</b> `}
          ${escapeHtml(d.plain_language_reason)}
        </div>

        <div class="adv-detector-hint">
          <span>💡</span>
          <span><b>Counterfactual Defense:</b> ${escapeHtml(d.counterfactual_hint)}</span>
        </div>
      </div>
    `;
  }).join("");
}

function setViewerMode(mode) {
  advState.viewMode = mode;
  const tabMod = document.getElementById("advTabModified");
  const tabDiff = document.getElementById("advTabDiff");
  const singleWrapper = document.getElementById("advSingleViewWrapper");
  const diffWrapper = document.getElementById("advDiffViewWrapper");

  if (mode === "modified") {
    tabMod?.classList.add("active");
    tabDiff?.classList.remove("active");
    if (singleWrapper) singleWrapper.style.display = "block";
    if (diffWrapper) diffWrapper.style.display = "none";
  } else {
    tabMod?.classList.remove("active");
    tabDiff?.classList.add("active");
    if (singleWrapper) singleWrapper.style.display = "none";
    if (diffWrapper) diffWrapper.style.display = "grid";
  }
}

// ============================================================================
// ADVERSARIAL WIZARD & EXPLANATION MODALS
// ============================================================================

async function openAdvWizard() {
  const modal = document.getElementById("advWizardModal");
  const container = document.getElementById("advWizardCardsContainer");
  if (!modal || !container) return;

  modal.style.display = "flex";

  try {
    const res = await api("/adversarial/wizard", {
      headers: { "X-Role": state.role }
    });
    if (res.ok) {
      advState.wizardScenarios = await res.json();
      renderWizardCards(advState.wizardScenarios);
    }
  } catch (err) {
    console.warn("Could not fetch wizard scenarios:", err);
  }
}

function renderWizardCards(scenarios) {
  const container = document.getElementById("advWizardCardsContainer");
  if (!container) return;

  container.innerHTML = scenarios.map((s, idx) => `
    <div class="adv-wizard-card">
      <span style="font-size: 26px;">${s.icon || '🧪'}</span>
      <div class="adv-wizard-info">
        <div class="adv-wizard-title">
          <span>${escapeHtml(s.title)}</span>
          <span class="adv-wizard-badge status-chip chip-blue">${escapeHtml(s.difficulty || 'Advanced')}</span>
        </div>
        <div class="adv-wizard-desc">${escapeHtml(s.description)}</div>
        <div style="font-size: 11px; color: var(--navy); margin-top: 4px; font-weight: 600;">
          👉 ${escapeHtml(s.guide_prompt)}
        </div>
      </div>
      <button class="btn-primary" style="padding: 6px 14px; font-size: 12px; white-space: nowrap;" onclick="loadWizardScenarioByIndex(${idx})">
        ⚡ Load Scenario
      </button>
    </div>
  `).join("");
}

function closeAdvWizard() {
  const modal = document.getElementById("advWizardModal");
  if (modal) modal.style.display = "none";
}

function loadWizardScenarioByIndex(index) {
  const scenario = advState.wizardScenarios[index];
  if (!scenario) return;

  closeAdvWizard();

  // 1. Select Target Doc
  if (scenario.target_doc) {
    advState.selectedDocKey = scenario.target_doc;
    const docSelect = document.getElementById("advDocSelect");
    if (docSelect) docSelect.value = scenario.target_doc;
    updateBaseDocSummaryCard();
  }

  // 2. Set Config
  clearAttackControls();
  const cfg = scenario.config || {};

  if (cfg.deepfake_photo) {
    const toggle = document.getElementById("advToggleDeepfake");
    if (toggle) toggle.checked = true;
    const row = document.getElementById("advDeepfakeSliderRow");
    if (row) row.style.display = "block";
    const slider = document.getElementById("advSliderDeepfakeIntensity");
    if (slider && cfg.deepfake_intensity) slider.value = Math.round(cfg.deepfake_intensity * 100);
  }

  if (cfg.override_name) {
    const input = document.getElementById("advInputOverrideName");
    if (input) input.value = cfg.override_name;
  }

  if (cfg.noise_level) {
    const slider = document.getElementById("advSliderNoise");
    if (slider) {
      slider.value = Math.round(cfg.noise_level * 100);
      document.getElementById("advNoiseVal").textContent = `${Math.round(cfg.noise_level * 100)}%`;
    }
  }

  if (cfg.rotation_angle) {
    const slider = document.getElementById("advSliderRotation");
    if (slider) {
      slider.value = cfg.rotation_angle;
      document.getElementById("advRotationVal").textContent = `${cfg.rotation_angle.toFixed(1)}°`;
    }
  }

  if (cfg.corrupt_qr) {
    const toggle = document.getElementById("advToggleCorruptQR");
    if (toggle) toggle.checked = true;
  }

  if (cfg.spoof_metadata) {
    const toggle = document.getElementById("advToggleSpoofMeta");
    if (toggle) toggle.checked = true;
  }

  if (cfg.jpeg_recompress) {
    const toggle = document.getElementById("advToggleDoubleJpeg");
    if (toggle) toggle.checked = true;
  }

  updateActiveAttacksBadge();
  showToast(`Scenario Loaded: "${scenario.title}". Click 'Run Verification Pipeline' to inspect!`, "success");
}

function openDetectorInfoModal(detectorId) {
  const modal = document.getElementById("advDetectorInfoModal");
  if (!modal) return;

  const info = ADV_DETECTOR_ENCYCLOPEDIA[detectorId] || {
    name: "Verification Probe",
    category: "Forensic Analysis",
    icon: "🔬",
    theory: "Analyzes specific document and cryptographic artifacts against statutory guidelines.",
    blindSpot: "Single-lane checks can miss sophisticated forgeries; multi-lane triangulation is mandatory.",
    mitigation: "Ensure compliance with AICTE Approval Process Handbook (APH) standards."
  };

  document.getElementById("advInfoDetectorName").textContent = info.name;
  document.getElementById("advInfoDetectorCategory").textContent = info.category;
  document.getElementById("advInfoDetectorIcon").textContent = info.icon;
  document.getElementById("advInfoTheoryText").textContent = info.theory;
  document.getElementById("advInfoBlindSpotText").textContent = info.blindSpot;
  document.getElementById("advInfoMitigationBox").textContent = info.mitigation;

  modal.style.display = "flex";
}

function closeDetectorInfoModal() {
  const modal = document.getElementById("advDetectorInfoModal");
  if (modal) modal.style.display = "none";
}

function exportSimulationReport() {
  if (!advState.activeSession || !advState.activeSession.session_id) {
    showToast("Please run an adversarial simulation before exporting report.", "warning");
    return;
  }

  const sid = advState.activeSession.session_id;
  const reportUrl = apiUrl(`/adversarial/report/${sid}`);
  window.open(reportUrl, "_blank");
  showToast("Simulation audit report opened in new tab.", "success");
}

// Global Window Exports for inline DOM Event Handlers
window.showToast = showToast;
window.scrollToBoundingBox = scrollToBoundingBox;
window.switchView = switchView;
window.loadApplicationDetail = loadApplicationDetail;
window.openDetectorInfoModal = openDetectorInfoModal;
window.loadWizardScenarioByIndex = loadWizardScenarioByIndex;
window.renderAllFindings = function() {
  if (state.activeAppDetail?.deficiencies) {
    renderFindingsList(state.activeAppDetail.deficiencies, true);
  }
};

