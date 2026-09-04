"""Gateway Healer — handles LLM provider rate limits and failovers.

Strategies:
- RATE_LIMIT: Rotate primary_llm_provider in .env, trigger cooldown
- PROVIDER_ERROR: Disable failing provider, switch to fallback
- FATAL: Reset all provider configs, clear rate limit cache
"""

import logging
import os
from pathlib import Path
from typing import Any, List, Optional

from .base import BaseHealer, HealingResult

logger = logging.getLogger(__name__)

# Provider rotation order
PROVIDER_CHAIN = ["alibaba", "gemini", "openrouter"]


class GatewayHealer(BaseHealer):
    """Handles LLM gateway errors — rate limits, provider failures, fatal exhaustion."""

    name = "gateway"
    stage_label = "Gateway/LLM"
    source = "gateway"

    def __init__(self, env_file: str = ".env", **kwargs):
        super().__init__(cooldown_hours=1.0, **kwargs)  # 1h cooldown for fast recovery
        self.env_file = env_file

    def can_heal(self, error_type: str, component: str) -> bool:
        return error_type in ("RATE_LIMIT", "PROVIDER_ERROR", "FATAL")

    def heal(self, errors: List[Any]) -> List[HealingResult]:
        results = []
        seen_types = set()

        for error in errors:
            error_type = getattr(error, "error_type", "")
            component = getattr(error, "component", "")
            error_id = getattr(error, "id", None)

            if error_type in seen_types:
                continue
            seen_types.add(error_type)

            if error_type == "RATE_LIMIT":
                result = self._rotate_provider(error_id, component)
            elif error_type == "PROVIDER_ERROR":
                result = self._switch_provider(error_id, component)
            elif error_type == "FATAL":
                result = self._reset_all_providers(error_id)
            else:
                continue

            results.append(result)
            if len(results) >= self.max_heal_per_cycle:
                break

        return results

    def _get_current_provider(self) -> str:
        """Read current primary_llm_provider from .env or settings."""
        try:
            from src.core.config import get_settings
            return get_settings().primary_llm_provider
        except Exception:
            pass

        try:
            env_path = Path(self.env_file)
            if env_path.exists():
                for line in env_path.read_text().splitlines():
                    if line.startswith("PRIMARY_LLM_PROVIDER="):
                        return line.split("=", 1)[1].strip().strip("'\"")
        except Exception:
            pass
        return "alibaba"

    def _set_provider(self, provider: str) -> bool:
        """Update primary_llm_provider in .env file."""
        if self.dry_run:
            logger.info("[GatewayHealer] DRY RUN: Would set primary_llm_provider=%s", provider)
            return True

        try:
            env_path = Path(self.env_file)
            if not env_path.exists():
                return False

            lines = env_path.read_text().splitlines()
            new_lines = []
            found = False
            for line in lines:
                if line.startswith("PRIMARY_LLM_PROVIDER="):
                    new_lines.append(f"PRIMARY_LLM_PROVIDER={provider}")
                    found = True
                else:
                    new_lines.append(line)
            if not found:
                new_lines.append(f"PRIMARY_LLM_PROVIDER={provider}")

            env_path.write_text("\n".join(new_lines) + "\n")

            # Also update settings cache
            try:
                from src.core.config import get_settings
                settings = get_settings()
                settings.primary_llm_provider = provider
            except Exception:
                pass

            return True
        except Exception as exc:
            logger.error("[GatewayHealer] Failed to update provider: %s", exc)
            return False

    def _rotate_provider(self, error_id: Optional[str], component: str) -> HealingResult:
        """Rotate to next provider in chain."""
        current = self._get_current_provider()
        idx = PROVIDER_CHAIN.index(current) if current in PROVIDER_CHAIN else 0
        next_provider = PROVIDER_CHAIN[(idx + 1) % len(PROVIDER_CHAIN)]

        ok = self._set_provider(next_provider)
        if ok:
            self._broadcast(f"Rotated LLM provider: {current} → {next_provider} (rate limit on {component})")
            return HealingResult(
                healer=self.name,
                action=f"Rotated provider: {current} → {next_provider}",
                success=True,
                error_id=error_id,
                config_changed=True,
                details={"from": current, "to": next_provider, "reason": "rate_limit"},
            )
        return HealingResult(
            healer=self.name,
            action=f"Failed to rotate provider from {current}",
            success=False,
            error_id=error_id,
        )

    def _switch_provider(self, error_id: Optional[str], component: str) -> HealingResult:
        """Switch away from a failing provider."""
        failed = component.replace("_provider", "") if "_provider" in component else component
        current = self._get_current_provider()

        if current == failed:
            return self._rotate_provider(error_id, component)

        return HealingResult(
            healer=self.name,
            action=f"Provider {failed} failed but current primary is {current} — failover chain should handle",
            success=True,
            error_id=error_id,
            details={"failed_provider": failed, "current_primary": current},
        )

    def _reset_all_providers(self, error_id: Optional[str]) -> HealingResult:
        """Reset to default provider after all-providers-exhausted fatal."""
        ok = self._set_provider(PROVIDER_CHAIN[0])
        if ok:
            self._broadcast(f"Reset LLM provider to {PROVIDER_CHAIN[0]} after fatal exhaustion")
            return HealingResult(
                healer=self.name,
                action=f"Reset provider to {PROVIDER_CHAIN[0]}",
                success=True,
                error_id=error_id,
                config_changed=True,
                details={"reason": "fatal_reset"},
            )
        return HealingResult(
            healer=self.name,
            action="Failed to reset provider",
            success=False,
            error_id=error_id,
        )
