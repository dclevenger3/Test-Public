"""Connectors pull courses and assignments from a specific LMS behind ClassLink."""

from .base import Connector
from .canvas import CanvasConnector
from .canvas_feed import CanvasFeedConnector
from .google_classroom import GoogleClassroomConnector

REGISTRY: dict[str, type[Connector]] = {
    "canvas": CanvasConnector,
    "canvas_feed": CanvasFeedConnector,
    "google_classroom": GoogleClassroomConnector,
}

__all__ = ["Connector", "REGISTRY", "CanvasConnector", "CanvasFeedConnector", "GoogleClassroomConnector"]
