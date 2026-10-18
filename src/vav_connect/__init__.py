"""SDK communautaire asynchrone pour VAV Connect/Otodo (lecture seule)."""

from .auth import SessionTokens
from .client import VAVClient
from .enums import PilotMode, WorkingMode
from .exceptions import APIError, AuthenticationError, ProtocolError, RateLimitError, TransportError, VAVError
from .models import Capability, Device, DeviceReference, Holidays, Home, Hub, Room, Snapshot, Thermostat, WeekEvent, ZoneReading

__version__ = "0.1.1"

__all__ = [
    "APIError", "AuthenticationError", "Capability", "Device", "DeviceReference",
    "Holidays", "Home", "Hub", "PilotMode", "ProtocolError", "RateLimitError",
    "Room", "SessionTokens", "Snapshot", "Thermostat", "TransportError",
    "VAVClient", "VAVError", "WeekEvent", "WorkingMode", "ZoneReading",
]
