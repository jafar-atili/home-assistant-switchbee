"""Support for SwitchBee switch."""
import logging

from switchbee.api import SwitchBeeError, SwitchBeeDeviceOfflineError
from switchbee.device import ApiStateCommand, DeviceType

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONF_SWITCHES_AS_LIGHTS

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Switchbee switch."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    switch_as_light = entry.data[CONF_SWITCHES_AS_LIGHTS]
    device_types = (
        [DeviceType.TimedPowerSwitch, DeviceType.GroupSwitch, DeviceType.TimedSwitch]
        if switch_as_light
        else [
            DeviceType.TimedPowerSwitch,
            DeviceType.GroupSwitch,
            DeviceType.Switch,
            DeviceType.TimedSwitch,
        ]
    )

    async_add_entities(
        Device(hass, device, coordinator)
        for device in coordinator.data.values()
        if device.type in device_types
    )


class Device(CoordinatorEntity, SwitchEntity):
    """Representation of an Switchbee switch."""

    def __init__(self, hass, device, coordinator):
        """Initialize the Switchbee switch."""
        super().__init__(coordinator)
        self._session = aiohttp_client.async_get_clientsession(hass)
        self._attr_name = f"{device.zone} {device.name}"
        self._device_id = device.id
        self._attr_unique_id = f"{coordinator.mac_formated}-{device.id}"
        self._attr_is_on = False
        self._attr_available = True
        self._attr_has_entity_name = True

    @property
    def available(self) -> bool:
        """Available."""
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

        if self.coordinator.data[self._device_id].state == -1:
            # This specific call will refresh the state of the device in the CU
            self.hass.async_create_task(async_refresh_state())

            if self.available:
                _LOGGER.error(
                    "%s switch is not responding, check the status in the SwitchBee mobile app",
                    self.name,
                )
            self._attr_available = False
            self.async_write_ha_state()
            return None
        else:
            if not self.available:
                _LOGGER.info(
                    "%s switch is now responding",
                    self.name,
                )
            self._attr_available = True

        # timed power switch state will represent a number of minutes until it goes off
        # regulare switches state is ON/OFF
        self._attr_is_on = (
            self.coordinator.data[self._device_id].state != ApiStateCommand.OFF
        )

        super()._handle_coordinator_update()

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        self._handle_coordinator_update()

    async def async_turn_on(self, **kwargs):
        """Async function to set on to switch."""
        return await self._async_set_state(ApiStateCommand.ON)

    async def async_turn_off(self, **kwargs):
        """Async function to set off to switch."""
        return await self._async_set_state(ApiStateCommand.OFF)

    async def _async_set_state(self, state):
        try:
            await self.coordinator.api.set_state(self._device_id, state)
        except (SwitchBeeError, SwitchBeeDeviceOfflineError) as exp:
            _LOGGER.error(
                "Failed to set %s state %s, error: %s", self._attr_name, state, exp
            )
            self._async_write_ha_state()
        else:
            await self.coordinator.async_refresh()
