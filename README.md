# OPNsense Kea Syslog (Home Assistant / HACS)

Custom integration for Home Assistant that opens a **Syslog TCP listener** (configurable port), parses logs from **Kea DHCP (OPNsense)**, and fires an event when a monitored MAC address appears in `DHCP4_LEASE_ALLOC` or `DHCP4_LEASE_RENEW`.

## What the integration does
- **Listens for Syslog via TCP** at `bind_host:port`
- **Allowlist** for IPs/CIDRs (e.g., your OPNsense's IP)
- Extracts MAC from `cid=[01:AA:BB:CC:DD:EE:FF]` (removes the `01:`)
- Extracts IP from `lease 192.168.1.101`
- If the MAC is in the configured list, fires `device_joined_network`
- **Cooldown per MAC** to avoid event spam (mainly on renew)
- Optional **live logging** of *all* received syslog lines (`log_all_lines`)

## Installation (HACS)
1. Add this repository in HACS (as a Custom Repository) **or** copy the folder:
   - `custom_components/opnsense_kea_syslog/` to your `config/custom_components/`
2. Restart Home Assistant
3. Go to **Settings → Devices & services → Add integration** and search for **OPNsense Kea Syslog**

## OPNsense Configuration
Set up syslog TCP forwarding to the Home Assistant IP at the port you define in the integration.

Go to System > Settings > Logging > Remote and create something like this:


<img width="1710" height="937" alt="image" src="https://github.com/user-attachments/assets/9db5e5d4-abe5-4db7-b605-28c660adb3b8" />


Note: Make sure the Hostname and Port matches your Home assistant configs.

## Example configuration (Integration Options)

This is an example of how to configure the integration in **Settings → Devices & services → OPNsense Kea Syslog → Configure**. Visually, it will look like this:

<img width="746" height="1193" alt="image" src="https://github.com/user-attachments/assets/aec16196-5abb-4f38-9611-c413f015b3c5" />


## Example automation (YAML)

```yaml
alias: Device joined network (robust MAC check)
mode: single
description: ligar luz ao conectar no DHCP

trigger:
  - platform: event
    event_type: device_joined_network

condition:
  - condition: template
    value_template: >
      {{ trigger.event.data.mac | lower == "AA:BB:CC:DD:EE:FF" }}

action:
  - service: notify.notify
    data:
      message: >
        Device connected with IP {{ trigger.event.data.ip }}
  - service: light.toggle
    metadata: {}
    target:
      entity_id: light.sala_amarela
    data:
      brightness_pct: 100
```

## Quick test (manual)
From an allowed host (e.g., OPNsense itself or any machine in the allowlist), and using a configured MAC address, connect and send a line:

```bash
nc <home_assistant_ip> <configured_port>
```

Paste a line like:
`INFO [kea-dhcp4.leases.0x...] DHCP4_LEASE_ALLOC [hwtype=1 AA:BB:CC:DD:EE:FF], cid=[01:AA:BB:CC:DD:EE:FF], tid=0x...: lease 192.168.1.101 has been allocated for 4000 seconds`

Then check **Developer Tools → Events** and listen to `device_joined_network`. You should see something like this:

<img width="827" height="1060" alt="image" src="https://github.com/user-attachments/assets/e418a15c-6a2f-4c3a-a528-5573c64da114" />

## Debug mode / Live logs (everything received)
If you enable `log_all_lines` in the integration options, Home Assistant will log every received line in real time.
Also, enable the debug mode in your `/homeassistant/configuration.yaml` to see everything:

```
logger:
  default: info
  logs:
    custom_components.opnsense_kea_syslog: debug
```

That will show the whole detection process, and you can easily check whether the configs are correct or not by checking the HA logs with `ha core logs -f`:

<img width="993" height="290" alt="image" src="https://github.com/user-attachments/assets/0183db13-db02-408e-83a2-9e48f5ad0d36" />
