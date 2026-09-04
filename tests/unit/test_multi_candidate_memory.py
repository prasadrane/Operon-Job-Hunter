"""Unit tests for Multi-Candidate Profile Partitioning in Core Memory Manager."""

import pytest
from src.core.memory.core_memory_manager import CoreMemoryManager, DEFAULT_DIRECTIVES


def test_core_memory_default_candidate_initialization():
    """Verify default candidate profile initializes with default directives in memory."""
    mgr = CoreMemoryManager(sync_db=False)
    assert mgr.candidate_id == "default"
    assert mgr.get_directive("sponsorship_required") == "Yes (H-1B)"
    assert "target_roles" in mgr.list_directives()


def test_core_memory_candidate_partitioning():
    """Verify separate candidates maintain isolated directive namespaces."""
    mgr_alice = CoreMemoryManager(candidate_id="alice_swe", sync_db=False)
    mgr_bob = CoreMemoryManager(candidate_id="bob_pm", sync_db=False)

    mgr_alice.set_directive("target_roles", "Senior Distributed Systems Engineer")
    mgr_bob.set_directive("target_roles", "Lead Product Manager, AI/ML")

    assert mgr_alice.get_directive("target_roles") == "Senior Distributed Systems Engineer"
    assert mgr_bob.get_directive("target_roles") == "Lead Product Manager, AI/ML"


def test_core_memory_switch_candidate():
    """Verify switching candidates dynamically switches directive contexts."""
    mgr = CoreMemoryManager(candidate_id="user_1", sync_db=False)
    mgr.set_directive("salary_floor", "$180,000")

    mgr.switch_candidate("user_2")
    assert mgr.candidate_id == "user_2"
    # user_2 has fresh default directives
    assert mgr.get_directive("salary_floor") == DEFAULT_DIRECTIVES["salary_floor"]

    mgr.set_directive("salary_floor", "$220,000")
    assert mgr.get_directive("salary_floor") == "$220,000"

    # Switch back to user_1
    mgr.switch_candidate("user_1")
    assert mgr.get_directive("salary_floor") == "$180,000"


def test_core_memory_render_system_ram_partitioned():
    """Verify system RAM rendering contains candidate-specific directives."""
    mgr = CoreMemoryManager(candidate_id="charlie_devops", sync_db=False)
    mgr.set_directive("target_roles", "Site Reliability Engineer")
    ram = mgr.render_system_ram()

    assert "CANDIDATE CORE DIRECTIVES (IN-CONTEXT RAM)" in ram
    assert "Site Reliability Engineer" in ram

