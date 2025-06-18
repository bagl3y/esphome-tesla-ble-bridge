# Tesla BLE Bridge (ESPHome ⇄ HTTP / MQTT)

This micro-service connects an **ESP32** running the firmware [esphome-tesla-ble](https://github.com/PedroKTFC/esphome-tesla-ble) to your energy-management stack (EVCC, Home Assistant, etc.).

* Persistent connection to the ESPHome native API (TCP 6053)
* Caches ESPHome entity states (SoC, connected, charging…)
* Exposes the data through:
  * **HTTP REST** (FastAPI)
  * **MQTT** (optional)
* Ultra-simple deployment with **Docker Compose**

---

## Table of contents

1. [Architecture](#architecture)
2. [Prerequisites](#prerequisites)
3. [Installation](#installation)
4. [Configuration](#configuration)
5. [Run](#run)
6. [HTTP API](#http-api)
7. [MQTT](#mqtt)
8. [Troubleshooting](#troubleshooting)
9. [License](#license)

---

## Architecture

```text
┌────────────┐       
│   ESP32    │
│  tesla-ble │
└─────┬──────┘
      │               REST / MQTT
┌─────▼──────────────────────────────────────────────┐
│               Tesla-BLE Bridge (app.py)            │
├────────────────────────────────────────────────────┤
│ • Auto-reconnect to ESP                            │
│ • State cache + HTTP/MQTT exposure                 │
└─────┬───────────────┬──────────────────────────────┘
      │               │
      │ REST JSON     │ MQTT (optional)
┌─────▼───────┐     ┌─▼──────────────────┐
│ EVCC / CURL │     │    MQTT broker     │
└─────────────┘     └────────────────────┘
```

---

## Prerequisites

1. **ESP32** already flashed with the _esphome-tesla-ble_ firmware (native API enabled, Noise key recommended).
2. Docker ≥ 20 or a local Python 3.12 environment.

---

## Installation

### A) Docker / Compose (recommended)

```bash
# clone the repo
$ git clone https://github.com/bagl3y/esphome-tesla-ble-bridge.git
$ cd esphome-tesla-ble-bridge

# create the config file
$ cp config.sample.json config.json
$ nano config.json  # set ESP host, MQTT, VIN…

# start
$ docker compose up -d
```

### B) Local (virtualenv)

```bash
$ python3 -m venv .venv && source .venv/bin/activate
$ pip install --upgrade pip
$ pip install -r requirements.txt

# optional: set CONFIG_FILE if config.json is elsewhere
$ export CONFIG_FILE=/path/to/config.json
$ uvicorn app:app --reload
```

---

## Configuration

All settings live in a single **`config.json`** file (default at the repo root, or specify a custom path via the `CONFIG_FILE` environment variable). No other env vars are required.

```jsonc
{
  "log_level": "INFO",              // DEBUG, INFO, WARNING…
  "mqtt": {
    "enable": true,                // enable MQTT publishing?
    "host": "mqtt",
    "port": 1883,
    "username": "",
    "password": "",
    "base_topic": "evcc/tesla"     // topic prefix
  },
  "vehicles": [
    {
      "vin": "5YJ3E1EA7HF000000", // optional – validates Fleet routes
      "host": "esp-tesla.local",  // ESP32 IP or mDNS name
      "port": 6053,
      "password": "",            // legacy ESPHome auth (usually empty)
      "encryption_key": "AbCd…==" // Noise key (Base64)
    }
  ]
}
```

👉 For multiple vehicles, add more objects to the `vehicles` array (one bridge instance per vehicle is still the safest approach for now).

---

## Run

| Mode | Command |
|------|---------|
| **Docker Compose** | `docker compose up -d` |
| **Plain Docker** | `docker build -t tesla-ble-bridge . && docker run -p 8000:8000 -v $PWD/config.json:/app/config.json:ro tesla-ble-bridge` |
| **Local (venv)** | `uvicorn app:app --host 0.0.0.0 --port 8000` |

The API will then be reachable at `http://localhost:8000`.

---

## HTTP API

### Legacy endpoints

| Method | URL | Description |
|--------|-----|-------------|
| `GET` | `/state/{key}` | Raw value of an ESPHome entity (`battery_level`, `charging`, …) |
| `GET` | `/entities` | List of discovered entities + metadata |

### Tesla Fleet-style API

#### Data & status

| Method | URL | Description |
|--------|-----|-------------|
| `GET` | `/api/1/vehicles/{VIN}/vehicle_data` | `charge_state`, `climate_state` (filter with `?endpoints=`) |
| `GET` | `/api/1/vehicles/{VIN}/body_controller_state` | Lock / sleep / presence information |
| `GET` | `/api/proxy/1/version` | Bridge version |

#### Commands

| Fleet command | Verb | URL | JSON body (example) |
|---------------|------|-----|---------------------|
| wake_up | `POST` | `/command/wake_up` | — |
| charge_start / charge_stop | `POST` | `/command/charge_start` | — |
| set_charging_amps | `POST` | `/command/set_charging_amps` | `{ "charging_amps": 5 }` |
| set_charge_limit | `POST` | `/command/set_charge_limit` | `{ "percent": 80 }` |
| auto_conditioning_start / stop | `POST` | `/command/auto_conditioning_start` | — |
| charge_port_door_open / close | `POST` | `/command/charge_port_door_open` | — |
| flash_lights | `POST` | `/command/flash_lights` | — |
| honk_horn | `POST` | `/command/honk_horn` | — |
| unlock_charge_port | `POST` | `/command/unlock_charge_port` | — |
| set_sentry_mode | `POST` | `/command/set_sentry_mode` | `{ "on": true }` |

All responses follow the Fleet format: `{ "response": … }`.

> The bridge also features a **generic handler**: any ESPHome `button`, `switch` or `number` entity can be triggered via `/api/1/vehicles/{VIN}/command/{object_id}`.  
> • `switch` → body `{ "state": true/false }`  
> • `number` → body `{ "value": 42 }`

---

## MQTT

If `mqtt.enable` is `true`, every entity listed in `ENTITY_MAP` is published to:

```text
{base_topic}/{simple_name}
```

Example with the default config:
* `evcc/tesla/soc        → 68.5`
* `evcc/tesla/connected  → True`

Messages are published with the `retain` flag.

---

## Troubleshooting

* **No connection**: check `host`/`port` and Noise key in `config.json`, ensure port 6053 is open.
* **`not supported argument 'encryption_key'`**: you're running an outdated `aioesphomeapi`; the official image already includes ≥ 32.
* **No MQTT messages**: set `"log_level": "DEBUG"` in `config.json`, inspect the logs and verify broker auth.

---

## License

Distributed under the **MIT** license – see `LICENSE` for details. 