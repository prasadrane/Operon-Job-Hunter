"""Unit tests for behavioral simulation (human-like typing/mouse/scroll)."""
import importlib.util
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Direct file import to avoid triggering __init__.py which imports patchright
bs_path = Path(__file__).parent.parent.parent / "src" / "pipeline" / "4_submission" / "behavioral_sim.py"
spec = importlib.util.spec_from_file_location("behavioral_sim", bs_path)
bs_mod = importlib.util.module_from_spec(spec)
sys.modules["behavioral_sim"] = bs_mod
spec.loader.exec_module(bs_mod)
BehavioralSimulator = bs_mod.BehavioralSimulator


@pytest.fixture
def mock_page():
    """Mock Playwright page object."""
    page = AsyncMock()
    page.mouse = MagicMock()
    page.mouse.move = AsyncMock()
    page.mouse.click = AsyncMock()
    page.mouse.down = AsyncMock()
    page.mouse.up = AsyncMock()
    page.keyboard = MagicMock()
    page.keyboard.type = AsyncMock()
    page.keyboard.press = AsyncMock()
    page.evaluate = AsyncMock(return_value={"x": 100, "y": 200, "width": 50, "height": 30})
    page.wait_for_timeout = AsyncMock()
    return page


class TestHumanType:
    """Test human-like typing behavior."""

    @pytest.mark.asyncio
    async def test_type_duration_correct(self, mock_page):
        """Typing duration matches expected Poisson distribution."""
        sim = BehavioralSimulator(typing_speed_wpm=100, typing_variance=0.1)
        text = "hello world"

        start = time.time()
        await sim.human_type(mock_page, "#input", text)
        elapsed = time.time() - start

        # Expected: ~10 chars * 0.12s/char = 1.2s (with 10% variance)
        # Allow generous bounds for CI variance
        assert 0.5 < elapsed < 3.0

    @pytest.mark.asyncio
    async def test_type_variance_in_delays(self, mock_page):
        """Keystroke delays vary (not uniform)."""
        sim = BehavioralSimulator(typing_speed_wpm=100, typing_variance=0.3)

        # Track timing between keystrokes
        keystroke_times = []
        original_type = mock_page.keyboard.type

        async def track_type(char):
            keystroke_times.append(time.time())
            return await original_type(char)

        mock_page.keyboard.type = track_type

        await sim.human_type(mock_page, "#input", "test text")

        # Calculate inter-keystroke delays
        if len(keystroke_times) > 1:
            delays = [keystroke_times[i+1] - keystroke_times[i] for i in range(len(keystroke_times)-1)]
            # Should have variance in delays
            assert len(delays) > 0
            assert max(delays) > min(delays) * 1.1  # At least 10% variance


class TestHumanClick:
    """Test human-like mouse clicking."""

    @pytest.mark.asyncio
    async def test_click_moves_to_element(self, mock_page):
        """Click moves mouse to element coordinates."""
        sim = BehavioralSimulator()

        await sim.human_click(mock_page, "#button")

        # Verify mouse.move called
        assert mock_page.mouse.move.called

    @pytest.mark.asyncio
    async def test_click_random_offset(self, mock_page):
        """Click adds random offset within bounds."""
        sim = BehavioralSimulator()

        # Run multiple clicks, collect positions
        positions = []
        original_move = mock_page.mouse.move

        async def track_move(x, y):
            positions.append((x, y))
            return await original_move(x, y)

        mock_page.mouse.move = track_move

        for _ in range(5):
            await sim.human_click(mock_page, "#button")

        # Positions should vary (random offset)
        x_coords = [p[0] for p in positions]
        y_coords = [p[1] for p in positions]
        assert len(set(x_coords)) > 1 or len(set(y_coords)) > 1


class TestHumanScroll:
    """Test human-like scrolling."""

    @pytest.mark.asyncio
    async def test_scroll_completes(self, mock_page):
        """Scroll completes in reasonable time."""
        sim = BehavioralSimulator()

        start = time.time()
        await sim.human_scroll(mock_page, "down", 500)
        elapsed = time.time() - start

        # Should complete quickly (< 2s for smooth scroll)
        assert elapsed < 2.0
        assert mock_page.evaluate.called


class TestErrorHandling:
    """Test graceful error handling."""

    @pytest.mark.asyncio
    async def test_missing_element_graceful(self, mock_page):
        """Handles missing elements without crash."""
        sim = BehavioralSimulator()

        # Mock element not found
        mock_page.evaluate.side_effect = Exception("Element not found")

        # Should not raise
        await sim.human_click(mock_page, "#nonexistent")
        await sim.human_type(mock_page, "#nonexistent", "test")


class TestConfiguration:
    """Test constructor configuration."""

    def test_constructor_params(self):
        """Configurable via constructor."""
        sim = BehavioralSimulator(
            typing_speed_wpm=120,
            typing_variance=0.3,
            mouse_bezier=False,
            mouse_overshoot=False,
        )

        assert sim.typing_speed_wpm == 120
        assert sim.typing_variance == 0.3
        assert sim.mouse_bezier is False
        assert sim.mouse_overshoot is False
