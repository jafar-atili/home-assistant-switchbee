"""Support for SwitchBee light."""

import logging

from switchbee.device import ApiStateCommand, DeviceType
from switchbee.api import SwitchBeeError, ApiAttribute, ApiStatus

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
        Device(hass, device, coordinator)
        for device in coordinator.data.values()
        if device.type
        in [
            DeviceType.Dimmer,
            DeviceType.Switch,
        ]
    )


class Device(CoordinatorEntity, LightEntity):
    """Representation of an SwitchBee light."""

    def __init__(self, hass, device, coordinator):
        """Initialize the SwitchBee light."""
        super().__init__(coordinator)
        self._session = aiohttp_client.async_get_clientsession(hass)
        self._attr_name = device.name
        self._device_id = device.id
        self._attr_unique_id = f"{self.coordinator.api.mac}-{device.id}"
        self._is_dimmer = device.type == DeviceType.Dimmer
        self._attr_device_info = DeviceInfo(
            identifiers={
                (DOMAIN, self._attr_unique_id),
            },
            manufacturer="SwitchBee",
            model=device.type.display,
            name=self.name,
            suggested_area=device.zone,
        )
        self._attr_is_on = False
        self._attr_brightness = 0
        self._attr_supported_features = SUPPORT_BRIGHTNESS if self._is_dimmer else 0
        self._last_brightness = None
        self.dev_availble = False

    @property
    def available(self) -> bool:
        """Available."""
        return self.dev_availble

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""

        if self._is_dimmer:
            if self.coordinator.data[self._device_id].brightness == -1:
                self.dev_availble = False
                return None

            self.dev_availble = True
            state = self.coordinator.data[self._device_id].brightness

            if state <= 2:
                self._attr_is_on = False
            else:
                self._attr_is_on = True

                self._attr_brightness = brightness_switchbee_to_hass(state)
                self._last_brightness = self._attr_brightness
        else:
            if self.coordinator.data[self._device_id].state == -1:
                self.dev_availble = False
                return None

            self.dev_availble = True
            self._attr_is_on = (
                True
                if self.coordinator.data[self._device_id].state == ApiStateCommand.ON
                else False
            )

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
                state = ApiStateCommand.ON
            else:
                state = brightness_hass_to_switchbee(self._last_brightness)

        try:
            ret = await self.coordinator.api.set_state(self._device_id, state)
        except SwitchBeeError as exp:
            _LOGGER.error(
                "Failed to set %s state %s, error: %s", self._attr_name, state, exp
            )
            self._attr_is_on = False
            self._async_write_ha_state()
        else:
            if ret[ApiAttribute.STATUS] == ApiStatus.OK:
                if self._is_dimmer:
                    self.coordinator.data[self._device_id].brightness = state
                else:
                    self.coordinator.data[self._device_id].state = state
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
                self._attr_is_on = False
                self._async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        """Turn off SwitchBee light."""
        try:
            ret = await self.coordinator.api.set_state(
                self._device_id, ApiStateCommand.OFF
            )
        except SwitchBeeError as exp:
            _LOGGER.error("Failed to turn off %s, error: %s", self._attr_name, exp)
            self._attr_is_on = True
            self._async_write_ha_state()
        else:
            if ret[ApiAttribute.STATUS] == ApiStatus.OK:
                if self._is_dimmer:
                    self.coordinator.data[self._device_id].brightness = 0
                else:
                    self.coordinator.data[self._device_id].state = ApiStateCommand.OFF
                self.coordinator.async_set_updated_data(self.coordinator.data)
            else:
                _LOGGER.error("Failed to turn off %s, error: %s", self._attr_name, ret)
                self._attr_is_on = True
                self._async_write_ha_state()
