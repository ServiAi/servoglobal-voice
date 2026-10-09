from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Command(Mapping[str, object]):
    """Validated request data translated at the HTTP boundary."""

    values: Mapping[str, object]

    def __getattr__(self, name: str) -> object:
        try:
            value = self.values[name]
            return Command(value) if isinstance(value, Mapping) else value
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __getitem__(self, key: str) -> object:
        return self.values[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.values)

    def __len__(self) -> int:
        return len(self.values)

    def as_mapping(self) -> Mapping[str, object]:
        return self.values


class View(Mapping[str, object]):
    """Framework-free application result accepted by API response models."""

    __slots__ = ("_values",)

    def __init__(self, **values: object) -> None:
        self._values = values

    def __getitem__(self, key: str) -> object:
        return self._values[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def __getattr__(self, name: str) -> object:
        try:
            value = self._values[name]
            return View(**value) if isinstance(value, Mapping) else value
        except KeyError as exc:
            raise AttributeError(name) from exc
