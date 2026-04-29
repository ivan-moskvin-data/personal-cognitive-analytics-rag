"""Модуль UI для PCAR на базе NiceGUI."""

from .state import AppState
from .layout import render_layout
from .chat import render_chat
from .inbox import render_inbox
from .analytics import render_dashboard, render_telemetry

__all__ = [
    "AppState",
    "render_layout",
    "render_chat",
    "render_inbox",
    "render_dashboard",
    "render_telemetry",
]
