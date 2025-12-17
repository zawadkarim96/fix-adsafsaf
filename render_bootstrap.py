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


def _apply_render_defaults() -> dict[str, Any]:
    """Ensure Streamlit runs with the expected Render configuration.

    The returned dict is safe to pass directly to ``bootstrap.run`` so the
    server always binds to the Render-provided ``$PORT`` even if Streamlit
    ignores the corresponding environment variables.
    """

    # Normalize the environment so both Streamlit and Render agree on which
    # interface/port to bind. We also mirror the computed value back into
    # ``PORT`` because some platforms (and older Streamlit builds) still
    # prefer reading that variable directly.
    os.environ.setdefault("STREAMLIT_SERVER_ADDRESS", "0.0.0.0")
    os.environ.setdefault("STREAMLIT_SERVER_PORT", os.getenv("PORT", "8501"))
    os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")
    os.environ.setdefault("STREAMLIT_BROWSER_GATHERUSAGESTATS", "false")

    # Explicitly pass the address/port to the bootstrapper so deployments bind
    # to the externally-provided port even if environment parsing changes.
    port_env = os.environ["STREAMLIT_SERVER_PORT"].strip()
    try:
        port = int(port_env)
    except ValueError:
        # Fallback to a safe default and update the environment so the value
        # stays consistent everywhere the port is read.
        port = 8501
    os.environ["PORT"] = str(port)

    return {
        "server.address": os.environ["STREAMLIT_SERVER_ADDRESS"],
        "server.port": port,
        "server.headless": os.environ["STREAMLIT_SERVER_HEADLESS"].lower()
        == "true",
        "browser.gatherUsageStats": os.environ["STREAMLIT_BROWSER_GATHERUSAGESTATS"].lower()
        == "true",
    }


if __name__ == "__main__":
    flag_options = _apply_render_defaults()
    app_path = os.path.join(os.path.dirname(__file__), "main.py")
    # Invoke the Streamlit runner directly instead of the Click-driven CLI to
    # avoid ``RuntimeError: There is no active click context`` when Railway
    # launches the app without a Click context.
    bootstrap.run(
        app_path,
        is_hello=False,
        args=[],
        flag_options=flag_options,
    )
