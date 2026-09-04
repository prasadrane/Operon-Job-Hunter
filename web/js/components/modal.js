/**
 * CareerGraph AI — Job Dossier & 7-Block Rubric Inspector Modal
 */

import { api } from "../api.js";
import { state } from "../state.js";
import { escapeHtml, formatCleanJobDescription } from "../utils.js";

export async function inspectJob(jobId) {
  const modal = document.getElementById("modal-container");
  const modalTitle = document.getElementById("modal-title");
  const modalBody = document.getElementById("modal-body");
  if (!modal || !modalTitle || !modalBody) return;

  modalTitle.textContent = "Loading Job Dossier...";
  modalBody.innerHTML = `
    <div class="text-center py-12 text-slate-500 flex flex-col items-center gap-2">
      <i data-lucide="loader-2" class="w-6 h-6 animate-spin text-cyan-400"></i>
      <span>Fetching job, rubric evaluation, and tailored artifacts...</span>
    </div>
  `;
  if (window.lucide) window.lucide.createIcons({ root: modalBody });

  modal.classList.remove("hidden");
  modal.classList.add("flex");

  try {
    const [jobRes, evalRes, artRes] = await Promise.all([
      api.getJob(jobId).catch(() => null),
      api.getEvaluation(jobId).catch(() => null),
      api.getArtifacts(jobId).catch(() => null),
    ]);

    if (!jobRes) throw new Error("Job details could not be loaded.");
    state.activeModalJob = jobRes;

    modalTitle.textContent = `${jobRes.company} — ${jobRes.title}`;

    modalBody.innerHTML = `
      <!-- Tab Content 1: Overview & JD -->
      <div id="modal-tab-details" class="modal-tab-content space-y-4">
        <div class="grid grid-cols-1 sm:grid-cols-3 gap-2.5 p-3.5 rounded-xl bg-[#07090e] border border-white/[0.08] text-xs">
          <div>
            <span class="text-slate-500 font-semibold block">Portal Engine</span>
            <span class="font-mono text-cyan-400 text-xs font-bold uppercase">${escapeHtml(
              jobRes.portal_type || "generic"
            )}</span>
          </div>
          <div>
            <span class="text-slate-500 font-semibold block">Lifecycle Status</span>
            <span class="font-mono text-slate-200 text-xs font-bold">${escapeHtml(
              jobRes.status || "discovered"
            )}</span>
          </div>
          <div>
            <span class="text-slate-500 font-semibold block">Location</span>
            <span class="text-slate-200 text-xs">${escapeHtml(
              jobRes.location || "United States / Remote"
            )}</span>
          </div>
        </div>

        <div class="space-y-1.5">
          <div class="flex items-center justify-between">
            <span class="font-bold text-slate-200 text-xs uppercase tracking-wider">Job Description</span>
            <a href="${escapeHtml(
              jobRes.url
            )}" target="_blank" class="text-cyan-400 hover:underline text-[11px] flex items-center gap-1 font-mono">
              <i data-lucide="external-link" class="w-3 h-3"></i> Open Posting
            </a>
          </div>
          <div class="max-h-64 overflow-y-auto whitespace-pre-wrap font-mono text-[11px] text-slate-300 bg-[#07090e] p-3 rounded-lg border border-white/[0.06] leading-relaxed select-text">
            ${escapeHtml(formatCleanJobDescription(jobRes.description))}
          </div>
        </div>
      </div>

      <!-- Tab Content 2: 7-Block Rubric -->
      <div id="modal-tab-eval" class="modal-tab-content hidden space-y-4">
        ${
          evalRes
            ? `
          <div class="p-4 rounded-xl bg-[#07090e] border border-white/[0.08] space-y-4">
            <div class="flex items-center justify-between">
              <div>
                <span class="font-bold text-slate-100 text-sm block">7-Block Evaluation Dossier</span>
                <span class="text-[11px] text-slate-400">Evaluated on ${
                  evalRes.evaluated_at
                    ? new Date(evalRes.evaluated_at).toLocaleDateString()
                    : "Active Batch"
                }</span>
              </div>
              <span class="font-mono font-black text-sm px-3 py-1 rounded-full ${
                evalRes.fit_score >= 80
                  ? "bg-emerald-950/90 text-emerald-400 border border-emerald-700"
                  : "bg-amber-950/90 text-amber-400 border border-amber-700"
              }">${evalRes.fit_score}/100</span>
            </div>

            <div class="text-slate-300 text-xs leading-relaxed bg-[#0d121f] p-3.5 rounded-lg border border-white/[0.04]">
              <span class="text-slate-400 font-semibold block text-[11px] uppercase tracking-wider mb-1">Executive Summary</span>
              ${escapeHtml(evalRes.reason || "Evaluation completed successfully.")}
            </div>

            ${
              evalRes.block_scores
                ? `
              <div class="grid grid-cols-1 md:grid-cols-2 gap-3 pt-2">
                <!-- Block A & B: Tech Stack & Skills Match -->
                <div class="p-3 rounded-lg bg-[#0d121f] border border-white/[0.04] space-y-2">
                  <div class="flex items-center justify-between">
                    <span class="text-xs font-bold text-cyan-400 flex items-center gap-1.5">
                      <i data-lucide="cpu" class="w-3.5 h-3.5"></i> Required Tech & Skills
                    </span>
                    ${
                      evalRes.block_scores.block_b?.match_score !== undefined
                        ? `
                      <span class="text-[10px] font-mono font-bold text-slate-300">Match: ${evalRes.block_scores.block_b.match_score}/100</span>
                    `
                        : ""
                    }
                  </div>
                  
                  ${
                    evalRes.block_scores.block_b?.matched_skills?.length
                      ? `
                    <div>
                      <span class="text-[10px] text-slate-500 font-semibold block mb-1">Verified Matching Skills:</span>
                      <div class="flex flex-wrap gap-1">
                        ${evalRes.block_scores.block_b.matched_skills
                          .map(
                            (s) =>
                              `<span class="tech-chip matched"><i data-lucide="check" class="w-2.5 h-2.5"></i> ${escapeHtml(
                                s
                              )}</span>`
                          )
                          .join("")}
                      </div>
                    </div>
                  `
                      : ""
                  }

                  ${
                    evalRes.block_scores.block_b?.missing_skills?.length
                      ? `
                    <div class="pt-1">
                      <span class="text-[10px] text-rose-400 font-semibold block mb-1">Skill Gaps:</span>
                      <div class="flex flex-wrap gap-1">
                        ${evalRes.block_scores.block_b.missing_skills
                          .map(
                            (s) =>
                              `<span class="tech-chip gap">${escapeHtml(s)}</span>`
                          )
                          .join("")}
                      </div>
                    </div>
                  `
                      : ""
                  }
                </div>

                <!-- Block C & D: Seniority & Compensation -->
                <div class="p-3 rounded-lg bg-[#0d121f] border border-white/[0.04] space-y-2.5">
                  <div>
                    <span class="text-xs font-bold text-amber-400 flex items-center gap-1.5 mb-1">
                      <i data-lucide="briefcase" class="w-3.5 h-3.5"></i> Level & Compensation
                    </span>
                    <div class="grid grid-cols-2 gap-2 text-xs pt-1">
                      <div class="bg-[#07090e] p-2 rounded border border-white/[0.04]">
                        <span class="text-slate-500 text-[10px] block">Seniority Fit</span>
                        <span class="font-semibold text-slate-200 text-[11px]">${escapeHtml(
                          evalRes.block_scores.block_c?.level_fit ||
                            evalRes.block_scores.block_a?.seniority_level ||
                            "Mid-Senior"
                        )}</span>
                      </div>
                      <div class="bg-[#07090e] p-2 rounded border border-white/[0.04]">
                        <span class="text-slate-500 text-[10px] block">Salary Band</span>
                        <span class="font-semibold text-amber-300 font-mono text-[11px]">${escapeHtml(
                          evalRes.block_scores.block_d?.salary_range || "Market Rate"
                        )}</span>
                      </div>
                    </div>
                  </div>

                  <!-- Block G: Ghost Job & Work Auth -->
                  <div class="pt-1 border-t border-white/[0.04] flex items-center justify-between text-[11px]">
                    <span class="text-slate-400 flex items-center gap-1">
                      <i data-lucide="shield-check" class="w-3.5 h-3.5 text-emerald-400"></i> Ghost Guard:
                      <span class="text-slate-200 font-medium">${
                        evalRes.is_ghost_job ? "⚠️ Flagged" : "Active & Verified"
                      }</span>
                    </span>
                    <span class="text-slate-400 flex items-center gap-1">
                      <i data-lucide="user-check" class="w-3.5 h-3.5 text-cyan-400"></i> Work Auth:
                      <span class="text-slate-200 font-medium">${
                        evalRes.work_auth_blocker ? "❌ Blocker" : "✅ Eligible"
                      }</span>
                    </span>
                  </div>
                </div>
              </div>
            `
                : ""
            }
          </div>
        `
            : `
          <div class="p-8 text-center text-slate-500 border border-dashed border-white/[0.06] rounded-xl">
            No Stage 2 evaluation has been executed for this job yet. Click "Auto-Tailor" or run batch evaluation to score this posting.
          </div>
        `
        }
      </div>

      <!-- Tab Content 3: Tailored Artifacts -->
      <div id="modal-tab-artifacts" class="modal-tab-content hidden space-y-4">
        ${
          artRes
            ? `
          <div class="p-4 rounded-xl bg-[#07090e] border border-white/[0.08] space-y-3">
            <span class="font-bold text-slate-200 text-sm block">Generated ATS PDF Resume</span>
            <div class="flex gap-2">
              <a href="/api/pdf/${jobId}" target="_blank" class="btn-primary text-xs px-4 py-2 flex items-center gap-2">
                <i data-lucide="file-down" class="w-4 h-4"></i> View / Download ATS Resume PDF
              </a>
            </div>
          </div>
        `
            : `
          <div class="p-8 text-center text-slate-500 border border-dashed border-white/[0.06] rounded-xl">
            No tailored ATS resume has been generated for this job yet. Click "Tailor" on the Kanban card to render one.
          </div>
        `
        }
      </div>
    `;

    if (window.lucide) window.lucide.createIcons({ root: modalBody });
  } catch (err) {
    modalBody.innerHTML = `<div class="text-rose-400 p-4 text-xs font-mono">Error loading job details: ${escapeHtml(
      err.message
    )}</div>`;
  }
}

export function closeModal() {
  const modal = document.getElementById("modal-container");
  modal?.classList.remove("flex");
  modal?.classList.add("hidden");
}
