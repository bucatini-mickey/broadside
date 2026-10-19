# Minimal synchronous pub/sub event bus for genuinely cross-cutting
# notifications (e.g. "a mast was just dismasted") that multiple unrelated
# systems care about. Day-to-day state changes should still be plain ECS
# component reads/writes, not routed through here - see the "Event bus"
# section of docs/design/01_architecture.md for the distinction.

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class EventBus:
    _handlers: dict[str, list[Callable[[Any], None]]] = field(
        default_factory=lambda: defaultdict(list)
    )

    def subscribe(self, event_name: str, handler: Callable[[Any], None]) -> None:
        self._handlers[event_name].append(handler)

    def publish(self, event_name: str, payload: Any = None) -> None:
        for handler in self._handlers.get(event_name, ()):
            handler(payload)
