/**
 * CareerGraph AI — Tab 3: GraphRAG Story Explorer Controller
 */

import { api } from "../api.js";
import { Toast } from "../components/toast.js";
import { escapeHtml } from "../utils.js";

let graphragData = { metrics: [], skills: [], stories: [] };

export function initGraphRAG() {
  document
    .getElementById("graphrag-search-input")
    ?.addEventListener("input", filterGraphRAGContent);
}

export async function loadGraphRAGStories() {
  try {
    const data = await api.getStories();
    graphragData = data || { metrics: [], skills: [], stories: [] };
    renderGraphRAGContent(graphragData);
  } catch (err) {
    console.error("Error loading GraphRAG stories:", err);
    Toast.error("Failed to load GraphRAG ledger: " + err.message);
  }
}

export function filterGraphRAGContent() {
  const query = (
    document.getElementById("graphrag-search-input")?.value || ""
  )
    .toLowerCase()
    .trim();

  if (!query) {
    renderGraphRAGContent(graphragData);
    return;
  }

  const filteredStories = (graphragData.stories || []).filter((st) => {
    return (
      (st.story_title || st.title || "").toLowerCase().includes(query) ||
      (st.company || "").toLowerCase().includes(query) ||
      (st.bullets || []).some((b) => b.toLowerCase().includes(query))
    );
  });

  const filteredSkills = (graphragData.skills || []).filter((s) =>
    s.toLowerCase().includes(query)
  );

  renderGraphRAGContent({
    metrics: graphragData.metrics || [],
    skills: filteredSkills,
    stories: filteredStories,
  });
}

export function renderGraphRAGContent(data) {
  // Render Metrics
  const metricsEl = document.getElementById("metrics-container");
  if (metricsEl && data.metrics) {
    metricsEl.innerHTML = data.metrics
      .map(
        (m) =>
          `<span class="px-3 py-1.5 rounded-lg bg-cyan-950/60 border border-cyan-800/80 text-cyan-300 font-mono text-xs font-semibold shadow-sm hover:border-cyan-400 transition cursor-default">${escapeHtml(
            m
          )}</span>`
      )
      .join("");
  }

  // Render Skills
  const skillsEl = document.getElementById("skills-container");
  if (skillsEl && data.skills) {
    skillsEl.innerHTML = data.skills
      .map(
        (s) =>
          `<span class="px-2.5 py-1 rounded-md bg-[#07090e] text-slate-300 text-xs border border-white/[0.08] hover:border-indigo-400 transition cursor-default font-mono">${escapeHtml(
            s
          )}</span>`
      )
      .join("");
  }

  // Render STAR Stories
  const storiesEl = document.getElementById("stories-container");
  if (storiesEl && data.stories) {
    if (data.stories.length === 0) {
      storiesEl.innerHTML = `<div class="col-span-2 text-center py-8 text-slate-500 border border-dashed border-white/[0.04] rounded-lg">No matching STAR stories found.</div>`;
      return;
    }

    storiesEl.innerHTML = data.stories
      .map(
        (st) => `
        <div class="bg-[#0d121f] border border-white/[0.08] rounded-xl p-5 space-y-3 shadow-lg hover:border-purple-500/40 transition">
          <div class="flex items-center justify-between border-b border-white/[0.06] pb-2.5">
            <span class="text-xs font-bold text-cyan-400 font-mono flex items-center gap-1.5">
              <i data-lucide="bookmark" class="w-3.5 h-3.5 text-purple-400"></i> ${escapeHtml(
                st.story_title || st.title
              )}
            </span>
            <span class="text-[11px] text-slate-400 font-mono px-2 py-0.5 rounded bg-[#07090e] border border-white/[0.04]">${escapeHtml(
              st.company || "Career Ledger"
            )}</span>
          </div>
          <div class="text-xs text-slate-300 space-y-2 leading-relaxed">
            ${(st.bullets || [])
              .map(
                (b) => `
              <div class="flex items-start gap-2">
                <span class="text-cyan-400 font-bold">•</span>
                <span>${escapeHtml(b)}</span>
              </div>
            `
              )
              .join("")}
          </div>
        </div>
      `
      )
      .join("");
  }

  if (window.lucide) window.lucide.createIcons();
}
