"""Specialized 5-Agent Discovery Squad for CareerGraph AI."""

from .base import BaseDiscoveryAgent
from .scout_falcon import ScoutFalconAgent
from .scout_atlas import ScoutAtlasAgent
from .scout_titan import ScoutTitanAgent
from .scout_horizon import ScoutHorizonAgent
from .scout_aegis import ScoutAegisAgent
from .discovery_squad import DiscoverySquadOrchestrator

__all__ = [
    "BaseDiscoveryAgent",
    "ScoutFalconAgent",
    "ScoutAtlasAgent",
    "ScoutTitanAgent",
    "ScoutHorizonAgent",
    "ScoutAegisAgent",
    "DiscoverySquadOrchestrator",
]
