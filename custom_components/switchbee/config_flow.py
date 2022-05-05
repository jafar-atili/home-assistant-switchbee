"""Config flow for SwitchBee Smart Home integration."""
from __future__ import annotations

import logging
from typing import Any

from switchbee import ATTR_DATA, ATTR_MAC, ATTR_NAME, SwitchBeeAPI, SwitchBeeError
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_EXPOSE_GROUP_SWITCHES,
    CONF_EXPOSE_SCENARIOS,
    DOMAIN,
    SCAN_INTERVAL_SEC,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]):
    """Validate the user input allows us to connect."""

    websession = async_get_clientsession(hass, verify_ssl=False)
    api = SwitchBeeAPI(
        data[CONF_HOST], data[CONF_USERNAME], data[CONF_PASSWORD], websession
    )
    try:
        await api.login()
    except SwitchBeeError as exp:
        _LOGGER.error(exp)
        if "LOGIN_FAILED" in str(exp):
            raise InvalidAuth from SwitchBeeError

        raise CannotConnect from SwitchBeeError

    try:
        resp = await api.get_configuration()
        return resp[ATTR_DATA][ATTR_MAC], resp[ATTR_DATA][ATTR_NAME]
    except SwitchBeeError as exp:
        _LOGGER.error(exp)
        raise CannotConnect from SwitchBeeError


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SwitchBee Smart Home."""

    VERSION = 1

    def __init__(self) -> None:
        self._name = None

    async def async_step_user(self, user_input=None):
        """Show the setup form to the user."""
        errors = {}

        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
            )

        try:
            mac, self._name = await validate_input(self.hass, user_input)
        except CannotConnect:
            errors["base"] = "cannot_connect"
        except InvalidAuth:
            errors["base"] = "invalid_auth"
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"

        else:
            await self.async_set_unique_id(mac)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(title=self._name, data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle a option flow for AEMET."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Handle options flow."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=self.config_entry.options.get(
                        CONF_SCAN_INTERVAL, SCAN_INTERVAL_SEC
                    ),
                ): cv.positive_int,
                vol.Required(
                    CONF_EXPOSE_SCENARIOS,
                    default=self.config_entry.options.get(CONF_EXPOSE_SCENARIOS, False),
                ): cv.boolean,
                vol.Required(
                    CONF_EXPOSE_GROUP_SWITCHES,
                    default=self.config_entry.options.get(
                        CONF_EXPOSE_GROUP_SWITCHES, False
                    ),
                ): cv.boolean,
            }
        )
        return self.async_show_form(step_id="init", data_schema=data_schema)


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
