"""Synthetic match simulator for PULSE."""

from .generator import Scenario, generate
from .scenarios import BALANCED, DEMO_HIGH_PRESS, SCENARIOS

__all__ = ["BALANCED", "DEMO_HIGH_PRESS", "SCENARIOS", "Scenario", "generate"]
