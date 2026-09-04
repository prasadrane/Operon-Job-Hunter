/**
 * CareerGraph AI — Centralized REST API Service
 */

async function request(url, options = {}) {
  const res = await fetch(url, options);
  if (!res.ok) {
    let errorDetail = res.statusText;
    try {
      const errJson = await res.json();
      errorDetail = errJson.detail || errJson.message || errorDetail;
    } catch (e) {
      // ignore
    }
    throw new Error(errorDetail);
  }
  return res.json();
}

export const api = {
  // Jobs & Pipeline
  getJobs: () => request("/api/jobs"),
  getJob: (jobId) => request(`/api/jobs/${jobId}`),
  getEvaluation: (jobId) => request(`/api/jobs/${jobId}/evaluation`),
  getArtifacts: (jobId) => request(`/api/jobs/${jobId}/artifacts`),
  updateJobStatus: (jobId, status) =>
    request(`/api/jobs/${jobId}/status`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    }),
  autoTailorJob: (jobId) =>
    request(`/api/jobs/${jobId}/autotailor`, { method: "POST" }),
  evaluateJob: (jobId) =>
    request(`/api/jobs/${jobId}/evaluate`, { method: "POST" }),
  tailorJob: (jobId, targetPages = 1) =>
    request(`/api/jobs/${jobId}/tailor`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target_pages: targetPages }),
    }),
  submitJob: (jobId, options = {}) =>
    request(`/api/jobs/${jobId}/submit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(options),
    }),
  ingestJob: (data) =>
    request("/api/jobs/ingest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),
  scanJobs: (autoPipeline = true, limitTailor = 5) =>
    request(`/api/jobs/scan?auto_pipeline=${autoPipeline}&limit_tailor=${limitTailor}`, {
      method: "POST",
    }),

  // GraphRAG & Stories
  getStories: () => request("/api/stories"),

  // Agent & Telemetry
  getAgentStatus: () => request("/api/agent/status"),
  getSubagentsStatus: () => request("/api/subagents/status"),
  runSubagentMission: () => request("/api/subagents/run_mission", { method: "POST" }),
  getTelemetryStats: () => request("/api/v2/telemetry/stats"),
  getTelemetrySpans: () => request("/api/v2/telemetry/spans"),

  // Settings, Workday & Analytics
  getSettings: () => request("/api/settings"),
  saveSettings: (settings) =>
    request("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settings),
    }),
  getWorkdayProfile: () => request("/api/profile/workday"),
  saveWorkdayProfile: (profile) =>
    request("/api/profile/workday", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(profile),
    }),
  getAnalytics: () => request("/api/analytics"),
};
