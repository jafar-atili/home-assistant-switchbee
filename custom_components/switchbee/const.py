"""Constants for the SwitchBee Smart Home integration."""

from switchbee.api import CentralUnitWsRPC, CentralUnitPolling

DOMAIN = "switchbee"
SCAN_INTERVAL_SEC = {CentralUnitWsRPC: 10, CentralUnitPolling: 5}
