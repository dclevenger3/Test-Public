"""Connectors pull courses and assignments from a specific LMS behind ClassLink."""

from .base import Connector
from .canvas import CanvasConnector
from .google_classroom import GoogleClassroomConnector

REGISTRY: dict[str, type[Connector]] = {
    "canvas": CanvasConnector,
    "google_classroom": GoogleClassroomConnector,
}

__all__ = ["Connector", "REGISTRY", "CanvasConnector", "GoogleClassroomConnector"]
