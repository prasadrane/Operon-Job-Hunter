/**
 * CareerGraph AI — Main Application Entrypoint (ES Module)
 * Powered by @ui-styling and @ui-ux-pro-max guidelines
 */

import { Toast } from "./components/toast.js";
import { closeModal } from "./components/modal.js";
import { initKanban, loadKanbanJobs } from "./tabs/kanban.js";
import { initQuickApply } from "./tabs/quick_apply.js";
import { initGraphRAG, loadGraphRAGStories } from "./tabs/graphrag.js";
import { initTelemetry, refreshAgentStatus } from "./tabs/telemetry.js";
import { initSettings, loadSettingsAndAnalytics } from "./tabs/settings.js";
import { initSubagentOffice, fetchSubagentsLiveStatus } from "./tabs/subagents.js";

// Make Toast and closeModal globally accessible for legacy HTML onclicks if needed
window.Toast = Toast;
window.closeModal = closeModal;

document.addEventListener("DOMContentLoaded", () => {
  Toast.init();
  initNavigationTabs();
  initGlobalControls();

  // Initialize Tab Controllers
  initKanban();
  initQuickApply();
  initGraphRAG();
  initTelemetry();
  initSettings();
  initSubagentOffice();

  // Initial Data Fetch
  loadAllData();

  if (window.lucide) {
    window.lucide.createIcons();
  }
});

function initNavigationTabs() {
  const tabs = document.querySelectorAll(".nav-tab");
  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      tabs.forEach((t) => t.classList.remove("active"));
      document
        .querySelectorAll(".tab-pane")
        .forEach((p) => p.classList.remove("active", "hidden"));
      document
        .querySelectorAll(".tab-pane")
        .forEach((p) => p.classList.add("hidden"));

      tab.classList.add("active");
      const targetId = tab.getAttribute("data-tab");
      const targetPane = document.getElementById(targetId);
      if (targetPane) {
        targetPane.classList.remove("hidden");
        targetPane.classList.add("active");
      }

      // Tab specific triggers
      if (targetId === "tab-graphrag") loadGraphRAGStories();
      if (targetId === "tab-live-agent") refreshAgentStatus();
      if (targetId === "tab-settings") loadSettingsAndAnalytics();
      if (targetId === "tab-subagent-office") {
        fetchSubagentsLiveStatus();
        if (window.factory?.resize) window.factory.resize();
      }

      if (window.lucide) window.lucide.createIcons();
    });
  });
}

function initGlobalControls() {
  document
    .getElementById("btn-refresh-all")
    ?.addEventListener("click", () => {
      loadAllData();
      Toast.info("Refreshing all pipeline & agent data...");
    });

  // Modal close handlers
  document.getElementById("btn-close-modal")?.addEventListener("click", closeModal);
  document.getElementById("modal-container")?.addEventListener("click", (e) => {
    if (e.target.id === "modal-container") closeModal();
  });

  // Modal sub-tab navigation
  const modalTabs = document.querySelectorAll(".modal-tab");
  modalTabs.forEach((btn) => {
    btn.addEventListener("click", () => {
      modalTabs.forEach((b) => {
        b.classList.remove("active", "text-cyan-400", "border-b-2", "border-cyan-400", "font-semibold");
        b.classList.add("text-slate-400", "font-medium");
      });
      document
        .querySelectorAll(".modal-tab-content")
        .forEach((c) => c.classList.add("hidden"));

      btn.classList.add("active", "text-cyan-400", "border-b-2", "border-cyan-400", "font-semibold");
      btn.classList.remove("text-slate-400", "font-medium");
      const target = btn.getAttribute("data-target");
      const content = document.getElementById(target);
      if (content) content.classList.remove("hidden");
      if (window.lucide) window.lucide.createIcons();
    });
  });
}

async function loadAllData() {
  await Promise.all([
    loadKanbanJobs(),
    loadGraphRAGStories(),
    refreshAgentStatus(),
    loadSettingsAndAnalytics(),
    fetchSubagentsLiveStatus(),
  ]);
}
