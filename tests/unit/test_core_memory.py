"""Unit tests for Self-Editing Core Memory Engine."""

import pytest
from src.core.db.dual_engine import init_dual_database_pool, get_connection
from src.core.memory.core_memory_manager import CoreMemoryManager, MAX_KEYS, MAX_VALUE_CHARS


@pytest.fixture(autouse=True)
def setup_db(tmp_path):
    checkpoints_path = str(tmp_path / "checkpoints.db")
    telemetry_path = str(tmp_path / "telemetry.db")
    init_dual_database_pool(checkpoints_path=checkpoints_path, telemetry_path=telemetry_path)
    yield


def test_core_memory_append_and_replace():
    memory = CoreMemoryManager()
    memory.set_directive("preferred_stack", "Python, FastAPI")
    
    # Test Append
    res = memory.execute_tool(action="core_memory_append", key="preferred_stack", value=", Kafka")
    assert memory.get_directive("preferred_stack") == "Python, FastAPI, Kafka"
    assert res["preferred_stack"] == "Python, FastAPI, Kafka"
    
    # Test Replace
    res = memory.execute_tool(action="core_memory_replace", key="salary_floor", value="$185,000")
    assert memory.get_directive("salary_floor") == "$185,000"
    assert res["salary_floor"] == "$185,000"


def test_key_quota_enforcement():
    memory = CoreMemoryManager()
    # Default has 3 directives. Add until 10 keys.
    for i in range(4, MAX_KEYS + 1):
        memory.execute_tool(action="core_memory_replace", key=f"key_{i}", value=f"value_{i}")
    
    assert len(memory.list_directives()) == MAX_KEYS
    
    # 11th key should raise ValueError
    with pytest.raises(ValueError, match="Key quota exceeded"):
        memory.execute_tool(action="core_memory_replace", key="extra_key", value="overflow")

    with pytest.raises(ValueError, match="Key quota exceeded"):
        memory.execute_tool(action="core_memory_append", key="extra_key_append", value="overflow")


def test_char_quota_enforcement():
    memory = CoreMemoryManager()
    
    # Exceeding 250 chars on replace
    long_value = "A" * (MAX_VALUE_CHARS + 1)
    with pytest.raises(ValueError, match="exceeds maximum allowed length"):
        memory.execute_tool(action="core_memory_replace", key="target_roles", value=long_value)
    
    # Exceeding 250 chars on append
    memory.set_directive("notes", "A" * 200)
    with pytest.raises(ValueError, match="exceeds maximum allowed length"):
        memory.execute_tool(action="core_memory_append", key="notes", value="B" * 51)


def test_sqlite_persistence_across_instances():
    memory1 = CoreMemoryManager()
    memory1.execute_tool(action="core_memory_replace", key="remote_preference", value="Strictly Remote")
    memory1.execute_tool(action="core_memory_append", key="target_roles", value=", Tech Lead")
    
    # Verify in DB table directly
    with get_connection("checkpoints") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM candidate_directives WHERE key = 'remote_preference';")
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "Strictly Remote"
    
    # New instance should reload from DB
    memory2 = CoreMemoryManager()
    assert memory2.get_directive("remote_preference") == "Strictly Remote"
    assert "Tech Lead" in memory2.get_directive("target_roles")


def test_render_system_prompt_prefix():
    memory = CoreMemoryManager()
    memory.set_directive("target_roles", "Senior Software Engineer")
    memory.set_directive("salary_floor", "$180,000")
    
    prefix = memory.render_system_prompt_prefix()
    assert "### CANDIDATE CORE DIRECTIVES (IN-CONTEXT RAM):" in prefix
    assert "- TARGET_ROLES: Senior Software Engineer" in prefix
    assert "- SALARY_FLOOR: $180,000" in prefix


def test_invalid_action():
    memory = CoreMemoryManager()
    with pytest.raises(ValueError, match="Unknown action"):
        memory.execute_tool(action="invalid_action", key="foo", value="bar")
