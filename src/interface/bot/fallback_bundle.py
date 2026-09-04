"""1-Click Assisted Fallback Bundle Generator for Telegram HITL."""

from typing import Any, Dict, Optional


class FallbackBundleGenerator:
    """Generates assisted fallback bundles formatted with tappable HTML snippets for 1-click mobile copying."""

    def generate(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Produce a complete fallback bundle including plain text, tappable HTML, and paths."""
        job_id = state.get("job_id", "")
        company = state.get("company", "Company")
        title = state.get("title", "Role")
        url = state.get("url") or state.get("job_url", "")
        resume_path = state.get("resume_pdf_path") or state.get("resume_path", "")
        cover_letter_path = state.get("cover_letter_path", "")
        qa_answers: Dict[str, Any] = state.get("qa_answers", {})

        # Build plain text clipboard copy
        qa_lines = [f"{k}: {v}" for k, v in qa_answers.items()]
        clipboard_text = f"Candidate Application for {company} - {title}\n"
        if qa_lines:
            clipboard_text += "\n".join(qa_lines)

        # Build tappable field mappings (wrapped in <code> tags for single-tap mobile copy)
        tappable_fields: Dict[str, str] = {}
        for k, v in qa_answers.items():
            tappable_fields[k] = f"<code>{v}</code>"

        # Build HTML formatted Telegram message
        html_lines = [
            f"<b>⚠️ Assisted Fallback Application: {company}</b>",
            f"<b>Position:</b> {title}",
        ]
        if url:
            html_lines.append(f"<b>Application Link:</b> <a href=\"{url}\">Open Job Portal</a>")
        if resume_path:
            html_lines.append(f"<b>Resume:</b> <code>{resume_path}</code>")
        if cover_letter_path:
            html_lines.append(f"<b>Cover Letter:</b> <code>{cover_letter_path}</code>")

        if qa_answers:
            html_lines.append("\n<b>📋 Quick-Copy Form Answers (Tap to copy):</b>")
            for k, v in qa_answers.items():
                label = k.replace("_", " ").title()
                html_lines.append(f"• <b>{label}:</b> <code>{v}</code>")

        html_lines.append(
            "\n<i>💡 Direct submit timed out or required manual input. "
            "Tap any field code block above to copy directly to your clipboard.</i>"
        )
        html_message = "\n".join(html_lines)

        return {
            "job_id": job_id,
            "job_url": url,
            "resume_path": resume_path,
            "cover_letter_path": cover_letter_path,
            "clipboard_text": clipboard_text.strip(),
            "html_message": html_message,
            "tappable_fields": tappable_fields,
            "instructions": "Direct submit session expired. Click job_url to open form, answers are copied to clipboard.",
        }
