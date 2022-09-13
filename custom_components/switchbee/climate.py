"""Support for SwitchBee thermostat button."""
from __future__ import annotations
import logging
from typing import Any

from switchbee.device import (
    DeviceType,
    ApiStateCommand,
    SwitchBeeThermostat,
)

from switchbee import SWITCHBEE_BRAND

from switchbee.const import (
    ThermostatFanSpeed,
    ThermostatMode,
    ThermostatTemperatureUnit,
    ApiAttribute,
)
from switchbee.api import SwitchBeeError, SwitchBeeDeviceOfflineError
from homeassistant.const import ATTR_TEMPERATURE, TEMP_CELSIUS, TEMP_FAHRENHEIT

from homeassistant.config_entries import ConfigEntry
from homeassistant.components.climate import ClimateEntity
from homeassistant.helpers import aiohttp_client

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.climate.const import (
    HVACAction,
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    ClimateEntityFeature,
    HVACMode,
)


from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


FAN_SB_TO_HASS = {
    ThermostatFanSpeed.AUTO: FAN_AUTO,
    ThermostatFanSpeed.LOW: FAN_LOW,
    ThermostatFanSpeed.MEDIUM: FAN_MEDIUM,
    ThermostatFanSpeed.HIGH: FAN_HIGH,
}

FAN_HASS_TO_SB = {
    FAN_AUTO: ThermostatFanSpeed.AUTO,
    FAN_LOW: ThermostatFanSpeed.LOW,
    FAN_MEDIUM: ThermostatFanSpeed.MEDIUM,
    FAN_HIGH: ThermostatFanSpeed.HIGH,
}

HVAC_MODE_SB_TO_HASS = {
    ThermostatMode.COOL: HVACMode.COOL,
    ThermostatMode.HEAT: HVACMode.HEAT,
    ThermostatMode.FAN: HVACMode.FAN_ONLY,
}

HVAC_MODE_HASS_TO_SB = {
    HVACMode.COOL: ThermostatMode.COOL,
    HVACMode.HEAT: ThermostatMode.HEAT,
    HVACMode.FAN_ONLY: ThermostatMode.FAN,
}

HVAC_ACTION_SB_TO_HASS = {
    ThermostatMode.COOL: HVACAction.COOLING,
    ThermostatMode.HEAT: HVACAction.HEATING,
    ThermostatMode.FAN: HVACAction.FAN,
}

HVAC_UNIT_SB_TO_HASS = {
    ThermostatTemperatureUnit.CELSIUS: TEMP_CELSIUS,
    ThermostatTemperatureUnit.FAHRENHEIT: TEMP_FAHRENHEIT,
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Switchbee thermostat."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        Device(hass, device, coordinator)
        for device in coordinator.data.values()
        if device.type == DeviceType.Thermostat
    )


class Device(CoordinatorEntity, ClimateEntity):
    """Representation of an Switchbee button."""

    def __init__(self, hass, device: SwitchBeeThermostat, coordinator):
        """Initialize the Switchbee switch."""
        super().__init__(coordinator)
        self._session = aiohttp_client.async_get_clientsession(hass)
        self._attr_name = f"{device.zone} {device.name}"
        self._device_id = device.id
        self._attr_unique_id = f"{coordinator.mac_formated}-{device.id}"
        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.FAN_MODE
        )

        # set HVAC capabilities
        self._attr_fan_modes = [FAN_AUTO, FAN_HIGH, FAN_MEDIUM, FAN_LOW]
        self._attr_target_temperature_step = 1
        self._attr_max_temp = device.max_temperature
        self._attr_min_temp = device.min_temperature
        self._attr_temperature_unit = HVAC_UNIT_SB_TO_HASS[device.unit]
        self._attr_hvac_modes = [HVAC_MODE_SB_TO_HASS[mode] for mode in device.modes]
        self._attr_hvac_modes.append(HVACMode.OFF)
        self._device = device
        self._attr_device_info = DeviceInfo(
            name=f"SwitchBee_{str(self._device.id)}",
            identifiers={
                (
                    DOMAIN,
                    f"{str(self._device.id)}-{coordinator.mac_formated}",
                )
            },
            manufacturer=SWITCHBEE_BRAND,
            model=coordinator.api.module_display(device.unit_id),
            suggested_area=device.zone,
            via_device=(
                DOMAIN,
                f"{coordinator.api.name} ({coordinator.api.mac})",
            ),
        )
        # update device state
        self._update_device_attrs(device)

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        self._handle_coordinator_update()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._update_device_attrs(self.coordinator.data[self._device_id])
        super()._handle_coordinator_update()

    def _update_device_attrs(self, device: SwitchBeeThermostat):
        if device.state == ApiStateCommand.OFF:
            self._attr_hvac_mode = HVACMode.OFF
        else:
            self._attr_hvac_mode = HVAC_MODE_SB_TO_HASS[device.mode]
        self._attr_fan_mode = FAN_SB_TO_HASS[device.fan]
        self._attr_current_temperature = device.temperature
        self._attr_target_temperature = device.target_temperature

    def _create_switchbee_request(
        self,
        power: str = None,
        mode: str = None,
        fan: str = None,
        target_temperature: int = 0,
    ) -> dict[str, str | int]:
        """Create SwitchBee thermostat state object."""

        new_power = power
        if not new_power:
            if self._attr_hvac_mode == HVACMode.OFF:
                new_power = ApiStateCommand.OFF
            else:
                new_power = ApiStateCommand.ON

        data = {
            ApiAttribute.POWER: new_power,
            ApiAttribute.MODE: mode if mode else ThermostatMode.COOL,
            ApiAttribute.FAN: fan if fan else FAN_HASS_TO_SB[self._attr_fan_mode],
            ApiAttribute.CONFIGURED_TEMPERATURE: target_temperature
            if target_temperature
            else self._attr_target_temperature,
        }

        return data

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set hvac mode."""

        if hvac_mode == HVACMode.OFF:
            state = self._create_switchbee_request(power=ApiStateCommand.OFF)
        else:
            state = self._create_switchbee_request(
                power=ApiStateCommand.ON, mode=HVAC_MODE_HASS_TO_SB[hvac_mode]
            )

        await self.operate(state)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        await self.operate(
            self._create_switchbee_request(target_temperature=kwargs[ATTR_TEMPERATURE])
        )

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set AC fand mode."""
        await self.operate(self._create_switchbee_request(fan=FAN_HASS_TO_SB[fan_mode]))

    async def operate(self, state: dict[str, str | int]):
        """send request to central unit."""
        try:
            await self.coordinator.api.set_state(self._device_id, state)
        except (SwitchBeeError, SwitchBeeDeviceOfflineError) as exp:
            _LOGGER.error(
                "Failed to set %s state %s, error: %s", self._attr_name, state, exp
            )
            self._async_write_ha_state()
        else:
            await self.coordinator.async_refresh()
