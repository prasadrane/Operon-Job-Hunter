/**
 * CareerGraph AI — Toast Notification Engine
 */

import { escapeHtml } from "../utils.js";

export const Toast = {
  container: null,

  init() {
    this.container = document.getElementById("toast-container");
  },

  show(message, type = "info", duration = 4000) {
    if (!this.container) this.init();
    if (!this.container) return;

    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;

    let iconName = "info";
    if (type === "success") iconName = "check-circle";
    if (type === "error") iconName = "alert-circle";
    if (type === "warn") iconName = "alert-triangle";

    toast.innerHTML = `
      <i data-lucide="${iconName}" class="w-4 h-4 flex-shrink-0 mt-0.5 ${
      type === "success"
        ? "text-emerald-400"
        : type === "error"
        ? "text-rose-400"
        : type === "warn"
        ? "text-amber-400"
        : "text-cyan-400"
    }"></i>
      <div class="flex-1 text-xs leading-relaxed font-medium">${escapeHtml(message)}</div>
      <button class="text-slate-500 hover:text-slate-200 transition text-xs">&times;</button>
    `;

    toast.querySelector("button")?.addEventListener("click", () => {
      this.dismiss(toast);
    });

    this.container.appendChild(toast);
    if (window.lucide) window.lucide.createIcons({ root: toast });

    setTimeout(() => {
      this.dismiss(toast);
    }, duration);
  },

  dismiss(toast) {
    toast.classList.add("hiding");
    setTimeout(() => {
      if (toast.parentNode) toast.parentNode.removeChild(toast);
    }, 250);
  },

  success(msg, duration) {
    this.show(msg, "success", duration);
  },
  error(msg, duration) {
    this.show(msg, "error", duration || 5000);
  },
  info(msg, duration) {
    this.show(msg, "info", duration);
  },
  warn(msg, duration) {
    this.show(msg, "warn", duration);
  },
};
