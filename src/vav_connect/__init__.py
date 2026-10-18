"""SDK communautaire asynchrone pour VAV Connect/Otodo (lecture seule)."""

from .auth import SessionTokens
from .client import VAVClient
from .enums import PilotMode, WorkingMode
from .exceptions import (
    APIError, AuthenticationError, ForbiddenError, ProtocolError,
    RateLimitError, TokenPersistenceError, TransportError, VAVError,
)
from .models import Capability, Device, DeviceReference, Holidays, Home, Hub, Room, Snapshot, Thermostat, WeekEvent, ZoneReading

__version__ = "0.2.0"

__all__ = [
    "APIError", "AuthenticationError", "Capability", "Device", "DeviceReference",
    "ForbiddenError", "Holidays", "Home", "Hub", "PilotMode", "ProtocolError", "RateLimitError",
    "Room", "SessionTokens", "Snapshot", "Thermostat", "TokenPersistenceError", "TransportError",
    "VAVClient", "VAVError", "WeekEvent", "WorkingMode", "ZoneReading",
]
