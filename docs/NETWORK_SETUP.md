# Avelon CRM LAN Setup

## Recommended network layout

```text
Staff PC 1  --->
Staff PC 2  --->   Office router/switch  --->  Server PC: 192.168.1.20:8080
Staff PC 3  --->
```

## Server PC requirements

- Windows 10 or Windows 11
- Python 3.11+
- MariaDB or MySQL
- Fixed local IP address recommended
- Windows Firewall allowing inbound TCP 8080

## Staff PC requirements

- Windows 10 or Windows 11
- AvelonCRM_Client.exe
- client_config.ini pointing to the server IP

## Recommended fixed IP

Set the Server PC IP to a fixed address or reserve it from the router DHCP settings.

Example:

```ini
url = http://192.168.1.20:8080
```

## Firewall rule

Open Windows Defender Firewall and allow inbound TCP traffic on port 8080.

## Browser health test

From a staff PC, open:

```text
http://192.168.1.20:8080/health
```

If it returns status ok, the client app should connect.
