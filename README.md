# SwitchBee Integration With Home Assistant

![PyPI](https://img.shields.io/pypi/v/pyswitchbee?label=pypi%20package)
![Build Status](https://img.shields.io/pypi/dm/pyswitchbee)


Custom integrations to control the following SwitchBee devices via Home Assistans:

- Lights (Dimmers and Switches)
- Switches (Timer Switch)
- Shutters 

Supported devices will be discovered after the `SwitchBee` integration is configured


The integration can be configured from via the frontend, the user must provide the

 ## Prerequisites

 In order to set up this integration, you need to get the following parameters:

 - Central Unit IP
 - Username
 - Password (`Getting the SwitchBee API password` below)

 ### Note

  The Central Unit version must be on 1.4.3(0) for the APIs to be exposed, you can contact [SwitchBee](https://www.switchbee.com) to get this version.

 ## Getting the SwitchBee API password

  You are also required required to set API user password in the SwitchBee app from your smartphone (iPhone users must install SwitchBee Next Gen app).

   1. Open the SwitchBee app on your smartphone
   2. Open the Menu from top left corner
   3. Click on Users and choose the API user
   4. Under the `User Info` tab, click `Edit` and set the desired password

## Optional Configuration 

- Scan Interval 
- Expose SwitchBee Scenarios as buttons in HASS
- Expose SwitchBee Group Scenarios as Switches


 [In case you want to buy me a coffe :)](https://paypal.me/jafaratili?country.x=IL&locale.x=he_IL)
