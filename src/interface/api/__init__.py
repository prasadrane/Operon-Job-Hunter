"""FastAPI REST API package for CareerGraph AI."""

from src.interface.api.routes import app
from src.interface.api.routes_v2 import app_v2

__all__ = ["app", "app_v2"]
