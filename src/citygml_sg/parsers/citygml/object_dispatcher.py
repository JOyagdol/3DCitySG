"""Dispatch raw XML elements to module-level handlers."""

from __future__ import annotations

from collections.abc import Callable
from xml.etree.ElementTree import Element

Handler = Callable[[Element], dict]


class ObjectDispatcher:
    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}

    def register(self, tag: str, handler: Handler) -> None:
        self._handlers[tag] = handler

    def dispatch(self, element: Element) -> dict:
        handler = self._handlers.get(element.tag)
        if handler is None:
            return {"tag": element.tag, "status": "unhandled"}
        return handler(element)
