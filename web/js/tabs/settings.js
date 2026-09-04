/**
 * CareerGraph AI — Tab 5: Settings, Workday Autofill & Analytics Controller
 */

import { api } from "../api.js";
import { state } from "../state.js";
import { Toast } from "../components/toast.js";

export function initSettings() {
  const slider = document.getElementById("input-min-score");
  slider?.addEventListener("input", (e) => {
    const val = e.target.value;
    const scoreVal = document.getElementById("setting-score-val");
    if (scoreVal) scoreVal.textContent = val;
  });

  document
    .getElementById("btn-save-settings")
    ?.addEventListener("click", handleSaveSettings);
  document
    .getElementById("btn-save-wd-profile")
    ?.addEventListener("click", handleSaveWorkdayProfile);
}

export async function loadSettings() {
  try {
    const data = await api.getSettings();
    state.settings = data;

    const minScoreEl = document.getElementById("header-min-score");
    if (minScoreEl) minScoreEl.textContent = data.min_fit_score || 85;
    const slider = document.getElementById("input-min-score");
    if (slider) slider.value = data.min_fit_score || 85;
    const scoreVal = document.getElementById("setting-score-val");
    if (scoreVal) scoreVal.textContent = data.min_fit_score || 85;
    const pagesEl = document.getElementById("setting-resume-pages");
    if (pagesEl) pagesEl.value = String(data.resume_target_pages || 1);
  } catch (err) {
    console.error("Error loading settings:", err);
  }
}

export async function loadWorkdayProfile() {
  try {
    const p = await api.getWorkdayProfile();
    state.workdayProfile = p;

    const emailEl = document.getElementById("wd-profile-email");
    if (emailEl && p.email) emailEl.value = p.email;
    const passEl = document.getElementById("wd-profile-password");
    if (passEl && p.password) passEl.value = p.password;
    const phoneEl = document.getElementById("wd-profile-phone");
    if (phoneEl && p.phone) phoneEl.value = p.phone;
    const firstEl = document.getElementById("wd-profile-firstname");
    if (firstEl && p.first_name) firstEl.value = p.first_name;
    const lastEl = document.getElementById("wd-profile-lastname");
    if (lastEl && p.last_name) lastEl.value = p.last_name;
    const addrEl = document.getElementById("wd-profile-address");
    if (addrEl && p.address_line1) addrEl.value = p.address_line1;
    const cityEl = document.getElementById("wd-profile-city");
    if (cityEl && p.city) cityEl.value = p.city;
    const stateEl = document.getElementById("wd-profile-state");
    if (stateEl && p.state) stateEl.value = p.state;
    const zipEl = document.getElementById("wd-profile-zip");
    if (zipEl && p.postal_code) zipEl.value = p.postal_code;
    const authEl = document.getElementById("wd-profile-auth");
    if (authEl) authEl.value = p.is_authorized_us ? "true" : "false";
    const sponsEl = document.getElementById("wd-profile-sponsorship");
    if (sponsEl) sponsEl.value = p.needs_sponsorship_future ? "true" : "false";
    const vetEl = document.getElementById("wd-profile-veteran");
    if (vetEl && p.veteran_status) vetEl.value = p.veteran_status;
  } catch (err) {
    console.error("Error loading Workday profile:", err);
  }
}

export async function handleSaveWorkdayProfile() {
  const profile = {
    email: document.getElementById("wd-profile-email")?.value?.trim() || "",
    password: document.getElementById("wd-profile-password")?.value || "",
    phone: document.getElementById("wd-profile-phone")?.value?.trim() || "",
    first_name: document.getElementById("wd-profile-firstname")?.value?.trim() || "",
    last_name: document.getElementById("wd-profile-lastname")?.value?.trim() || "",
    address_line1: document.getElementById("wd-profile-address")?.value?.trim() || "",
    city: document.getElementById("wd-profile-city")?.value?.trim() || "",
    state: document.getElementById("wd-profile-state")?.value?.trim() || "",
    postal_code: document.getElementById("wd-profile-zip")?.value?.trim() || "",
    is_authorized_us: document.getElementById("wd-profile-auth")?.value === "true",
    needs_sponsorship_future:
      document.getElementById("wd-profile-sponsorship")?.value === "true",
    veteran_status:
      document.getElementById("wd-profile-veteran")?.value || "not_veteran",
  };

  try {
    await api.saveWorkdayProfile(profile);
    Toast.success("Workday Enterprise Autofill Profile saved! Cyber-Pilot is armed.");
  } catch (err) {
    Toast.error("Save profile error: " + err.message);
  }
}

export async function loadSettingsAndAnalytics() {
  await loadSettings();
  await loadWorkdayProfile();
  try {
    const data = await api.getAnalytics();

    const appliedEl = document.getElementById("metric-total-applied");
    if (appliedEl) appliedEl.textContent = data.total_applied || 0;
    const rateEl = document.getElementById("metric-interview-rate");
    if (rateEl) rateEl.textContent = `${data.interview_rate_pct || 0.0}%`;
    const latencyEl = document.getElementById("metric-avg-latency");
    if (latencyEl) latencyEl.textContent = `${data.avg_response_latency_days || 0.0}d`;
    const offersEl = document.getElementById("metric-total-offers");
    if (offersEl) offersEl.textContent = data.total_offers || 0;

    const summaryBox = document.getElementById("analytics-summary-box");
    if (summaryBox) {
      summaryBox.textContent =
        data.summary_markdown || "No applications recorded in ledger yet.";
    }
  } catch (err) {
    console.error("Error loading analytics:", err);
  }
}

export async function handleSaveSettings() {
  const minScore = parseInt(
    document.getElementById("input-min-score")?.value || "85",
    10
  );
  const browserDir = document
    .getElementById("setting-browser-dir")
    ?.value?.trim();

  try {
    await api.saveSettings({
      min_fit_score: minScore,
      browser_profile_dir: browserDir,
    });
    Toast.success("Autonomy thresholds & paths saved successfully!");
    await loadSettings();
  } catch (err) {
    Toast.error("Save settings error: " + err.message);
  }
}
