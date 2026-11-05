"""Package entry point for the demo Book Admin service."""

from .app import create_app
from .config import Settings

__all__ = ["create_app", "Settings"]
