"""Home Assistant sensor platform entry point.

Sensor implementations live in ``sensors.py`` so they are kept in one place
and can be removed or changed as a group without touching the platform loader.
"""

from .sensors import async_setup_entry

__all__ = ["async_setup_entry"]
