"""
Behavioral simulation for human-like mouse movements and typing.

Implements Poisson typing delays, Bézier mouse curves, and overshoot correction
to avoid bot detection during automated form submission.
"""
import asyncio
import math
import random
from typing import Any, List, Tuple

import numpy as np


class BehavioralSimulator:
    """Simulates human-like typing and mouse movements."""

    def __init__(
        self,
        typing_speed_wpm: int = 85,
        typing_variance: float = 0.2,
        mouse_bezier: bool = True,
        mouse_overshoot: bool = True,
    ):
        """
        Initialize behavioral simulator.

        Args:
            typing_speed_wpm: Words per minute (1 word = 5 chars)
            typing_variance: Variance factor for Poisson delays (0.0-1.0)
            mouse_bezier: Use cubic Bézier curves for mouse movement
            mouse_overshoot: Add overshoot + correction to mouse clicks
        """
        self.typing_speed_wpm = typing_speed_wpm
        self.typing_variance = typing_variance
        self.mouse_bezier = mouse_bezier
        self.mouse_overshoot = mouse_overshoot

        # Calculate base delay per character (seconds)
        # λ = 60 / (wpm * 5) seconds per character
        self.base_char_delay = 60.0 / (typing_speed_wpm * 5)

    async def human_type(self, page: Any, selector: str, text: str) -> None:
        """
        Type text with human-like Poisson delays between keystrokes.

        Args:
            page: Playwright page object
            selector: CSS selector for input element
            text: Text to type
        """
        try:
            # Focus element
            await page.evaluate(f"document.querySelector('{selector}').focus()")
        except Exception:
            # Element not found, silently return
            return

        for char in text:
            # Poisson delay: exponential distribution
            # Scale by variance factor
            delay = np.random.exponential(scale=self.base_char_delay)
            delay = delay * (1.0 + random.uniform(-self.typing_variance, self.typing_variance))
            delay = max(0.01, delay)  # Minimum 10ms

            await asyncio.sleep(delay)
            await page.keyboard.type(char)

    async def human_click(self, page: Any, selector: str) -> None:
        """
        Click element with human-like mouse movement.

        Args:
            page: Playwright page object
            selector: CSS selector for element to click
        """
        try:
            # Get element bounding box
            box = await page.evaluate(f"""
                (() => {{
                    const el = document.querySelector('{selector}');
                    if (!el) return null;
                    const rect = el.getBoundingClientRect();
                    return {{
                        x: rect.x,
                        y: rect.y,
                        width: rect.width,
                        height: rect.height
                    }};
                }})()
            """)

            if not box:
                return

            # Calculate target center with random offset
            target_x = box["x"] + box["width"] / 2 + random.uniform(-5, 5)
            target_y = box["y"] + box["height"] / 2 + random.uniform(-5, 5)

            if self.mouse_bezier:
                # Generate Bézier curve path
                path = self._generate_bezier_path(target_x, target_y)

                # Move along path
                for x, y in path:
                    await page.mouse.move(x, y)
                    await asyncio.sleep(0.005)  # 5ms between steps
            else:
                # Direct move
                await page.mouse.move(target_x, target_y)

            if self.mouse_overshoot:
                # Overshoot by 5-15px
                overshoot_x = target_x + random.uniform(5, 15)
                overshoot_y = target_y + random.uniform(5, 15)
                await page.mouse.move(overshoot_x, overshoot_y)
                await asyncio.sleep(0.05)

                # Correct back to target
                await page.mouse.move(target_x, target_y)
                await asyncio.sleep(0.03)

            # Click
            await page.mouse.click(target_x, target_y)

        except Exception:
            # Element not found or other error, silently return
            return

    def _generate_bezier_path(
        self, target_x: float, target_y: float, steps: int = 20
    ) -> List[Tuple[float, float]]:
        """
        Generate cubic Bézier curve path to target.

        Args:
            target_x: Target X coordinate
            target_y: Target Y coordinate
            steps: Number of interpolation steps

        Returns:
            List of (x, y) coordinates along curve
        """
        # Start from current mouse position (assume 0,0 for simplicity)
        start_x, start_y = 0.0, 0.0

        # Generate 2-4 random control points
        num_control = random.randint(2, 4)
        control_points = []

        for i in range(num_control):
            # Random control points between start and target
            t = (i + 1) / (num_control + 1)
            cx = start_x + (target_x - start_x) * t + random.uniform(-50, 50)
            cy = start_y + (target_y - start_y) * t + random.uniform(-50, 50)
            control_points.append((cx, cy))

        # Cubic Bézier interpolation
        path = []
        for step in range(steps + 1):
            t = step / steps
            x, y = self._cubic_bezier(
                start_x, start_y,
                control_points[0][0], control_points[0][1],
                control_points[1][0], control_points[1][1],
                target_x, target_y,
                t
            )
            path.append((x, y))

        return path

    def _cubic_bezier(
        self,
        x0: float, y0: float,
        x1: float, y1: float,
        x2: float, y2: float,
        x3: float, y3: float,
        t: float
    ) -> Tuple[float, float]:
        """
        Calculate point on cubic Bézier curve at parameter t.

        B(t) = (1-t)³P0 + 3(1-t)²tP1 + 3(1-t)t²P2 + t³P3

        Args:
            x0, y0: Start point
            x1, y1: Control point 1
            x2, y2: Control point 2
            x3, y3: End point
            t: Parameter [0, 1]

        Returns:
            (x, y) coordinates
        """
        u = 1 - t
        u2 = u * u
        u3 = u2 * u
        t2 = t * t
        t3 = t2 * t

        x = u3 * x0 + 3 * u2 * t * x1 + 3 * u * t2 * x2 + t3 * x3
        y = u3 * y0 + 3 * u2 * t * y1 + 3 * u * t2 * y2 + t3 * y3

        return x, y

    async def human_scroll(self, page: Any, direction: str, amount: int) -> None:
        """
        Scroll with human-like smooth acceleration.

        Args:
            page: Playwright page object
            direction: "up" or "down"
            amount: Pixels to scroll
        """
        # Determine scroll direction
        delta = amount if direction == "down" else -amount

        # Smooth scroll in chunks
        chunk_size = 50
        chunks = max(1, abs(delta) // chunk_size)

        for i in range(chunks):
            chunk_delta = delta // chunks
            await page.evaluate(f"window.scrollBy(0, {chunk_delta})")
            await asyncio.sleep(0.02)  # 20ms between chunks

        # Final small adjustment
        remainder = delta % chunks
        if remainder != 0:
            await page.evaluate(f"window.scrollBy(0, {remainder})")
