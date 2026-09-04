/**
 * CareerGraph AI — Tab 2: Quick Ingest & Apply Controller
 */

import { api } from "../api.js";
import { state } from "../state.js";
import { Toast } from "../components/toast.js";
import { escapeHtml } from "../utils.js";
import { loadKanbanJobs, tailorJobAction, submitJobAction } from "./kanban.js";

export function initQuickApply() {
  document
    .getElementById("btn-quick-ingest-eval")
    ?.addEventListener("click", handleQuickIngestAndEval);
  document
    .getElementById("btn-quick-tailor")
    ?.addEventListener("click", handleQuickTailor);
  document
    .getElementById("btn-quick-submit")
    ?.addEventListener("click", handleQuickSubmit);
}

export async function handleQuickIngestAndEval() {
  const url = document.getElementById("input-job-url")?.value?.trim();
  const company = document.getElementById("input-job-company")?.value?.trim();
  const title = document.getElementById("input-job-title")?.value?.trim();
  const desc = document.getElementById("input-job-desc")?.value?.trim();

  if (!url && (!company || !title)) {
    Toast.warn("Please enter a Job URL or Company & Title.");
    return;
  }

  const btn = document.getElementById("btn-quick-ingest-eval");
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<i data-lucide="loader-2" class="w-4 h-4 animate-spin"></i> <span>Ingesting & Scoring...</span>`;
    if (window.lucide) window.lucide.createIcons({ root: btn });
  }

  try {
    const job = await api.ingestJob({ url, company, title, description: desc });
    state.activeQuickJob = job;

    const evalData = await api.evaluateJob(job.id);
    renderQuickEvalVerdict(job, evalData);
    await loadKanbanJobs();
    Toast.success(`Job ingested & scored: ${evalData.fit_score}/100!`);
  } catch (err) {
    Toast.error("Error: " + err.message);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `<i data-lucide="zap" class="w-4 h-4"></i> <span>Ingest & Run 7-Block Evaluation</span>`;
      if (window.lucide) window.lucide.createIcons({ root: btn });
    }
  }
}

export function renderQuickEvalVerdict(job, evalData) {
  document.getElementById("quick-eval-placeholder")?.classList.add("hidden");
  const resContainer = document.getElementById("quick-eval-results");
  resContainer?.classList.remove("hidden");

  const scorePill = document.getElementById("quick-score-pill");
  if (scorePill) {
    scorePill.classList.remove("hidden");
    scorePill.textContent = `${evalData.fit_score}/100`;
    if (evalData.fit_score >= 85) {
      scorePill.className =
        "px-2.5 py-0.5 rounded-full text-xs font-bold font-mono text-emerald-400 bg-emerald-950/80 border border-emerald-700";
    } else {
      scorePill.className =
        "px-2.5 py-0.5 rounded-full text-xs font-bold font-mono text-rose-400 bg-rose-950/80 border border-rose-700";
    }
  }

  const compTitle = document.getElementById("quick-eval-company-title");
  if (compTitle) compTitle.textContent = `${job.company} — ${job.title}`;
  const portalEl = document.getElementById("quick-eval-portal");
  if (portalEl) portalEl.textContent = job.portal_type || "generic";
  const reasonEl = document.getElementById("quick-eval-reason");
  if (reasonEl)
    reasonEl.textContent = evalData.reason || "Evaluated by 7-Block Rubric Engine.";

  const blocksContainer = document.getElementById("quick-eval-blocks");
  if (blocksContainer) {
    blocksContainer.innerHTML = `
      <div class="p-2.5 bg-[#07090e] rounded-lg border border-white/[0.06]">
        <div class="text-[10px] text-slate-500 uppercase font-semibold">Block A (Seniority)</div>
        <div class="font-bold text-slate-200 truncate mt-0.5">${escapeHtml(job.title)}</div>
      </div>
      <div class="p-2.5 bg-[#07090e] rounded-lg border border-white/[0.06]">
        <div class="text-[10px] text-slate-500 uppercase font-semibold">Block B (CV Fit Score)</div>
        <div class="font-bold ${
          evalData.fit_score >= 85 ? "text-emerald-400" : "text-amber-400"
        } mt-0.5">${evalData.fit_score} / 100</div>
      </div>
      <div class="p-2.5 bg-[#07090e] rounded-lg border border-white/[0.06]">
        <div class="text-[10px] text-slate-500 uppercase font-semibold">Work Auth Verification</div>
        <div class="font-bold ${
          evalData.work_auth_blocker ? "text-rose-400" : "text-emerald-400"
        } mt-0.5">
          ${evalData.work_auth_blocker ? "❌ Blocker Detected" : "✅ Approved I-140"}
        </div>
      </div>
      <div class="p-2.5 bg-[#07090e] rounded-lg border border-white/[0.06]">
        <div class="text-[10px] text-slate-500 uppercase font-semibold">Ghost-Job Guard</div>
        <div class="font-bold ${
          evalData.is_ghost_job ? "text-rose-400" : "text-emerald-400"
        } mt-0.5">
          ${evalData.is_ghost_job ? "⚠️ Ghost Job Risk" : "✅ Legitimate Posting"}
        </div>
      </div>
    `;
  }

  document.getElementById("quick-actions-bar")?.classList.remove("hidden");
  if (window.lucide) window.lucide.createIcons();
}

export async function handleQuickTailor() {
  if (!state.activeQuickJob) return;
  await tailorJobAction(state.activeQuickJob.id);
}

export async function handleQuickSubmit() {
  if (!state.activeQuickJob) return;
  await submitJobAction(state.activeQuickJob.id);
}
