"""
Smart plug control via tinytuya for GPU PC power management.
"""

import asyncio

import tinytuya

from .config import SmartPlugConfig
from .core.logging import get_logger

log = get_logger("smart_plug")


class SmartPlug:
    """Control a Tuya-based smart plug (LSC, etc.)."""

    def __init__(self, config: SmartPlugConfig):
        self.config = config
        self._device = None

    def _get_device(self) -> tinytuya.OutletDevice:
        """Get or create the device connection."""
        if self._device is None and self.config.enabled:
            self._device = tinytuya.OutletDevice(
                dev_id=self.config.device_id,
                address=self.config.ip_address,
                local_key=self.config.local_key,
                version=self.config.version,
            )
            self._device.set_socketTimeout(5)
        return self._device

    def is_configured(self) -> bool:
        """Check if the plug is properly configured."""
        return (
            self.config.enabled
            and self.config.device_id
            and self.config.ip_address
            and self.config.local_key
        )

    async def turn_on(self) -> bool:
        """Turn on the smart plug."""
        if not self.is_configured():
            log.debug("Not configured, skipping turn_on")
            return False

        def _turn_on():
            device = self._get_device()
            result = device.turn_on()
            return result

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, _turn_on)
            log.info(f"Turn ON result: {result}")
            return True
        except Exception as e:
            log.error(f"Turn ON failed: {e}")
            return False

    async def turn_off(self) -> bool:
        """Turn off the smart plug."""
        if not self.is_configured():
            return False

        def _turn_off():
            device = self._get_device()
            result = device.turn_off()
            return result

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, _turn_off)
            log.info(f"Turn OFF result: {result}")
            return True
        except Exception as e:
            log.error(f"Turn OFF failed: {e}")
            return False

    async def get_status(self) -> dict | None:
        """Get the current status of the plug."""
        if not self.is_configured():
            return None

        def _status():
            device = self._get_device()
            return device.status()

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, _status)
            return result
        except Exception as e:
            log.error(f"Status failed: {e}")
            return None

    async def is_on(self) -> bool | None:
        """Check if the plug is currently on."""
        status = await self.get_status()
        if status and "dps" in status:
            # DPS 1 is usually the power switch
            return status["dps"].get("1", False)
        return None
