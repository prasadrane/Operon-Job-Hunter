"""Unit tests for H-1B dataset management, tiered confidence scoring, entity resolution, and ATS probing."""

import importlib
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.models import JobPosting

h1b_mgr_mod = importlib.import_module("src.pipeline.1_discovery.h1b_dataset_manager")
H1BDatasetManager = h1b_mgr_mod.H1BDatasetManager
H1BTier = h1b_mgr_mod.H1BTier

ats_prober_mod = importlib.import_module("src.pipeline.1_discovery.ats_prober")
ATSProber = ats_prober_mod.ATSProber


def test_h1b_dataset_manager_indexing_and_tiering():
    """Test H1B dataset indexing, search, and 4-tier confidence scoring."""
    sample_data = [
        {
            "employer_name": "AMAZON.COM SERVICES LLC",
            "domain": "amazon.com",
            "lca_count": 8500,
            "approval_rate": 0.99,
            "is_cap_exempt": False,
            "prevailing_wage_median": 185000,
        },
        {
            "employer_name": "STRIPE, INC.",
            "domain": "stripe.com",
            "lca_count": 320,
            "approval_rate": 0.98,
            "is_cap_exempt": False,
            "prevailing_wage_median": 195000,
        },
        {
            "employer_name": "STANFORD UNIVERSITY",
            "domain": "stanford.edu",
            "lca_count": 45,
            "approval_rate": 1.0,
            "is_cap_exempt": True,
            "prevailing_wage_median": 135000,
        },
        {
            "employer_name": "LOCAL TECH BOUTIQUE LLC",
            "domain": "localboutique.io",
            "lca_count": 2,
            "approval_rate": 0.80,
            "is_cap_exempt": False,
            "prevailing_wage_median": 120000,
        },
    ]

    manager = H1BDatasetManager(initial_records=sample_data)
    
    # Tier 1 Platinum check
    amz = manager.lookup("Amazon")
    assert amz is not None
    assert amz["tier"] == H1BTier.TIER_1_PLATINUM
    assert amz["score"] >= 90.0

    # Brand alias resolution check
    cashapp = manager.lookup("Cash App")
    # Even if Cash App is an alias for Block/Square, resolver should handle it
    assert manager.resolve_brand_to_legal("Cash App") in ("Block, Inc.", "Square, Inc.", "Block Inc.")

    # Cap exempt check
    stanford = manager.lookup("Stanford University")
    assert stanford is not None
    assert stanford["is_cap_exempt"] is True

    # Tier 3 Occasional check
    boutique = manager.lookup("Local Tech Boutique")
    assert boutique is not None
    assert boutique["tier"] == H1BTier.TIER_3_OCCASIONAL


@pytest.mark.asyncio
async def test_ats_prober_endpoint_discovery():
    """Test automated ATS endpoint probing for unmapped sponsor domains."""
    prober = ATSProber()
    
    mock_gh_resp = MagicMock()
    mock_gh_resp.status_code = 200
    mock_gh_resp.json.return_value = {"jobs": [{"id": 1, "title": "Software Engineer"}]}

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_gh_resp
        
        discovered = await prober.probe_domain("stripe.com", "Stripe")
        assert discovered is not None
        assert discovered["portal_type"] in ("greenhouse", "lever", "ashby", "workday")
        assert discovered["board_token"] == "stripe"
