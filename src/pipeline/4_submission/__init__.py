"""Stage 4: Playwright Persistent Browser Submitter & ATS Adapters."""

from .browser_manager import BrowserManager
from .captcha_handler import CaptchaHandler
from .submitter_engine import SubmitterEngine
from .adapters import (
    BaseATSAdapter,
    GreenhouseAdapter,
    LeverAdapter,
    AshbyAdapter,
    WorkdayAdapter,
    GenericAdapter,
    get_adapter,
)

from .axtree_parser import (
    AXNode,
    AXTreeParser,
    inject_bid_attributes,
    inject_bid_attributes_async,
)
from .som_annotator import SetOfMarksAnnotator

from .websurfer_agent import WebSurferAgent
from .action_dispatcher import ActionDispatcher

__all__ = [
    "BrowserManager",
    "CaptchaHandler",
    "SubmitterEngine",
    "BaseATSAdapter",
    "GreenhouseAdapter",
    "LeverAdapter",
    "AshbyAdapter",
    "WorkdayAdapter",
    "GenericAdapter",
    "get_adapter",
    "AXNode",
    "AXTreeParser",
    "inject_bid_attributes",
    "inject_bid_attributes_async",
    "SetOfMarksAnnotator",
    "WebSurferAgent",
    "ActionDispatcher",
]

