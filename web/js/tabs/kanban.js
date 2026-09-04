/**
 * CareerGraph AI — Tab 1: Pipeline Kanban Board Controller
 */

import { api } from "../api.js";
import { state, events } from "../state.js";
import { Toast } from "../components/toast.js";
import { inspectJob } from "../components/modal.js";
import { escapeHtml, formatTimeAgo, formatSalaryCompact } from "../utils.js";

export function initKanban() {
  initKanbanControls();
  initDragAndDrop();
  events.on("jobs:updated", (jobs) => {
    state.jobs = jobs;
    filterAndRenderKanban();
  });
}

export function initKanbanControls() {
  const searchInput = document.getElementById("kanban-search-input");
  const clearBtn = document.getElementById("btn-clear-search");

  searchInput?.addEventListener("input", (e) => {
    const val = e.target.value;
    if (val) {
      clearBtn?.classList.remove("hidden");
    } else {
      clearBtn?.classList.add("hidden");
    }
    filterAndRenderKanban();
  });

  clearBtn?.addEventListener("click", () => {
    if (searchInput) searchInput.value = "";
    clearBtn.classList.add("hidden");
    filterAndRenderKanban();
  });

  // Portal Pills
  const pills = document.querySelectorAll(".portal-pill");
  pills.forEach((pill) => {
    pill.addEventListener("click", () => {
      pills.forEach((p) => p.classList.remove("active"));
      pill.classList.add("active");
      state.activePortalFilter = pill.getAttribute("data-portal") || "all";
      filterAndRenderKanban();
    });
  });

  // Scan Jobs button
  document.getElementById("btn-trigger-scan")?.addEventListener("click", triggerScan);
}

export function initDragAndDrop() {
  const columns = document.querySelectorAll(".kanban-col");
  columns.forEach((col) => {
    col.addEventListener("dragover", (e) => {
      e.preventDefault();
      col.classList.add("drag-over");
    });

    col.addEventListener("dragleave", () => {
      col.classList.remove("drag-over");
    });

    col.addEventListener("drop", async (e) => {
      e.preventDefault();
      col.classList.remove("drag-over");
      const targetCol = col.getAttribute("data-col");
      const jobId = state.draggedJobId || e.dataTransfer.getData("text/plain");
      if (!jobId || !targetCol) return;

      try {
        await api.updateJobStatus(jobId, targetCol);
        Toast.success(`Job updated to "${targetCol}"`);
        await loadKanbanJobs();
      } catch (err) {
        Toast.error("Failed to update status: " + err.message);
      }
    });
  });
}

export async function loadKanbanJobs() {
  // Show loading skeleton
  showKanbanLoading();

  try {
    const jobs = await api.getJobs();
    state.jobs = jobs || [];
    events.emit("jobs:updated", state.jobs);
  } catch (err) {
    console.error("Error loading jobs:", err);
    Toast.error("Failed to load pipeline jobs: " + err.message);
  } finally {
    hideKanbanLoading();
  }
}

function showKanbanLoading() {
  const cols = ["discovered", "matched", "tailored", "applied", "interviewing", "archived"];
  cols.forEach((colName) => {
    const container = document.getElementById(`cards-${colName}`);
    if (!container) return;
    container.innerHTML = `
      <div class="kanban-skeleton">
        <div class="skeleton-card">
          <div class="skeleton-header">
            <div class="skeleton-avatar"></div>
            <div class="skeleton-lines">
              <div class="skeleton-line w-3/4"></div>
              <div class="skeleton-line w-1/2"></div>
            </div>
          </div>
          <div class="skeleton-line w-full"></div>
          <div class="skeleton-badges">
            <div class="skeleton-badge"></div>
            <div class="skeleton-badge"></div>
            <div class="skeleton-badge"></div>
          </div>
          <div class="skeleton-chips">
            <div class="skeleton-chip"></div>
            <div class="skeleton-chip"></div>
          </div>
        </div>
      </div>
    `;
  });
}

function hideKanbanLoading() {
  // Loading state cleared when renderKanbanBoard is called
}

export function filterAndRenderKanban() {
  const searchEl = document.getElementById("kanban-search-input");
  let rawQuery = (searchEl?.value || "").trim();

  if (rawQuery.includes("@")) {
    if (searchEl) searchEl.value = "";
    document.getElementById("btn-clear-search")?.classList.add("hidden");
    rawQuery = "";
  }

  const query = rawQuery.toLowerCase();
  const portalFilter = state.activePortalFilter.toLowerCase();

  const filtered = state.jobs.filter((job) => {
    const techText = (job.tech_stack || []).join(" ").toLowerCase();
    const skillsText = (job.matched_skills || []).join(" ").toLowerCase();
    const seniorityText = (job.seniority || "").toLowerCase();
    const salaryText = (job.salary_range || "").toLowerCase();

    const matchesSearch =
      !query ||
      (job.company || "").toLowerCase().includes(query) ||
      (job.title || "").toLowerCase().includes(query) ||
      (job.location || "").toLowerCase().includes(query) ||
      (job.portal_type || "").toLowerCase().includes(query) ||
      techText.includes(query) ||
      skillsText.includes(query) ||
      seniorityText.includes(query) ||
      salaryText.includes(query);

    const matchesPortal =
      portalFilter === "all" ||
      (job.portal_type || "generic").toLowerCase().includes(portalFilter);

    return matchesSearch && matchesPortal;
  });

  const totalCountEl = document.getElementById("kanban-total-count");
  const filteredCountEl = document.getElementById("kanban-filtered-count");
  if (totalCountEl) totalCountEl.textContent = state.jobs.length;
  if (filteredCountEl) filteredCountEl.textContent = filtered.length;

  renderKanbanBoard(filtered);
}

export function renderKanbanBoard(jobs) {
  const cols = {
    discovered: [],
    matched: [],
    tailored: [],
    applied: [],
    interviewing: [],
    archived: [],
  };

  jobs.forEach((job) => {
    const st = (job.status || "discovered").toLowerCase();
    if (st === "discovered" || st === "evaluating") {
      cols.discovered.push(job);
    } else if (st === "matched" || st === "match") {
      cols.matched.push(job);
    } else if (st === "tailored" || st === "tailoring") {
      cols.tailored.push(job);
    } else if (st === "applied" || st === "submitting") {
      cols.applied.push(job);
    } else if (st === "interviewing" || st === "assessment" || st === "acknowledged") {
      cols.interviewing.push(job);
    } else {
      cols.archived.push(job);
    }
  });

  document.getElementById("count-discovered").textContent = cols.discovered.length;
  document.getElementById("count-matched").textContent = cols.matched.length;
  document.getElementById("count-tailored").textContent = cols.tailored.length;
  document.getElementById("count-applied").textContent = cols.applied.length;
  document.getElementById("count-interviewing").textContent = cols.interviewing.length;
  document.getElementById("count-archived").textContent = cols.archived.length;
  document.getElementById("badge-kanban-total").textContent = jobs.length;

  for (const [colName, colJobs] of Object.entries(cols)) {
    const container = document.getElementById(`cards-${colName}`);
    if (!container) continue;
    container.innerHTML = "";

    if (colJobs.length === 0) {
      container.innerHTML = `
        <div class="text-[11px] text-slate-500 text-center py-10 border border-dashed border-white/[0.04] rounded-lg">
          No records
        </div>
      `;
      continue;
    }

    const renderLimit = 35;
    const visibleJobs = colJobs.slice(0, renderLimit);

    visibleJobs.forEach((job) => {
      const card = createJobCard(job);
      container.appendChild(card);
    });

    if (colJobs.length > renderLimit) {
      const moreBtn = document.createElement("button");
      moreBtn.className =
        "w-full py-2 text-[11px] text-cyan-400 hover:text-cyan-300 font-mono text-center rounded bg-slate-900/60 border border-slate-800 hover:bg-slate-800 transition";
      moreBtn.innerHTML = `+ ${colJobs.length - renderLimit} more jobs in ${colName}`;
      moreBtn.addEventListener("click", () => {
        moreBtn.remove();
        colJobs.slice(renderLimit).forEach((job) => {
          container.appendChild(createJobCard(job));
        });
        if (window.lucide) window.lucide.createIcons({ root: container });
      });
      container.appendChild(moreBtn);
    }
  }

  if (window.lucide) window.lucide.createIcons();
}

export function createJobCard(job) {
  const card = document.createElement("div");
  card.className = "job-card";
  card.setAttribute("draggable", "true");

  const st = (job.status || "discovered").toLowerCase();
  const companyInitial = (job.company || "C").trim().charAt(0).toUpperCase();
  const locationText = job.location || "US / Remote";
  const fitScore =
    job.fit_score !== undefined && job.fit_score !== null
      ? Math.round(job.fit_score)
      : null;
  const timeAgo = formatTimeAgo(job.posted_at || job.discovered_at);
  const salaryComp = formatSalaryCompact(job.salary_range);
  const seniority = job.seniority || "";

  const matchedSet = new Set((job.matched_skills || []).map((s) => s.trim()));
  const allTech = [...(job.matched_skills || []), ...(job.tech_stack || [])]
    .map((s) => s.trim())
    .filter((v, i, a) => v && a.indexOf(v) === i);

  const displayTech = allTech.slice(0, 3);
  const remainingCount = allTech.length - displayTech.length;

  // Score color logic
  let scoreColor = "neutral";
  let scoreGradient = "from-cyan-500 to-blue-500";
  if (fitScore !== null) {
    if (fitScore >= 80) {
      scoreColor = "excellent";
      scoreGradient = "from-emerald-500 to-teal-400";
    } else if (fitScore >= 70) {
      scoreColor = "good";
      scoreGradient = "from-cyan-500 to-sky-400";
    } else if (fitScore >= 50) {
      scoreColor = "fair";
      scoreGradient = "from-amber-500 to-yellow-400";
    } else {
      scoreColor = "poor";
      scoreGradient = "from-rose-500 to-red-400";
    }
  }

  // Build tooltip content
  const tooltipData = [
    job.h1b_sponsored ? "✓ H-1B Sponsor" : null,
    seniority ? `Level: ${seniority}` : null,
    salaryComp ? `Salary: ${salaryComp}` : null,
    timeAgo ? `Posted: ${timeAgo}` : null,
    allTech.length > 3 ? `Skills: ${allTech.slice(3).join(", ")}` : null,
  ].filter(Boolean);

  card.innerHTML = `
    <!-- Header: Score Ring + Company -->
    <div class="card-header">
      <div class="card-company-section">
        <div class="card-avatar">${companyInitial}</div>
        <div class="card-company-info">
          <div class="card-company">${escapeHtml(job.company || "Company")}</div>
          <div class="card-location">
            <i data-lucide="map-pin" class="w-3 h-3"></i>
            ${escapeHtml(locationText)}
          </div>
        </div>
      </div>
      ${fitScore !== null ? `
        <div class="score-ring score-${scoreColor}" data-tooltip="Fit Score: ${fitScore}%">
          <svg viewBox="0 0 36 36" class="score-ring-svg">
            <path class="score-ring-bg" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
            <path class="score-ring-fill" stroke-dasharray="${fitScore}, 100" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
          </svg>
          <span class="score-ring-text">${fitScore}</span>
        </div>
      ` : ""}
    </div>

    <!-- Title -->
    <div class="card-title">${escapeHtml(job.title || "Software Engineer")}</div>

    <!-- Metadata Row (compact) -->
    <div class="card-meta-row">
      ${job.portal_type ? `<span class="meta-chip portal">${escapeHtml(job.portal_type)}</span>` : ""}
      ${seniority ? `<span class="meta-chip seniority">${escapeHtml(seniority)}</span>` : ""}
      ${salaryComp ? `<span class="meta-chip salary">$${escapeHtml(salaryComp)}</span>` : ""}
      ${job.h1b_sponsored ? `<span class="meta-chip h1b">H-1B</span>` : ""}
    </div>

    <!-- Tech Chips (compact) -->
    ${displayTech.length > 0 ? `
      <div class="card-tech-row">
        ${displayTech.map((t) => {
          const isMatched = matchedSet.has(t);
          return `<span class="tech-chip ${isMatched ? 'matched' : ''}">${escapeHtml(t)}</span>`;
        }).join("")}
        ${remainingCount > 0 ? `<span class="tech-chip more">+${remainingCount}</span>` : ""}
      </div>
    ` : ""}

    <!-- Footer: Actions -->
    <div class="card-footer">
      <button class="card-btn btn-view" data-id="${job.id}">
        <i data-lucide="eye" class="w-3.5 h-3.5"></i>
        <span>View</span>
      </button>
      ${st === "discovered" ? `
        <button class="card-btn btn-primary-action" data-id="${job.id}">
          <i data-lucide="sparkles" class="w-3.5 h-3.5"></i>
          <span>Auto-Tailor</span>
        </button>
      ` : ""}
      ${st === "matched" ? `
        <button class="card-btn btn-primary-action" data-id="${job.id}">
          <i data-lucide="file-text" class="w-3.5 h-3.5"></i>
          <span>Tailor</span>
        </button>
      ` : ""}
      ${st === "tailored" ? `
        <a href="/api/pdf/${job.id}" target="_blank" class="card-btn btn-secondary-action">
          <i data-lucide="file-down" class="w-3.5 h-3.5"></i>
          <span>PDF</span>
        </a>
        <button class="card-btn btn-primary-action" data-id="${job.id}">
          <i data-lucide="send" class="w-3.5 h-3.5"></i>
          <span>Submit</span>
        </button>
      ` : ""}
      ${st === "applied" ? `
        <a href="/api/pdf/${job.id}" target="_blank" class="card-btn btn-secondary-action">
          <i data-lucide="file-down" class="w-3.5 h-3.5"></i>
          <span>PDF</span>
        </a>
      ` : ""}
    </div>

    <!-- Tooltip (hidden by default, shown on hover) -->
    ${tooltipData.length > 0 ? `
      <div class="card-tooltip">
        ${tooltipData.map((item) => `<div>${escapeHtml(item)}</div>`).join("")}
      </div>
    ` : ""}
  `;

  // Drag events
  card.addEventListener("dragstart", (e) => {
    state.draggedJobId = job.id;
    e.dataTransfer.setData("text/plain", job.id);
    card.classList.add("dragging");
  });

  card.addEventListener("dragend", () => {
    card.classList.remove("dragging");
    state.draggedJobId = null;
  });

  // Action clicks
  card.querySelector(".btn-view")?.addEventListener("click", () => inspectJob(job.id));
  card.querySelector(".btn-primary-action")?.addEventListener("click", () => {
    if (st === "discovered") autoTailorJobAction(job.id);
    else if (st === "matched") tailorJobAction(job.id);
    else if (st === "tailored") submitJobAction(job.id);
  });

  return card;
}

export async function autoTailorJobAction(jobId) {
  Toast.info(`Running 1-Click Auto-Tailor on job ${jobId}...`);
  try {
    const data = await api.autoTailorJob(jobId);
    Toast.success(`Tailored ATS Resume generated! Fit Score: ${data.fit_score}/100.`);
    await loadKanbanJobs();
  } catch (err) {
    Toast.error("Auto-tailor error: " + err.message);
  }
}

export async function tailorJobAction(jobId) {
  Toast.info(`Generating tailored ATS Resume for ${jobId}...`);
  try {
    const targetPages = state.settings.resume_target_pages || 1;
    await api.tailorJob(jobId, targetPages);
    Toast.success("Resume tailored! PDF generated & verified.");
    await loadKanbanJobs();
  } catch (err) {
    Toast.error("Tailor error: " + err.message);
  }
}

export async function submitJobAction(jobId) {
  if (!confirm(`Are you sure you want to submit application for job ${jobId}?`)) return;
  Toast.info(`Submitting application for ${jobId}...`);
  try {
    await api.submitJob(jobId, { dry_run: false });
    Toast.success("Application submitted successfully!");
    await loadKanbanJobs();
  } catch (err) {
    Toast.error("Submit error: " + err.message);
  }
}

export async function triggerScan() {
  const btn = document.getElementById("btn-trigger-scan");
  if (!btn) return;
  btn.disabled = true;
  btn.innerHTML = `<i data-lucide="loader-2" class="w-3.5 h-3.5 animate-spin"></i> <span>Running Auto-Pilot...</span>`;
  if (window.lucide) window.lucide.createIcons({ root: btn });

  try {
    const res = await api.scanJobs(true, 5);
    Toast.success(
      `Scan complete! Discovered: ${res.discovered}, Evaluated: ${res.evaluated}, Tailored: ${res.tailored}`
    );
    await loadKanbanJobs();
  } catch (err) {
    Toast.error("Scan failed: " + err.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<i data-lucide="radar" class="w-3.5 h-3.5"></i> <span>Scan Jobs</span>`;
    if (window.lucide) window.lucide.createIcons({ root: btn });
  }
}
