"""Shared test fixtures and a network guard.

The suite is strictly offline. To make that guarantee enforceable rather than
aspirational, we monkeypatch ``socket.socket`` so any accidental network call
raises loudly instead of silently reaching out.
"""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"


@pytest.fixture(scope="session")
def strong_text() -> str:
    """The strong, GEO-ready sample article as raw Markdown."""
    return (SAMPLES_DIR / "strong.md").read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def weak_text() -> str:
    """The weak sample article as raw Markdown."""
    return (SAMPLES_DIR / "weak.md").read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail any test that tries to open a socket — the suite must stay offline."""

    def _blocked(*args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("Network access is not allowed in tests.")

    monkeypatch.setattr(socket, "socket", _blocked)
