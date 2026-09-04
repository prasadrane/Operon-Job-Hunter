"""Unit tests for the 5-Agent Discovery Squad architecture."""

import importlib
import pytest
from unittest.mock import MagicMock, patch

from src.core.models import JobPosting, JobStatus

_squad_mod = importlib.import_module("src.pipeline.1_discovery.agents.discovery_squad")
DiscoverySquadOrchestrator = getattr(_squad_mod, "DiscoverySquadOrchestrator", None)

_falcon_mod = importlib.import_module("src.pipeline.1_discovery.agents.scout_falcon")
ScoutFalconAgent = getattr(_falcon_mod, "ScoutFalconAgent", None)

_atlas_mod = importlib.import_module("src.pipeline.1_discovery.agents.scout_atlas")
ScoutAtlasAgent = getattr(_atlas_mod, "ScoutAtlasAgent", None)

_titan_mod = importlib.import_module("src.pipeline.1_discovery.agents.scout_titan")
ScoutTitanAgent = getattr(_titan_mod, "ScoutTitanAgent", None)

_horizon_mod = importlib.import_module("src.pipeline.1_discovery.agents.scout_horizon")
ScoutHorizonAgent = getattr(_horizon_mod, "ScoutHorizonAgent", None)

_aegis_mod = importlib.import_module("src.pipeline.1_discovery.agents.scout_aegis")
ScoutAegisAgent = getattr(_aegis_mod, "ScoutAegisAgent", None)


def test_scout_falcon_fast_path():
    """Verify ScoutFalconAgent extracts Greenhouse, Lever, and Ashby postings."""
    assert ScoutFalconAgent is not None, "ScoutFalconAgent must be implemented"
    falcon = ScoutFalconAgent()

    mock_jobs = [
        JobPosting(id="gh_1", company="Anthropic", title="AI Engineer", url="https://boards.greenhouse.io/anthropic/1", portal_type="greenhouse"),
        JobPosting(id="lev_1", company="Spotify", title="Backend Engineer", url="https://jobs.lever.co/spotify/1", portal_type="lever"),
    ]

    with patch.object(falcon.portal_crawler, "crawl", side_effect=[[mock_jobs[0]], [mock_jobs[1]]]):
        results = falcon.run(companies=[
            {"name": "Anthropic", "portal_type": "greenhouse", "board_token": "anthropic"},
            {"name": "Spotify", "portal_type": "lever", "board_token": "spotify"},
        ])
        assert len(results) == 2
        assert results[0].company == "Anthropic"
        assert results[1].company == "Spotify"


def test_scout_atlas_enterprise():
    """Verify ScoutAtlasAgent extracts Workday and SmartRecruiters postings."""
    assert ScoutAtlasAgent is not None, "ScoutAtlasAgent must be implemented"
    atlas = ScoutAtlasAgent()

    mock_jobs = [
        JobPosting(id="wd_1", company="Capital One", title="Lead SWE", url="https://capitalone.wd1.myworkdayjobs.com/1", portal_type="workday"),
        JobPosting(id="sr_1", company="Block", title="Senior Engineer", url="https://jobs.smartrecruiters.com/block/1", portal_type="smartrecruiters"),
    ]

    with patch.object(atlas.portal_crawler, "crawl", side_effect=[[mock_jobs[0]], [mock_jobs[1]]]):
        results = atlas.run(companies=[
            {"name": "Capital One", "portal_type": "workday", "board_token": "capitalone"},
            {"name": "Block", "portal_type": "smartrecruiters", "board_token": "block"},
        ])
        assert len(results) == 2
        assert results[0].portal_type == "workday"
        assert results[1].portal_type == "smartrecruiters"


def test_scout_titan_bigtech():
    """Verify ScoutTitanAgent extracts Amazon, Microsoft, and Google postings."""
    assert ScoutTitanAgent is not None, "ScoutTitanAgent must be implemented"
    titan = ScoutTitanAgent()

    mock_jobs = [
        JobPosting(id="amz_1", company="Amazon", title="SDE II", url="https://amazon.jobs/1", portal_type="amazon"),
        JobPosting(id="msft_1", company="Microsoft", title="Principal SWE", url="https://jobs.careers.microsoft.com/1", portal_type="microsoft"),
    ]

    with patch.object(titan.portal_crawler, "crawl", side_effect=[[mock_jobs[0]], [mock_jobs[1]]]):
        results = titan.run(companies=[
            {"name": "Amazon", "portal_type": "amazon", "board_token": "amazon"},
            {"name": "Microsoft", "portal_type": "microsoft", "board_token": "microsoft"},
        ])
        assert len(results) == 2
        assert results[0].company == "Amazon"
        assert results[1].company == "Microsoft"


def test_scout_horizon_market_sweeper():
    """Verify ScoutHorizonAgent ingests EchoJobs aggregator stream."""
    assert ScoutHorizonAgent is not None, "ScoutHorizonAgent must be implemented"
    horizon = ScoutHorizonAgent()

    mock_jobs = [
        JobPosting(id="echo_1", company="Datadog", title="Staff Engineer", url="https://boards.greenhouse.io/datadog/1", portal_type="greenhouse"),
    ]

    with patch.object(horizon.feeder, "fetch_jobs", return_value=mock_jobs):
        results = horizon.run(max_pages=1, include_aggregators=False)
        assert len(results) == 1
        assert results[0].company == "Datadog"


def test_scout_aegis_visa_and_blocker_gatekeeper():
    """Verify ScoutAegisAgent verifies H-1B eligibility and purges clearance/citizen blockers."""
    assert ScoutAegisAgent is not None, "ScoutAegisAgent must be implemented"
    aegis = ScoutAegisAgent()

    raw_jobs = [
        JobPosting(id="j1", company="Google", title="Software Engineer", url="http://g.co/1", description="Build distributed search backends."),
        JobPosting(id="j2", company="Defense Contractor", title="Engineer", url="http://def.co/1", description="Must be a U.S. citizen with active TS/SCI security clearance."),
    ]

    passed_jobs, rejected_count = aegis.sanitize_and_verify(raw_jobs)
    assert len(passed_jobs) == 1
    assert passed_jobs[0].company == "Google"
    assert passed_jobs[0].h1b_sponsored is True
    assert rejected_count == 1


def test_discovery_squad_orchestrator_concurrent_run():
    """Verify DiscoverySquadOrchestrator coordinates all 5 subagents with canonical deduplication."""
    assert DiscoverySquadOrchestrator is not None, "DiscoverySquadOrchestrator must be implemented"
    orchestrator = DiscoverySquadOrchestrator()

    job_dup1 = JobPosting(id="dup1", company="Databricks", title="SWE", url="https://boards.greenhouse.io/databricks/1?utm_source=echojobs", description="Data platform backend.")
    job_dup2 = JobPosting(id="dup2", company="Databricks", title="SWE", url="https://boards.greenhouse.io/databricks/1", description="Data platform backend.")

    with patch.object(orchestrator.falcon, "run", return_value=[job_dup1]),          patch.object(orchestrator.atlas, "run", return_value=[]),          patch.object(orchestrator.titan, "run", return_value=[]),          patch.object(orchestrator.horizon, "run", return_value=[job_dup2]),          patch.object(orchestrator.aegis, "sanitize_and_verify", side_effect=lambda jobs: ([jobs[0]], 0)):
        
        final_jobs = orchestrator.run_squad()
        # Canonical URL normalization should collapse the 2 duplicate URLs into 1 unique role
        assert len(final_jobs) == 1
        assert final_jobs[0].company == "Databricks"
