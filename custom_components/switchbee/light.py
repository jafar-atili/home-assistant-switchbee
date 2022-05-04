"""Support for SwitchBee light."""

import logging

import switchbee

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    SUPPORT_BRIGHTNESS,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

MAX_BRIGHTNESS = 255

_LOGGER = logging.getLogger(__name__)


def brightness_hass_to_switchbee(value: int):
    """Convert hass brightness to SwitchBee."""
    return int((value * 100) / MAX_BRIGHTNESS)


def brightness_switchbee_to_hass(value: int):
    """Convert SwitchBee brightness to hass."""
    return int((value * MAX_BRIGHTNESS) / 100)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up SwitchBee light."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        Device(hass, coordinator.data[device], coordinator)
        for device in coordinator.data
        if coordinator.data[device]["type"] == switchbee.TYPE_DIMMER
    )


class Device(CoordinatorEntity, LightEntity):
    """Representation of an SwitchBee light."""

    def __init__(self, hass, device, coordinator):
        """Initialize the SwitchBee light."""
        super().__init__(coordinator)
        self._session = aiohttp_client.async_get_clientsession(hass)
        self._attr_name = device["name"]
        self._device_id = device[switchbee.ATTR_ID]
        self._attr_unique_id = device["uid"]
        self._attr_device_info = DeviceInfo(
            identifiers={
                (DOMAIN, device["uid"]),
            },
            manufacturer="SwitchBee",
            model="Dimmer",
            name=self.name,
        )
        self._attr_is_on = False
        self._attr_brightness = 0
        self._attr_supported_features = SUPPORT_BRIGHTNESS
        self._last_brightness = None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        state = self.coordinator.data[self._device_id][switchbee.ATTR_STATE]
        # the state can be one of the following:
        #  OFF --> Means brightness is 0
        #  ON --> Means Brightness is 100
        #  Positive Integer --> current brightness
        if isinstance(state, str):
            if state == switchbee.STATE_OFF:
                self._attr_is_on = False
                self._attr_brightness = 0

            else:
                # ON
                self._attr_is_on = True
                self._attr_brightness = 100

        elif isinstance(state, int):
            if state <= 2:
                self._attr_is_on = False
            else:
                self._attr_is_on = True

                self._attr_brightness = brightness_switchbee_to_hass(state)
                self._last_brightness = self._attr_brightness

        super()._handle_coordinator_update()

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        self._handle_coordinator_update()

    async def async_turn_on(self, **kwargs):
        """Async function to set on to light."""

        if ATTR_BRIGHTNESS in kwargs:
            if brightness_hass_to_switchbee(kwargs[ATTR_BRIGHTNESS]) <= 2:
                state = 0
            else:
                state = brightness_hass_to_switchbee(kwargs[ATTR_BRIGHTNESS])

        else:
            # Set the last brightness we know
            if not self._last_brightness:
                # First turn on, set the light brightness to the last brightness the HUB remembers
                state = switchbee.STATE_ON
            else:
                state = brightness_hass_to_switchbee(self._last_brightness)

        try:
            ret = await self.coordinator.api.set_state(self._device_id, state)
        except switchbee.SwitchBeeError as exp:
            _LOGGER.error(
                "Failed to set %s state %s, error: %s", self._attr_name, state, exp
            )
        else:
            if ret[switchbee.ATTR_STATUS] == switchbee.STATUS_OK:
                self.coordinator.data[self._device_id][switchbee.ATTR_STATE] = state
                if (
                    ATTR_BRIGHTNESS in kwargs
                    and brightness_hass_to_switchbee(kwargs[ATTR_BRIGHTNESS]) >= 2
                ):
                    self._last_brightness = kwargs[ATTR_BRIGHTNESS]
                self.coordinator.async_set_updated_data(self.coordinator.data)
            else:
                _LOGGER.error(
                    "Failed to set %s state to %s: error %s",
                    self._attr_name,
                    str(state),
                    ret,
                )

    async def async_turn_off(self, **kwargs):
        """Turn off SwitchBee light."""
        try:
            ret = await self.coordinator.api.set_state(
                self._device_id, switchbee.STATE_OFF
            )
        except switchbee.SwitchBeeError as exp:
            _LOGGER.error("Failed to turn off %s, error: %s", self._attr_name, exp)
        else:
            if ret[switchbee.ATTR_STATUS] == switchbee.STATUS_OK:
                self.coordinator.data[self._device_id][
                    switchbee.ATTR_STATE
                ] = switchbee.STATE_OFF
                self.coordinator.async_set_updated_data(self.coordinator.data)
            else:
                _LOGGER.error("Failed to turn off %s, error: %s", self._attr_name, ret)
