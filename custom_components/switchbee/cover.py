"""Support for SwitchBee cover."""

import logging
import time

import switchbee

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

DEVICE_CLASS_MAP = {
    "SHUTTER": CoverDeviceClass.SHUTTER,
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up SwitchBee switch."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        Device(hass, coordinator.data[device], coordinator)
        for device in coordinator.data
        if coordinator.data[device]["type"] == switchbee.TYPE_SHUTTER
    )


class Device(CoordinatorEntity, CoverEntity):
    """Representation of an SwitchBee cover."""

    def __init__(self, hass, device, coordinator):
        """Initialize the SwitchBee cover."""
        super().__init__(coordinator)
        self._session = aiohttp_client.async_get_clientsession(hass)
        self._attr_name = device["name"]
        self._attr_unique_id = device["uid"]
        self._device_id = device[switchbee.ATTR_ID]
        self._attr_device_info = DeviceInfo(
            identifiers={
                (DOMAIN, device["uid"]),
            },
            manufacturer="SwitchBee",
            model=device["type"],
            name=self.name,
            suggested_area=device["area"],
        )
        self._attr_current_cover_position = 0
        self._attr_is_closed = True
        self._attr_supported_features = (
            CoverEntityFeature.CLOSE
            | CoverEntityFeature.OPEN
            | CoverEntityFeature.SET_POSITION
            | CoverEntityFeature.STOP
        )
        self._attr_device_class = DEVICE_CLASS_MAP[device["type"]]

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        position = self.coordinator.data[self._device_id][switchbee.ATTR_STATE]
        if isinstance(position, str) and position == switchbee.STATE_OFF:
            self._attr_current_cover_position = 0
        elif isinstance(position, int):
            self._attr_current_cover_position = position

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
            curr_pos = curr_pos[switchbee.ATTR_DATA]
        except switchbee.SwitchBeeError as exp:
            _LOGGER.error("Failed to get %s position, error: %s", self._attr_name, exp)
            return -1
        else:
            self.coordinator.data[self._device_id][switchbee.ATTR_STATE] = curr_pos
            self.coordinator.async_set_updated_data(self.coordinator.data)

    async def async_stop_cover(self, **kwargs):
        """Stop a moving cover."""
        # to stop the shutter, we just interrupt it with any state during operation
        await self.async_set_cover_position(
            position=self.current_cover_position, force=True
        )
        # wait 2 seconds and update the current position in the entity
        time.sleep(2)
        await self._update_cover_position_from_central_unit()

    async def async_set_cover_position(self, **kwargs):
        """Async function to set position to cover."""
        if (
            self._attr_current_cover_position == kwargs[ATTR_POSITION]
            and "force" not in kwargs
        ):
            return
        try:
            ret = await self.coordinator.api.set_state(
                self._device_id, kwargs[ATTR_POSITION]
            )
        except switchbee.SwitchBeeError as exp:
            _LOGGER.error(
                "Failed to set %s position to %s, error: %s",
                self._attr_name,
                str(kwargs[ATTR_POSITION]),
                exp,
            )

        else:
            if ret[switchbee.ATTR_STATUS] == switchbee.STATUS_OK:
                self.coordinator.data[self._device_id][switchbee.ATTR_STATE] = kwargs[
                    ATTR_POSITION
                ]
                self.coordinator.async_set_updated_data(self.coordinator.data)
            else:
                _LOGGER.error(
                    "Failed to set %s position to %s, error: %s",
                    self._attr_name,
                    str(kwargs[ATTR_POSITION]),
                    ret,
                )
