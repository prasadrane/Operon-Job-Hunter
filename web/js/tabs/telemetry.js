/**
 * CareerGraph AI — Tab 4: Live Agent Telemetry & Logs Controller
 */

import { api } from "../api.js";
import { state } from "../state.js";
import { Toast } from "../components/toast.js";
import { escapeHtml } from "../utils.js";

export function initTelemetry() {
  document
    .getElementById("log-filter-level")
    ?.addEventListener("change", renderTelemetryLogs);
  document
    .getElementById("btn-trigger-email-sync")
    ?.addEventListener("click", handleTriggerEmailSync);
}

export async function refreshAgentStatus() {
  try {
    const data = await api.getAgentStatus();
    state.agentLogsCache = data.logs || [];
    renderTelemetryLogs();
  } catch (err) {
    console.debug("Agent status poll error:", err);
  }

  await loadAgenticGuardrailsTelemetry();
}

export async function loadAgenticGuardrailsTelemetry() {
  try {
    const res = await fetch("/api/v2/telemetry/agentic_guardrails");
    if (!res.ok) return;
    const data = await res.json();

    const consensusRateEl = document.getElementById("telemetry-consensus-rate");
    if (consensusRateEl && data.consensus_voting) {
      consensusRateEl.textContent = `${(
        data.consensus_voting.agreement_rate * 100
      ).toFixed(1)}% Agreement`;
    }

    const consensusConfEl = document.getElementById("telemetry-consensus-conf");
    if (consensusConfEl && data.consensus_voting) {
      consensusConfEl.textContent = `Conf: ${data.consensus_voting.avg_confidence}`;
    }

    const cbStatusEl = document.getElementById("telemetry-cb-status");
    if (cbStatusEl && data.circuit_breakers) {
      cbStatusEl.textContent = `Active (${data.circuit_breakers.timeout_threshold_seconds}s Budget)`;
    }

    const cbStallsEl = document.getElementById("telemetry-cb-stalls");
    if (cbStallsEl && data.circuit_breakers) {
      cbStallsEl.textContent = `${data.circuit_breakers.stalls_intercepted} Stalls`;
    }

    const cpDriverEl = document.getElementById("telemetry-cp-driver");
    if (cpDriverEl && data.checkpoint_efficiency) {
      const driverName =
        data.checkpoint_efficiency.driver === "sqlite"
          ? "SqliteSaver"
          : `${data.checkpoint_efficiency.driver}Saver`;
      cpDriverEl.textContent = `${driverName} (WAL)`;
    }

    const cpSizeEl = document.getElementById("telemetry-cp-size");
    if (cpSizeEl && data.checkpoint_efficiency) {
      cpSizeEl.textContent = `~${data.checkpoint_efficiency.avg_snapshot_size_kb} KB State`;
    }

    const regCountEl = document.getElementById("telemetry-registry-count");
    if (regCountEl && data.crawler_registry) {
      regCountEl.textContent = `${data.crawler_registry.total_tools} Dynamic Tools`;
    }
  } catch (err) {
    console.debug("Agentic guardrails telemetry error:", err);
  }
}

export function renderTelemetryLogs() {
  const logsContainer = document.getElementById("live-logs-box");
  if (!logsContainer) return;

  const levelFilter =
    document.getElementById("log-filter-level")?.value || "ALL";

  const filteredLogs = state.agentLogsCache.filter((log) => {
    if (levelFilter === "ALL") return true;
    return (log.level || "INFO").toUpperCase() === levelFilter;
  });

  if (filteredLogs.length === 0) {
    logsContainer.innerHTML = `<div class="text-slate-600 text-center py-8">No log entries matching level "${levelFilter}".</div>`;
    return;
  }

  logsContainer.innerHTML = filteredLogs
    .slice()
    .reverse()
    .map((log) => {
      let lvlColor = "text-cyan-400 bg-cyan-950/80 border-cyan-800";
      if (log.level === "WARNING")
        lvlColor = "text-amber-400 bg-amber-950/80 border-amber-800";
      if (log.level === "ERROR")
        lvlColor = "text-rose-400 bg-rose-950/80 border-rose-800 font-bold";
      return `
        <div class="flex items-start gap-2.5 py-1.5 border-b border-white/[0.04] hover:bg-white/[0.02] px-1 rounded transition">
          <span class="text-slate-500 text-[10px] font-mono pt-0.5">${(
            log.timestamp || ""
          ).slice(11, 19)}</span>
          <span class="${lvlColor} text-[10px] px-1.5 py-0.5 rounded border font-mono">[${
        log.level || "INFO"
      }]</span>
          <span class="text-slate-200 text-xs font-mono flex-1 leading-relaxed">${escapeHtml(
            log.message || ""
          )}</span>
        </div>
      `;
    })
    .join("");
}

export async function handleTriggerEmailSync() {
  const btn = document.getElementById("btn-trigger-email-sync");
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<i data-lucide="loader-2" class="w-3.5 h-3.5 animate-spin"></i> <span>Syncing...</span>`;
    if (window.lucide) window.lucide.createIcons({ root: btn });
  }

  try {
    await api.getAnalytics();
    Toast.success(
      "Gmail synchronization complete! Applications and lifecycle updated."
    );
  } catch (e) {
    Toast.error("Email sync error: " + e.message);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `<i data-lucide="mail-check" class="w-3.5 h-3.5 text-cyan-400"></i> <span>Sync Gmail Status</span>`;
      if (window.lucide) window.lucide.createIcons({ root: btn });
    }
  }
}
