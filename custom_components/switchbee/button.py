"""Support for SwitchBee scenario button."""
import logging

import switchbee

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Switchbee button."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        Device(hass, coordinator.data[device], coordinator)
        for device in coordinator.data
        if coordinator.data[device]["type"]
        in [
            switchbee.TYPE_SCENARIO,
        ]
    )


class Device(CoordinatorEntity, ButtonEntity):
    """Representation of an Switchbee button."""

    def __init__(self, hass, device, coordinator):
        """Initialize the Switchbee switch."""
        super().__init__(coordinator)
        self._session = aiohttp_client.async_get_clientsession(hass)
        self._attr_name = device["name"]
        self._device_id = device[switchbee.ATTR_ID]
        self._attr_unique_id = device["uid"]

    async def async_press(self):
        """Fire the scenario in the SwitchBee hub."""
        try:
            ret = await self.coordinator.api.set_state(
                self._device_id, switchbee.STATE_ON
            )
        except switchbee.SwitchBeeError as exp:
            _LOGGER.error("Failed to fire scenario %s, error: %s", self._attr_name, exp)
        else:
            if ret[switchbee.ATTR_STATUS] == switchbee.STATUS_OK:
                self.coordinator.data[self._device_id][
                    switchbee.ATTR_STATE
                ] = switchbee.STATE_ON
                self.coordinator.async_set_updated_data(self.coordinator.data)
            else:
                _LOGGER.error(
                    "Failed to fire scenario %s: error: %s", self._attr_name, ret
                )
