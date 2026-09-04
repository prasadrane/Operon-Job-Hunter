/**
 * CareerGraph AI — Shared Application State & Event Bus
 */

export const state = {
  jobs: [],
  activeQuickJob: null,
  agentLogsCache: [],
  activeModalJob: null,
  activePortalFilter: "all",
  draggedJobId: null,
  settings: {
    min_fit_score: 85,
    resume_target_pages: 1,
    browser_profile_dir: "./data/browser_profile",
  },
  workdayProfile: null,
  agentStatus: "Autonomous Ready",
  subagentsStatus: {},
};

// Lightweight Event Bus for cross-module coordination
class EventBus {
  constructor() {
    this.listeners = {};
  }

  on(event, callback) {
    if (!this.listeners[event]) this.listeners[event] = [];
    this.listeners[event].push(callback);
    return () => this.off(event, callback);
  }

  off(event, callback) {
    if (!this.listeners[event]) return;
    this.listeners[event] = this.listeners[event].filter((cb) => cb !== callback);
  }

  emit(event, data) {
    if (!this.listeners[event]) return;
    this.listeners[event].forEach((cb) => {
      try {
        cb(data);
      } catch (err) {
        console.error(`[EventBus] Error in listener for ${event}:`, err);
      }
    });
  }
}

export const events = new EventBus();
