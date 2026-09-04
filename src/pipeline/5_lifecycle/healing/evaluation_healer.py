"""Evaluation Healer — handles LLM fallback and scoring failures.

Strategies:
- LLM_FALLBACK: Adjust min_fit_score threshold, log fallback frequency
- LLM_BATCH_ERROR: Force single-job scoring mode
"""

import logging
import os
from pathlib import Path
from typing import Any, List, Optional

from .base import BaseHealer, HealingResult

logger = logging.getLogger(__name__)


class EvaluationHealer(BaseHealer):
    """Handles evaluation stage errors — LLM fallbacks and scoring failures."""

    name = "evaluation"
    stage_label = "Evaluation"
    source = "evaluation"

    def __init__(self, env_file: str = ".env", **kwargs):
        super().__init__(cooldown_hours=4.0, **kwargs)
        self.env_file = env_file

    def can_heal(self, error_type: str, component: str) -> bool:
        return error_type in ("LLM_FALLBACK", "LLM_BATCH_ERROR", "EVALUATION_ERROR")

    def heal(self, errors: List[Any]) -> List[HealingResult]:
        results = []
        fallback_count = 0
        batch_errors = 0

        for error in errors:
            error_type = getattr(error, "error_type", "")
            error_id = getattr(error, "id", None)

            if error_type == "LLM_FALLBACK":
                fallback_count += 1
            elif error_type == "LLM_BATCH_ERROR":
                batch_errors += 1
            elif error_type == "EVALUATION_ERROR":
                results.append(HealingResult(
                    healer=self.name,
                    action=f"Evaluation error logged — gateway healer should handle LLM recovery",
                    success=True,
                    error_id=error_id,
                    details={"delegated_to": "gateway"},
                ))

        # If multiple fallbacks, lower the threshold to allow more jobs through
        if fallback_count >= 3:
            result = self._adjust_threshold(fallback_count)
            results.append(result)

        # Log batch error pattern
        if batch_errors > 0:
            results.append(HealingResult(
                healer=self.name,
                action=f"Recorded {batch_errors} batch LLM errors — scorer already falls back to single-job mode",
                success=True,
                details={"batch_errors": batch_errors, "note": "auto-recovery via scorer fallback"},
            ))

        return results[:self.max_heal_per_cycle]

    def _adjust_threshold(self, fallback_count: int) -> HealingResult:
        """Lower min_fit_score to widen the funnel when LLM fallbacks are frequent."""
        try:
            from src.core.config import get_settings
            current = float(get_settings().min_fit_score)
        except (ValueError, TypeError, OSError) as exc:
            logger.warning("Could not read min_fit_score as float (%s: %s), using default 72.0",
                           type(exc).__name__, exc)
            current = 72.0

        # Lower by 5 points per 3 fallbacks, minimum 50
        new_threshold = max(50.0, current - (fallback_count // 3) * 5)

        if new_threshold >= current:
            return HealingResult(
                healer=self.name,
                action=f"Threshold already at minimum ({current})",
                success=True,
                details={"current_threshold": current, "fallback_count": fallback_count},
            )

        if self.dry_run:
            return HealingResult(
                healer=self.name,
                action=f"DRY RUN: Would lower min_fit_score {current} → {new_threshold}",
                success=True,
                config_changed=False,
                details={"from": current, "to": new_threshold},
            )

        # Update .env
        try:
            env_path = Path(self.env_file)
            if env_path.exists():
                lines = env_path.read_text().splitlines()
                new_lines = []
                found = False
                for line in lines:
                    if line.startswith("MIN_FIT_SCORE="):
                        new_lines.append(f"MIN_FIT_SCORE={new_threshold}")
                        found = True
                    else:
                        new_lines.append(line)
                if not found:
                    new_lines.append(f"MIN_FIT_SCORE={new_threshold}")
                env_path.write_text("\n".join(new_lines) + "\n")

            # Update settings cache
            try:
                from src.core.config import get_settings
                get_settings().min_fit_score = new_threshold
            except (ValueError, TypeError, OSError) as exc:
                logger.warning("Failed to update settings cache (%s: %s)", type(exc).__name__, exc)

            self._broadcast(f"Lowered min_fit_score: {current} → {new_threshold} ({fallback_count} LLM fallbacks)")
            return HealingResult(
                healer=self.name,
                action=f"Lowered min_fit_score: {current} → {new_threshold}",
                success=True,
                config_changed=True,
                details={"from": current, "to": new_threshold, "fallback_count": fallback_count},
            )
        except (ValueError, TypeError, OSError) as exc:
            return HealingResult(
                healer=self.name,
                action=f"Failed to adjust threshold ({type(exc).__name__}): {exc}",
                success=False,
            )
