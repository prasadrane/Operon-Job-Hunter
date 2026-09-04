"""Tailoring Healer — handles PDF compilation and GraphRAG failures.

Strategies:
- PDF_COMPILE_ERROR: Switch pdf_compiler_backend (reportlab↔typst)
- GRAPH_RAG_ERROR: Delete embedded_graph.json to trigger rebuild
"""

import logging
import os
from pathlib import Path
from typing import Any, List, Optional

from .base import BaseHealer, HealingResult

logger = logging.getLogger(__name__)


class TailoringHealer(BaseHealer):
    """Handles tailoring stage errors — PDF compiler and GraphRAG failures."""

    name = "tailoring"
    stage_label = "Tailoring"
    source = "tailoring"

    def __init__(self, env_file: str = ".env", **kwargs):
        super().__init__(cooldown_hours=4.0, **kwargs)
        self.env_file = env_file

    def can_heal(self, error_type: str, component: str) -> bool:
        return error_type in ("PDF_COMPILE_ERROR", "GRAPH_RAG_ERROR", "TAILORING_ERROR")

    def heal(self, errors: List[Any]) -> List[HealingResult]:
        results = []
        seen_types = set()

        for error in errors:
            error_type = getattr(error, "error_type", "")
            error_id = getattr(error, "id", None)

            if error_type in seen_types:
                continue
            seen_types.add(error_type)

            if error_type == "PDF_COMPILE_ERROR":
                results.append(self._switch_pdf_backend(error_id))
            elif error_type == "GRAPH_RAG_ERROR":
                results.append(self._rebuild_graph(error_id))
            elif error_type == "TAILORING_ERROR":
                results.append(HealingResult(
                    healer=self.name,
                    action=f"Tailoring error logged — check specific component: {getattr(error, 'component', 'unknown')}",
                    success=False,
                    error_id=error_id,
                    details={"component": getattr(error, "component", "unknown")},
                ))

            if len(results) >= self.max_heal_per_cycle:
                break

        return results

    def _get_current_backend(self) -> str:
        try:
            from src.core.config import get_settings
            return get_settings().pdf_compiler_backend
        except Exception:
            pass
        try:
            env_path = Path(self.env_file)
            if env_path.exists():
                for line in env_path.read_text().splitlines():
                    if line.startswith("PDF_COMPILER_BACKEND="):
                        return line.split("=", 1)[1].strip().strip("'\"")
        except Exception:
            pass
        return "reportlab"

    def _switch_pdf_backend(self, error_id: Optional[str]) -> HealingResult:
        """Switch between reportlab and typst PDF backends."""
        current = self._get_current_backend()
        new_backend = "typst" if current == "reportlab" else "reportlab"

        if self.dry_run:
            return HealingResult(
                healer=self.name,
                action=f"DRY RUN: Would switch pdf_compiler_backend {current} → {new_backend}",
                success=True,
                config_changed=False,
                details={"from": current, "to": new_backend},
            )

        try:
            env_path = Path(self.env_file)
            if env_path.exists():
                lines = env_path.read_text().splitlines()
                new_lines = []
                found = False
                for line in lines:
                    if line.startswith("PDF_COMPILER_BACKEND="):
                        new_lines.append(f"PDF_COMPILER_BACKEND={new_backend}")
                        found = True
                    else:
                        new_lines.append(line)
                if not found:
                    new_lines.append(f"PDF_COMPILER_BACKEND={new_backend}")
                env_path.write_text("\n".join(new_lines) + "\n")

            try:
                from src.core.config import get_settings
                get_settings().pdf_compiler_backend = new_backend
            except Exception:
                pass

            self._broadcast(f"Switched PDF backend: {current} → {new_backend}")
            return HealingResult(
                healer=self.name,
                action=f"Switched PDF backend: {current} → {new_backend}",
                success=True,
                error_id=error_id,
                config_changed=True,
                details={"from": current, "to": new_backend},
            )
        except Exception as exc:
            return HealingResult(
                healer=self.name,
                action=f"Failed to switch PDF backend: {exc}",
                success=False,
                error_id=error_id,
            )

    def _rebuild_graph(self, error_id: Optional[str]) -> HealingResult:
        """Delete embedded_graph.json to trigger rebuild on next access."""
        graph_path = Path("./data/embedded_graph.json")

        if not graph_path.exists():
            return HealingResult(
                healer=self.name,
                action="embedded_graph.json already absent — will rebuild on next access",
                success=True,
                error_id=error_id,
            )

        if self.dry_run:
            return HealingResult(
                healer=self.name,
                action="DRY RUN: Would delete embedded_graph.json to trigger rebuild",
                success=True,
                config_changed=False,
            )

        try:
            graph_path.unlink()
            self._broadcast("Deleted embedded_graph.json — will rebuild on next GraphRAG access")
            return HealingResult(
                healer=self.name,
                action="Deleted embedded_graph.json — will rebuild on next access",
                success=True,
                error_id=error_id,
                config_changed=True,
            )
        except Exception as exc:
            return HealingResult(
                healer=self.name,
                action=f"Failed to delete embedded_graph.json: {exc}",
                success=False,
                error_id=error_id,
            )
