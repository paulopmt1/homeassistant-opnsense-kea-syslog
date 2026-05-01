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

Expected format is **one message per line** (newline `\n`).

## Emitted event: `device_joined_network`
When detected, the integration fires an event with:

- `event_type`: `DHCP4_LEASE_ALLOC` or `DHCP4_LEASE_RENEW`
- `mac`: `AA:BB:CC:DD:EE:FF`
- `ip`: `192.168.1.101` (if present in the line)
- `remote_ip`: Remote IP that connected (e.g., OPNsense)
- `raw`: Full received line
- `ts`: UTC ISO timestamp of the moment received by HA

## Live logs (everything received)
If you enable `log_all_lines` in the integration options, Home Assistant will log every received line in real time:

- Example log line: `Syslog line from 192.168.1.1: <full_line>`

Where to see it:
- **Settings → System → Logs**
- Or CLI: `ha core logs -f`

## Example automation (YAML)

```yaml
automation:
  - alias: "Phone joined the network"
    mode: single
    trigger:
      - platform: event
        event_type: device_joined_network
    condition:
      - condition: template
        value_template: >
          {{ trigger.event.data.mac in ['AA:BB:CC:DD:EE:FF'] }}
    action:
      - service: notify.notify
        data:
          message: >
            MAC {{ trigger.event.data.mac }} joined the network (IP {{ trigger.event.data.ip }}),
            via {{ trigger.event.data.event_type }}.
```

## Quick test (manual)
From an allowed host (e.g., OPNsense itself or any machine in the allowlist), connect and send a line:

```bash
nc <home_assistant_ip> <configured_port>
```

Paste a line like:
`INFO [kea-dhcp4.leases.0x...] DHCP4_LEASE_ALLOC [hwtype=1 AA:BB:CC:DD:EE:FF], cid=[01:AA:BB:CC:DD:EE:FF], tid=0x...: lease 192.168.1.101 has been allocated for 4000 seconds`

Then check **Developer Tools → Events** and listen to `device_joined_network`.
