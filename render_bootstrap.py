"""Render-friendly Streamlit launcher with safe signal handling.

Render occasionally invokes the Streamlit runtime from a worker thread,
which raises ``ValueError: signal only works in main thread`` on Python 3.13.
This entrypoint patches the Streamlit bootstrap signal handler to no-op when
running outside the main thread and sets the required config defaults for
Render deployments before starting the app.
"""
from __future__ import annotations

import os
import threading
from typing import Any

from streamlit.web import bootstrap
from streamlit.web import cli as stcli

# Keep a reference to the original handler so we can call it when safe.
_original_set_up_signal_handler = bootstrap._set_up_signal_handler


def _safe_set_up_signal_handler(server: Any) -> None:
    """Install the Streamlit signal handler only from the main thread.

    Render sometimes runs the Streamlit runtime in a background thread on
    Python 3.13, which causes ``signal.signal`` to raise. Skipping the
    handler in that scenario prevents the crash while preserving the normal
    shutdown behavior when we are on the main thread (local dev, most hosts).
    """

    if threading.current_thread() is threading.main_thread():
        _original_set_up_signal_handler(server)
    else:
        # Fall back to default asyncio cancellation; Render will still stop
        # the dyno/container cleanly.
        pass


# Patch the bootstrap to use the thread-aware variant.
bootstrap._set_up_signal_handler = _safe_set_up_signal_handler  # type: ignore[attr-defined]


def _apply_render_defaults() -> None:
    """Ensure Streamlit runs with the expected Render configuration."""

    os.environ.setdefault("STREAMLIT_SERVER_ADDRESS", "0.0.0.0")
    os.environ.setdefault("STREAMLIT_SERVER_PORT", os.getenv("PORT", "8501"))
    os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")
    os.environ.setdefault("STREAMLIT_BROWSER_GATHERUSAGESTATS", "false")


if __name__ == "__main__":
    _apply_render_defaults()
    stcli._main_run("main.py")
