"""Stage capability introspection for agents (P5a)."""
from .stage_registry import (
    StageCapability, StageDescriptor, can_handle, get_capability,
    list_capabilities, run_stage,
)

__all__ = ["StageCapability", "StageDescriptor", "can_handle", "get_capability",
           "list_capabilities", "run_stage"]
