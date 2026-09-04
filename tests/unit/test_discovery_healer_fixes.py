"""Tests for discovery_healer.py bug fixes:
1. _save_companies_yaml preserves extra top-level keys
2. Workday validation URL uses single token in path
"""

import importlib
import os
import tempfile
from unittest.mock import patch, MagicMock

import pytest
import yaml

_dh_mod = importlib.import_module("src.pipeline.5_lifecycle.healing.discovery_healer")
_save_companies_yaml = _dh_mod._save_companies_yaml
_load_companies_yaml = _dh_mod._load_companies_yaml
validate_candidate = _dh_mod.validate_candidate
HealingCandidate = _dh_mod.HealingCandidate


# ─── Bug 1: YAML save preserves top-level keys ─────────────────────────────


class TestSaveCompaniesYamlPreservesKeys:
    """_save_companies_yaml must not drop non-'companies' top-level keys."""

    def test_preserves_version_and_metadata(self, tmp_path):
        filepath = str(tmp_path / "companies.yaml")
        original = {
            "version": "2.0",
            "metadata": {"last_updated": "2025-01-01", "source": "test"},
            "companies": [
                {"name": "Acme", "portal_type": "greenhouse", "board_token": "acme"},
            ],
        }
        with open(filepath, "w") as f:
            yaml.safe_dump(original, f)

        updated_companies = [
            {"name": "Acme", "portal_type": "lever", "board_token": "acme-inc"},
            {"name": "NewCo", "portal_type": "ashby", "board_token": "newco"},
        ]
        _save_companies_yaml(filepath, updated_companies)

        with open(filepath, "r") as f:
            result = yaml.safe_load(f)

        assert result["version"] == "2.0"
        assert result["metadata"]["last_updated"] == "2025-01-01"
        assert result["metadata"]["source"] == "test"
        assert len(result["companies"]) == 2
        assert result["companies"][0]["portal_type"] == "lever"

    def test_preserves_custom_top_level_keys(self, tmp_path):
        filepath = str(tmp_path / "companies.yaml")
        original = {
            "companies": [{"name": "Old"}],
            "settings": {"max_retries": 3},
            "tags": ["h1b", "remote"],
        }
        with open(filepath, "w") as f:
            yaml.safe_dump(original, f)

        _save_companies_yaml(filepath, [{"name": "New"}])

        with open(filepath, "r") as f:
            result = yaml.safe_load(f)

        assert result["settings"] == {"max_retries": 3}
        assert result["tags"] == ["h1b", "remote"]
        assert result["companies"] == [{"name": "New"}]

    def test_creates_file_with_companies_key_when_no_existing(self, tmp_path):
        filepath = str(tmp_path / "new_companies.yaml")
        _save_companies_yaml(filepath, [{"name": "Fresh"}])

        with open(filepath, "r") as f:
            result = yaml.safe_load(f)

        assert result == {"companies": [{"name": "Fresh"}]}

    def test_roundtrip_load_save_preserves_structure(self, tmp_path):
        filepath = str(tmp_path / "companies.yaml")
        original = {
            "version": "1.5",
            "companies": [{"name": "A"}, {"name": "B"}],
            "notes": "keep me",
        }
        with open(filepath, "w") as f:
            yaml.safe_dump(original, f)

        companies = _load_companies_yaml(filepath)
        companies.append({"name": "C"})
        _save_companies_yaml(filepath, companies)

        with open(filepath, "r") as f:
            result = yaml.safe_load(f)

        assert result["version"] == "1.5"
        assert result["notes"] == "keep me"
        assert len(result["companies"]) == 3


# ─── Bug 2: Workday URL format ─────────────────────────────────────────────


class TestWorkdayUrlFormat:
    """Workday validation URL must use single token in path, not double."""

    def test_workday_url_single_token_in_path(self):
        """The URL should be /wday/cxs/{token}/jobs — NOT /wday/cxs/{token}/{token}/jobs."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)

        with patch.object(_dh_mod.httpx, "Client", return_value=mock_client):
            candidate = HealingCandidate("workday", "mytenant", "test")
            validate_candidate(candidate)

        mock_client.post.assert_called_once()
        url = mock_client.post.call_args[0][0]

        # Correct pattern: token as subdomain + token once in path (not twice)
        assert url == "https://mytenant.wd1.myworkdayjobs.com/wday/cxs/mytenant/jobs"
        # Double-token pattern must NOT appear
        assert "/mytenant/mytenant/" not in url

    def test_workday_url_uses_post_not_get(self):
        mock_client = MagicMock()
        mock_client.post.return_value = MagicMock(status_code=200)
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)

        with patch.object(_dh_mod.httpx, "Client", return_value=mock_client):
            candidate = HealingCandidate("workday", "tenant1")
            validate_candidate(candidate)

        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args[1]
        assert "json" in call_kwargs
        assert "limit" in call_kwargs["json"]
