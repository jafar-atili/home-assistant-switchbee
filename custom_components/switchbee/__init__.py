"""The SwitchBee Smart Home integration."""

from __future__ import annotations

from datetime import timedelta
import logging

from switchbee.api import CentralUnitAPI, SwitchBeeError
from switchbee.device import DeviceType

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.device_registry import format_mac

from .const import (
    CONF_EXPOSE_GROUP_SWITCHES,
    CONF_EXPOSE_SCENARIOS,
    DOMAIN,
    SCAN_INTERVAL_SEC,
)

_LOGGER = logging.getLogger(__name__)


PLATFORMS: list[Platform] = [
    Platform.SWITCH,
    Platform.COVER,
    Platform.LIGHT,
    Platform.BUTTON,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SwitchBee Smart Home from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    central_unit = entry.data[CONF_HOST]
    user = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]

    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, SCAN_INTERVAL_SEC)
    expose_group_switches = entry.options.get(CONF_EXPOSE_GROUP_SWITCHES)
    expose_scenarios = entry.options.get(CONF_EXPOSE_SCENARIOS)

    websession = async_get_clientsession(hass, verify_ssl=False)
    api = CentralUnitAPI(central_unit, user, password, websession)
    try:
        await api.connect()
    except SwitchBeeError:
        return False

    coordinator = SwitchBeeCoordinator(
        hass, api, scan_interval, expose_group_switches, expose_scenarios
    )
    await coordinator.async_config_entry_first_refresh()
    entry.async_on_unload(entry.add_update_listener(update_listener))
    hass.data[DOMAIN][entry.entry_id] = coordinator

    hass.config_entries.async_setup_platforms(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def update_listener(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Update listener."""
    await hass.config_entries.async_reload(config_entry.entry_id)


class SwitchBeeCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Freedompro data API."""

    def __init__(
        self, hass, swb_api, scan_interval, expose_group_switches, expose_scenarios
    ):
        """Initialize."""
        self._api: CentralUnitAPI = swb_api
        self._reconnect_counts: int = 0
        self._expose_group_switches: bool = expose_group_switches
        self._prev_expose_group_switches: bool = False
        self._expose_scenarios: bool = expose_scenarios
        self._prev_expose_scenarios: bool = False
        self._mac_addr_fmt = format_mac(swb_api.mac)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )

    @property
    def api(self) -> CentralUnitAPI:
        """Return SwitchBee API object."""
        return self._api

    @property
    def mac_formated(self) -> str:
        """Return SwitchBee API object."""
        return self._mac_addr_fmt

    async def _async_update_data(self):

        if self._reconnect_counts != self._api.reconnect_count:
            self._reconnect_counts = self._api.reconnect_count
            _LOGGER.debug(
                "Central Unit re-connected again due to invalid token, total %i",
                self._reconnect_counts,
            )

        include_devices = [
            DeviceType.Switch,
            DeviceType.Dimmer,
            DeviceType.TimedPowerSwitch,
            DeviceType.Shutter,
        ]

        config_changed = False

        if self._expose_group_switches != self._prev_expose_group_switches:
            self._prev_expose_group_switches = self._expose_group_switches
            config_changed = True

        if self._expose_scenarios != self._prev_expose_scenarios:
            self._prev_expose_scenarios = self._expose_scenarios
            config_changed = True

        if self._expose_group_switches:
            include_devices.append(DeviceType.GroupSwitch)

        if self._expose_scenarios:
            include_devices.append(DeviceType.Scenario)

        # The devices are loaded once during the config_entry
        if not self._api.devices or config_changed:
            # Try to load the devices from the CU for the first time
            try:
                await self._api.fetch_configuration(include_devices)
            except SwitchBeeError as exp:
                raise UpdateFailed(
                    f"Error communicating with API: {exp}"
                ) from SwitchBeeError
            else:
                _LOGGER.debug("Loaded devices")

        # Get the state of the devices
        try:
            await self._api.fetch_states()
        except SwitchBeeError as exp:
            raise UpdateFailed(
                f"Error communicating with API: {exp}"
            ) from SwitchBeeError
        else:
            return self._api.devices
