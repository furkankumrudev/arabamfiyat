"""The contract every listing source implements.

The analysis layer never knows where listings came from. A source only has to
yield normalized ``VehicleListing`` records; loading, cleaning and analysis are
the same for demo data, an imported file or a future partner feed.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol

from src.ingestion.schema import VehicleListing


class ListingSource(Protocol):
    """A provider of normalized vehicle listings."""

    #: Stored in the ``source`` column so every row stays traceable to its origin.
    name: str

    def listings(self) -> Iterator[VehicleListing]:
        """Yield the listings this source currently offers."""
        ...
