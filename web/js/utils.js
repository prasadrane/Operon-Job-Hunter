/**
 * CareerGraph AI — Frontend Utilities
 */

export function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

export function formatTimeAgo(dateStr) {
  if (!dateStr) return "";
  try {
    const d = new Date(dateStr);
    const now = new Date();
    const diffSec = Math.floor((now - d) / 1000);
    if (isNaN(diffSec) || diffSec < 0) return "";
    if (diffSec < 60) return "just now";
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
    if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
    if (diffSec < 604800) return `${Math.floor(diffSec / 86400)}d ago`;
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  } catch (e) {
    return "";
  }
}

export function formatSalaryCompact(salaryStr) {
  if (!salaryStr) return "";
  return salaryStr
    .replace(/,000\b/g, "k")
    .replace(/\s*USD\b/gi, "")
    .replace(/\s+/g, " ")
    .trim();
}

export function formatCleanJobDescription(desc) {
  if (!desc) return "No description provided.";
  let d = desc;
  try {
    // Strip raw HTML tags while preserving line breaks
    d = d.replace(/<br\s*[\/]?>/gi, "\n");
    d = d.replace(/<\/p>/gi, "\n\n");
    d = d.replace(/<\/li>/gi, "\n");
    d = d.replace(/<li[^>]*>/gi, "• ");
    d = d.replace(/<[^>]+>/g, "");
    // Normalize excessive whitespace
    d = d.replace(/\n{3,}/g, "\n\n");
    return d.trim();
  } catch (e) {
    return desc;
  }
}
