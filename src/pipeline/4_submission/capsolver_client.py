"""CapSolver API client for automated CAPTCHA solving."""

import logging
import time
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

CAPSOLVER_API_BASE = "https://api.capsolver.com"


class CapSolverError(Exception):
    """Raised when CapSolver API returns an error."""
    pass


class CapSolverTimeoutError(Exception):
    """Raised when CapSolver task times out."""
    pass


class CapSolverClient:
    """Client for CapSolver REST API.

    Supports reCAPTCHA, hCaptcha, and Cloudflare Turnstile solving.
    """

    def __init__(
        self,
        api_key: str,
        timeout_sec: int = 120,
        poll_interval: float = 2.0,
    ) -> None:
        """Initialize CapSolver client.

        Args:
            api_key: CapSolver API key
            timeout_sec: Maximum time to wait for task completion
            poll_interval: Seconds between polling for task result
        """
        self.api_key = api_key
        self.timeout_sec = timeout_sec
        self.poll_interval = poll_interval
        self.client = httpx.Client(timeout=30.0)

    def solve_recaptcha(
        self,
        site_key: str,
        page_url: str,
        **kwargs: Any,
    ) -> str:
        """Solve Google reCAPTCHA v2.

        Args:
            site_key: reCAPTCHA site key from page
            page_url: URL where captcha appears
            **kwargs: Additional parameters (invisible, proxy, etc.)

        Returns:
            Solved token string

        Raises:
            CapSolverError: If API returns error
            CapSolverTimeoutError: If task times out
        """
        task_data = {
            "type": "ReCaptchaV2TaskProxyless",
            "websiteURL": page_url,
            "websiteKey": site_key,
            **kwargs,
        }
        return self._solve_task(task_data)

    def solve_hcaptcha(
        self,
        site_key: str,
        page_url: str,
        **kwargs: Any,
    ) -> str:
        """Solve hCaptcha.

        Args:
            site_key: hCaptcha site key from page
            page_url: URL where captcha appears
            **kwargs: Additional parameters

        Returns:
            Solved token string

        Raises:
            CapSolverError: If API returns error
            CapSolverTimeoutError: If task times out
        """
        task_data = {
            "type": "HCaptchaTaskProxyless",
            "websiteURL": page_url,
            "websiteKey": site_key,
            **kwargs,
        }
        return self._solve_task(task_data)

    def solve_turnstile(
        self,
        site_key: str,
        page_url: str,
        **kwargs: Any,
    ) -> str:
        """Solve Cloudflare Turnstile.

        Args:
            site_key: Turnstile site key from page
            page_url: URL where captcha appears
            **kwargs: Additional parameters

        Returns:
            Solved token string

        Raises:
            CapSolverError: If API returns error
            CapSolverTimeoutError: If task times out
        """
        task_data = {
            "type": "AntiTurnstileTaskProxyless",
            "websiteURL": page_url,
            "websiteKey": site_key,
            **kwargs,
        }
        return self._solve_task(task_data)

    def _solve_task(self, task_data: Dict[str, Any]) -> str:
        """Create and solve a CapSolver task.

        Args:
            task_data: Task configuration dict

        Returns:
            Solved token string

        Raises:
            CapSolverError: If API returns error
            CapSolverTimeoutError: If task times out
        """
        # Step 1: Create task
        create_payload = {
            "clientKey": self.api_key,
            "task": task_data,
        }

        try:
            response = self.client.post(
                f"{CAPSOLVER_API_BASE}/createTask",
                json=create_payload,
            )
            result = response.json()

            if result.get("errorId") != 0:
                error_code = result.get("errorCode", "UNKNOWN_ERROR")
                error_desc = result.get("errorDescription", "No description")
                logger.error("CapSolver create task error: %s - %s", error_code, error_desc)
                raise CapSolverError(f"{error_code}: {error_desc}")

            task_id = result.get("taskId")
            if not task_id:
                raise CapSolverError("No taskId in response")

            logger.info("CapSolver task created: %s", task_id)

        except httpx.RequestError as e:
            logger.error("CapSolver API request error: %s", e)
            raise CapSolverError(f"API request failed: {e}") from e

        # Step 2: Poll for solution
        start_time = time.time()

        while time.time() - start_time < self.timeout_sec:
            time.sleep(self.poll_interval)

            try:
                get_payload = {"clientKey": self.api_key, "taskId": task_id}
                response = self.client.post(
                    f"{CAPSOLVER_API_BASE}/getTaskResult",
                    json=get_payload,
                )
                result = response.json()

                if result.get("errorId") != 0:
                    error_code = result.get("errorCode", "UNKNOWN_ERROR")
                    error_desc = result.get("errorDescription", "No description")
                    logger.error("CapSolver get result error: %s - %s", error_code, error_desc)
                    raise CapSolverError(f"{error_code}: {error_desc}")

                status = result.get("status")
                if status == "ready":
                    solution = result.get("solution", {})
                    token = solution.get("token")
                    if not token:
                        raise CapSolverError("No token in solution")
                    logger.info("CapSolver task solved: %s", task_id)
                    return token

                # Status is "processing" - continue polling
                logger.debug("CapSolver task %s status: %s", task_id, status)

            except httpx.RequestError as e:
                logger.warning("CapSolver polling error: %s", e)
                # Continue polling on transient errors
                continue

        # Timeout reached
        logger.error("CapSolver task %s timed out after %s seconds", task_id, self.timeout_sec)
        raise CapSolverTimeoutError(f"Task {task_id} timed out after {self.timeout_sec} seconds")

    def close(self) -> None:
        """Close HTTP client."""
        self.client.close()

    def __enter__(self) -> "CapSolverClient":
        """Context manager entry."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager exit."""
        self.close()
