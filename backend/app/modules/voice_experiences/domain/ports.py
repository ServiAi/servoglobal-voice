"""Opaque handles supplied by the composition root."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol


class DatabaseSession(Protocol):
    """A unit-of-work handle; only adapters inside the module know its concrete type."""


SessionFactory = Callable[[], DatabaseSession]
