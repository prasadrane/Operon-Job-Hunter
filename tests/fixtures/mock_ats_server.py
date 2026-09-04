"""Dynamic Mock ATS Test Server fixture with ephemeral port allocation for Greenhouse and Lever."""

import asyncio
import logging
import socket
import threading
import time
from typing import Optional
from fastapi import FastAPI, Form, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

logger = logging.getLogger(__name__)


def create_mock_ats_app() -> FastAPI:
    """Create FastAPI app with simulated Greenhouse and Lever application and submission flows."""
    app = FastAPI(title="Mock ATS Test Server")

    @app.get("/", response_class=JSONResponse)
    def index():
        return {"status": "ok", "service": "MockATSServer"}

    # =========================================================================
    # Greenhouse Portal Routes
    # =========================================================================
    @app.get("/greenhouse/test_job", response_class=HTMLResponse)
    def get_greenhouse_job():
        return """<!DOCTYPE html>
<html>
<head>
  <title>Greenhouse Test Job Portal</title>
</head>
<body>
  <h1>Apply for Staff Software Engineer at Acme Corp</h1>
  <form id="application_form" action="/greenhouse/submit" method="post" enctype="multipart/form-data">
    <div class="field">
      <label for="first_name">First Name</label>
      <input type="text" id="first_name" name="first_name" required autocomplete="given-name" />
    </div>
    <div class="field">
      <label for="last_name">Last Name</label>
      <input type="text" id="last_name" name="last_name" required autocomplete="family-name" />
    </div>
    <div class="field">
      <label for="email">Email</label>
      <input type="email" id="email" name="email" required autocomplete="email" />
    </div>
    <div class="field">
      <label for="phone">Phone</label>
      <input type="tel" id="phone" name="phone" autocomplete="tel" />
    </div>
    <div class="field">
      <label for="job_application_answers_attributes_0_text_value">LinkedIn Profile</label>
      <input type="text" id="job_application_answers_attributes_0_text_value" name="job_application[answers_attributes][0][text_value]" placeholder="LinkedIn Profile" />
    </div>
    <div class="field">
      <label for="resume">Resume/CV</label>
      <input type="file" id="resume" name="resume" />
    </div>
    <div class="field">
      <input type="submit" id="submit_app" value="Submit Application" />
    </div>
  </form>
</body>
</html>"""

    @app.post("/greenhouse/submit", response_class=HTMLResponse)
    async def submit_greenhouse(request: Request):
        return """<!DOCTYPE html>
<html>
<head><title>Application Submitted</title></head>
<body>
  <div id="application_confirmation">
    <h1>Thank you for applying!</h1>
    <p>Your application for Staff Software Engineer has been received.</p>
    <p class="receipt">Confirmation ID: <strong>GH-CONF-9876</strong></p>
  </div>
</body>
</html>"""

    # =========================================================================
    # Lever Portal Routes
    # =========================================================================
    @app.get("/lever/test_job", response_class=HTMLResponse)
    def get_lever_job():
        return """<!DOCTYPE html>
<html>
<head>
  <title>Lever Test Job Application</title>
</head>
<body>
  <h1>Submit your application - Senior Backend Engineer</h1>
  <form id="application-form" action="/lever/submit" method="post" enctype="multipart/form-data">
    <div class="field">
      <label>Full Name</label>
      <input type="text" name="name" id="name" placeholder="Full name" required />
    </div>
    <div class="field">
      <label>Email</label>
      <input type="email" name="email" id="email" placeholder="Email address" required />
    </div>
    <div class="field">
      <label>Phone</label>
      <input type="tel" name="phone" id="phone" placeholder="Phone number" />
    </div>
    <div class="field">
      <label>LinkedIn URL</label>
      <input type="text" name="urls[LinkedIn]" id="urls-linkedin" placeholder="LinkedIn URL" />
    </div>
    <div class="field">
      <label>Resume</label>
      <input type="file" name="resume" id="resume-file" />
    </div>
    <div class="field">
      <button type="submit" class="template-btn-submit">Submit application</button>
    </div>
  </form>
</body>
</html>"""

    @app.post("/lever/submit", response_class=HTMLResponse)
    async def submit_lever(request: Request):
        return """<!DOCTYPE html>
<html>
<head><title>Application Confirmation</title></head>
<body>
  <div class="application-confirmation">
    <h1>Application submitted!</h1>
    <p>Thank you for submitting your application.</p>
    <p>Confirmation: <strong>LEVER-CONF-5432</strong></p>
  </div>
</body>
</html>"""

    return app


class MockATSServer:
    """Mock ATS HTTP Server for automated testing with dynamic ephemeral port binding."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self.host = host
        self.port = port or self._find_free_port()
        self.app = create_mock_ats_app()
        self.server: Optional[uvicorn.Server] = None
        self.thread: Optional[threading.Thread] = None

    def _find_free_port(self) -> int:
        """Find an available ephemeral port on the host."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((self.host, 0))
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            return int(s.getsockname()[1])

    def start(self) -> None:
        """Start uvicorn server in a background daemon thread."""
        config = uvicorn.Config(
            self.app,
            host=self.host,
            port=self.port,
            log_level="error",
            loop="asyncio"
        )
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()

        # Wait until server is reachable
        max_attempts = 30
        for _ in range(max_attempts):
            try:
                with socket.create_connection((self.host, self.port), timeout=0.1):
                    break
            except (ConnectionRefusedError, OSError):
                time.sleep(0.05)

    def stop(self) -> None:
        """Stop uvicorn server."""
        if self.server:
            self.server.should_exit = True
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)

    def get_base_url(self) -> str:
        """Return base URL string."""
        return f"http://{self.host}:{self.port}"
