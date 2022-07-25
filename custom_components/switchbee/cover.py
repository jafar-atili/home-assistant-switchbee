"""Support for SwitchBee cover."""

import logging

from asyncio import sleep
from switchbee.device import SwitchBeeShutter, DeviceType
from switchbee.api import (
    SwitchBeeError,
    SwitchBeeTokenError,
    SwitchBeeDeviceOfflineError,
)

from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up SwitchBee switch."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        Device(hass, device, coordinator)
        for device in coordinator.data.values()
        if device.type == DeviceType.Shutter
    )


class Device(CoordinatorEntity, CoverEntity):
    """Representation of an SwitchBee cover."""

    def __init__(self, hass, device: SwitchBeeShutter, coordinator):
        """Initialize the SwitchBee cover."""
        super().__init__(coordinator)
        self._session = aiohttp_client.async_get_clientsession(hass)
        self._attr_name = device.name
        self._attr_unique_id = f"{self.coordinator.api.mac}-{device.id}"
        self._device_id = device.id
        self._attr_device_info = DeviceInfo(
            identifiers={
                (DOMAIN, self._attr_unique_id),
            },
            manufacturer="SwitchBee",
            model=device.type.display,
            name=self.name,
            suggested_area=device.zone,
        )
        self._attr_current_cover_position = 0
        self._attr_is_closed = True
        self._attr_supported_features = (
            CoverEntityFeature.CLOSE
            | CoverEntityFeature.OPEN
            | CoverEntityFeature.SET_POSITION
            | CoverEntityFeature.STOP
        )
        self._attr_assumed_state = False
        self._attr_device_class = CoverDeviceClass.SHUTTER
        self._attr_available = True

    @property
    def available(self) -> bool:
        return self._attr_available

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""

        async def async_refresh_state():
            try:
                await self.coordinator.api.set_state(self._device_id, "dummy")
            except SwitchBeeDeviceOfflineError:
                return
            except SwitchBeeError:
                return

        if int(self.coordinator.data[self._device_id].position) == -1:
            self.hass.async_create_task(async_refresh_state())
            if self.available:
                _LOGGER.error(
                    "%s shutter is not responding, check the status in the SwitchBee mobile app",
                    self.name,
                )
            self._attr_available = False
            self.async_write_ha_state()
            return None

        if not self.available:
            _LOGGER.info("%s shutter is now responding", self.name)
            self._attr_available = True

        self._attr_current_cover_position = self.coordinator.data[
            self._device_id
        ].position

        if self._attr_current_cover_position == 0:
            self._attr_is_closed = True
        else:
            self._attr_is_closed = False
        super()._handle_coordinator_update()

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        self._handle_coordinator_update()

    async def async_open_cover(self, **kwargs):
        """Open the cover."""
        if self._attr_current_cover_position == 100:
            return
        await self.async_set_cover_position(position=100)

    async def async_close_cover(self, **kwargs):
        """Close the cover."""
        if self._attr_current_cover_position == 0:
            return
        await self.async_set_cover_position(position=0)

    async def _update_cover_position_from_central_unit(self):
        """Set the cover position in HAAS based on the central unit."""
        try:
            curr_pos = await self.coordinator.api.get_state(self._device_id)
            curr_pos = curr_pos["data"]
        except (SwitchBeeError, SwitchBeeDeviceOfflineError) as exp:
            _LOGGER.error("Failed to get %s position, error: %s", self._attr_name, exp)
            self.async_write_ha_state()
            return -1
        else:
            self.coordinator.data[self._device_id].position = curr_pos
            self.coordinator.async_set_updated_data(self.coordinator.data)

    async def async_stop_cover(self, **kwargs):
        """Stop a moving cover."""
        # to stop the shutter, we just interrupt it with any state during operation
        await self.async_set_cover_position(
            position=self.current_cover_position, force=True
        )
        # wait 2 seconds and update the current position in the entity
        await sleep(2)
        await self._update_cover_position_from_central_unit()

    async def async_set_cover_position(self, **kwargs):
        """Async function to set position to cover."""
        last_position = self._attr_current_cover_position
        if (
            self._attr_current_cover_position == kwargs[ATTR_POSITION]
            and "force" not in kwargs
        ):
            return
        try:
            await self.coordinator.api.set_state(self._device_id, kwargs[ATTR_POSITION])
        except (SwitchBeeError, SwitchBeeTokenError) as exp:
            _LOGGER.error(
                "Failed to set %s position to %s, error: %s",
                self._attr_name,
                str(kwargs[ATTR_POSITION]),
                exp,
            )
            self._attr_current_cover_position = last_position
            _LOGGER.info("Restoring to %i", last_position)
            self.async_write_ha_state()
            return

        self.coordinator.data[self._device_id].position = kwargs[ATTR_POSITION]
        self.coordinator.async_set_updated_data(self.coordinator.data)
        self.async_write_ha_state()
