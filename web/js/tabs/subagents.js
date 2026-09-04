/**
 * CareerGraph AI — Tab 6: 2D Serpentine Platformer Factory Controller
 */

import { api } from "../api.js";
import { Toast } from "../components/toast.js";
import { escapeHtml } from "../utils.js";
import { initFactory } from "../../factory/index.js";

let factoryInstance = null;
let sseSource = null;

export function initSubagentOffice() {
  const btnStandup = document.getElementById("btn-office-standup");
  const btnSprint = document.getElementById("btn-office-sprint");
  const btnScan = document.getElementById("btn-factory-scan");
  const btnCenter = document.getElementById("btn-factory-center");
  const btnZoomIn = document.getElementById("btn-zoom-in");
  const btnZoomOut = document.getElementById("btn-zoom-out");
  const btnHighContrast = document.getElementById("btn-high-contrast");
  const btnReducedMotion = document.getElementById("btn-reduced-motion");
  const dialogueEl = document.getElementById("office-standup-dialogue");
  const neuralStream = document.getElementById("office-neural-stream");

  // 1. Initialize PixiJS 2D Serpentine Platformer Engine
  try {
    if (document.getElementById("factory-canvas")) {
      factoryInstance = initFactory({ force: true });
      window.factoryInstance = factoryInstance;
    }
  } catch (err) {
    console.warn("Could not initialize 2D Platformer Factory Visualization:", err);
  }

  // 2. Setup Server-Sent Events (SSE) Real-Time Telemetry Stream for HUD
  connectSubagentHUDStream(dialogueEl, neuralStream);

  // 3. Stage & Tier Quick Focus Controls
  document.getElementById("zone-focus-discovery")?.addEventListener("click", () => {
    factoryInstance?.camera?.panTo(0, 60);
    Toast.info("🛰️ Tier 1: Discovery Wing focused");
  });

  document.getElementById("zone-focus-eval")?.addEventListener("click", () => {
    factoryInstance?.camera?.panTo(0, 155);
    Toast.info("⚖️ Tier 2: Evaluation Lab focused");
  });

  document.getElementById("zone-focus-tailoring")?.addEventListener("click", () => {
    factoryInstance?.camera?.panTo(0, 250);
    Toast.info("📜 Tier 3: Tailoring Workshop focused");
  });

  document.getElementById("zone-focus-submission")?.addEventListener("click", () => {
    factoryInstance?.camera?.panTo(0, 345);
    Toast.info("🚀 Tier 4: Submission Dispatch Bay focused");
  });

  document.getElementById("zone-focus-lifecycle")?.addEventListener("click", () => {
    factoryInstance?.camera?.panTo(0, 440);
    Toast.info("👑 Tier 5: Command HQ & Lifecycle focused");
  });

  // 4. Zoom & Viewport Controls
  btnZoomIn?.addEventListener("click", () => {
    if (!factoryInstance?.camera) return;
    factoryInstance.camera.zoomBy(0.18);
    Toast.info(`🔍 Zoom In: ${Math.round(factoryInstance.camera.scale * 100)}%`);
  });

  btnZoomOut?.addEventListener("click", () => {
    if (!factoryInstance?.camera) return;
    factoryInstance.camera.zoomBy(-0.18);
    Toast.info(`🔍 Zoom Out: ${Math.round(factoryInstance.camera.scale * 100)}%`);
  });

  btnCenter?.addEventListener("click", () => {
    if (!factoryInstance?.camera) return;
    factoryInstance.camera.setZoom(0.88);
    factoryInstance.camera.panTo(0, 250);
    Toast.info("🎯 View reset to 100% plant fit");
  });

  // 5. Accessibility Controls
  btnHighContrast?.addEventListener("click", () => {
    document.body.classList.toggle("factory-high-contrast");
    const active = document.body.classList.contains("factory-high-contrast");
    btnHighContrast.classList.toggle("bg-cyan-700", active);
    btnHighContrast.classList.toggle("text-white", active);
    Toast.info(active ? "◐ High contrast mode enabled" : "◐ Normal contrast restored");
  });

  btnReducedMotion?.addEventListener("click", () => {
    if (!factoryInstance?.motionGate) return;
    const current = factoryInstance.motionGate.reducedMotion;
    factoryInstance.motionGate.setReducedMotion(!current);
    const active = factoryInstance.motionGate.reducedMotion;
    btnReducedMotion.classList.toggle("bg-cyan-700", active);
    btnReducedMotion.classList.toggle("text-white", active);
    Toast.info(active ? "⏱ Slow-Mo / Reduced motion enabled" : "⏱ Normal animation speed restored");
  });

  // 6. Scan Button Click
  btnScan?.addEventListener("click", async () => {
    Toast.info("🛰️ Triggering live discovery scan across job portals...");
    btnScan.disabled = true;
    try {
      const res = await fetch("/api/v2/discovery/scan", { method: "POST" });
      const data = await res.json();
      Toast.success(data.message || "Discovery scan completed!");
    } catch (err) {
      Toast.error("Scan error: " + err.message);
    } finally {
      setTimeout(() => { btnScan.disabled = false; }, 3000);
    }
  });

  // 7. Standup Meeting
  btnStandup?.addEventListener("click", async () => {
    Toast.success("📣 Standup meeting called! Apex assembling all subagents.");
    const badge = document.getElementById("standup-status-badge");
    if (badge) {
      badge.textContent = "⚡ Standup Active: Commander Apex Briefing";
      badge.className =
        "text-[10px] font-mono px-2 py-0.5 rounded bg-amber-950 text-amber-300 border border-amber-700/50 animate-pulse";
    }

    if (dialogueEl) {
      dialogueEl.innerHTML = `<span class="text-amber-400 font-bold">[Commander Apex]:</span> "Factory standup in session! 5-tier serpentine platformer online, all state machines monotonic."`;
    }

    if (factoryInstance?.standup) {
      factoryInstance.standup.show?.({
        speaker: "Commander Apex",
        text: "2D platformer assembly line running at 60 FPS. Stage 0 Triage active.",
      });
      setTimeout(() => {
        factoryInstance.standup.hide?.();
        if (badge) badge.textContent = "⚡ SSE Stream Active";
      }, 10000);
    }
  });

  // 8. Run Autonomous Sprint / Mission
  btnSprint?.addEventListener("click", async () => {
    Toast.info("🚀 Commander Apex awakened subagents and launched Autonomous Mission...");
    btnSprint.disabled = true;

    try {
      await api.runSubagentMission();
      Toast.success("Autonomous Mission underway! Watch job cartridges travel down the 5 conveyor tiers.");
    } catch (err) {
      Toast.error("Mission error: " + err.message);
    } finally {
      setTimeout(() => {
        btnSprint.disabled = false;
      }, 6000);
    }
  });
}

function connectSubagentHUDStream(dialogueEl, neuralStream) {
  try {
    sseSource = new EventSource("/api/v2/subagents/stream");

    sseSource.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        const evType = payload.event;

        if (evType === "subagents_snapshot" && payload.data) {
          const snap = payload.data;
          if (dialogueEl && snap.orchestrator_speech) {
            dialogueEl.innerHTML = `<span class="text-amber-400 font-bold">[Commander Apex]:</span> "${escapeHtml(
              snap.orchestrator_speech
            )}"`;
          }
        } else if (evType === "agent_update" && payload.data) {
          const update = payload.data;
          if (dialogueEl && update.orchestrator_speech) {
            dialogueEl.innerHTML = `<span class="text-amber-400 font-bold">[Commander Apex]:</span> "${escapeHtml(
              update.orchestrator_speech
            )}"`;
          }
        } else if (evType === "log" && payload.data && neuralStream) {
          const entry = document.createElement("div");
          entry.className =
            "flex items-start gap-2 text-cyan-300 font-mono text-[11px] animate-fadeIn";
          entry.innerHTML = `<span>[${new Date(
            payload.data.timestamp
          ).toLocaleTimeString()}]</span> <span>${escapeHtml(
            payload.data.message
          )}</span>`;
          neuralStream.prepend(entry);
        }
      } catch (e) {
        // ignore parsing glitch
      }
    };

    sseSource.onerror = () => {
      if (sseSource) sseSource.close();
      setTimeout(() => connectSubagentHUDStream(dialogueEl, neuralStream), 5000);
    };
  } catch (e) {
    console.warn("HUD SSE stream unsupported:", e);
  }
}

export async function fetchSubagentsLiveStatus() {
  try {
    const data = await api.getSubagentsStatus();
    const dialogueEl = document.getElementById("office-standup-dialogue");
    if (dialogueEl && data.orchestrator_speech) {
      dialogueEl.innerHTML = `<span class="text-amber-400 font-bold">[Commander Apex]:</span> "${escapeHtml(
        data.orchestrator_speech
      )}"`;
    }
  } catch (err) {
    console.error("Error fetching subagents live status:", err);
  }
}
