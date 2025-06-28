# Tesla BLE Bridge (ESPHome ⇄ HTTP / MQTT)

This micro-service connects an **ESP32** running the firmware [esphome-tesla-ble](https://github.com/PedroKTFC/esphome-tesla-ble) to your energy-management stack (EVCC, Home Assistant, etc.).

It is **fully compatible with [EVCC](https://evcc.io/)** thanks to the built-in `tesla-ble` provider template.

Ready-to-use Docker images are published on [Docker Hub](https://hub.docker.com/r/bagl3y/esphome-tesla-ble-bridge/tags).

* Persistent connection to the ESPHome native API (TCP 6053) for **multiple vehicles**.
* Caches ESPHome entity states (SoC, connected, charging…) for each vehicle.
* Exposes the data through:
  * **HTTP REST** (FastAPI)
  * **MQTT** (optional)
* Ultra-simple deployment with **Docker Compose** or **Kubernetes**.

> **⚠️  Work in progress:** MQTT publishing and support for controlling **multiple ESP32 devices** from a single bridge instance are still under active development and may change without notice.

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
      "vin": "XP7YGCEK5SB617830", // required – used in API routes and MQTT topics
      "host": "esp-tesla.local",  // ESP32 IP or mDNS name
      "port": 6053,
      "password": "",            // legacy ESPHome auth (usually empty)
      "encryption_key": "AbCd…==" // Noise key (Base64)
    },
    {
      "vin": "5YJ3E1EA7HF000000",
      "host": "esp-other.local",
      "encryption_key": "XyZ…=="
    }
  ]
}
```

👉 To manage multiple vehicles, simply add more objects to the `vehicles` array. The bridge will create a dedicated connection for each one.

---

## Run

| Mode | Command |
|------|---------|
| **Docker Compose** | `docker compose up -d` |
| **Plain Docker** | `docker build -t tesla-ble-bridge . && docker run -p 8000:8000 -v $PWD/config.json:/app/config.json:ro tesla-ble-bridge` |
| **Local (venv)** | `uvicorn src.interface_http.http_app:app --host 0.0.0.0 --port 8000` |

The API will then be reachable at `http://localhost:8000`.

---

## HTTP API

All vehicle-specific endpoints are prefixed with `/api/1/vehicles/{VIN}`.

### Health & Status

| Method | URL | Description |
|--------|-----|-------------|
| `GET` | `/health/live` | Liveness probe (service is running) |
| `GET` | `/health/ready`| Readiness probe (connected to the ESP32) |

### Vehicle Data

| Method | URL | Description |
|--------|-----|-------------|
| `GET` | `/api/1/vehicles/{VIN}/vehicle_data` | `charge_state`, `climate_state` (filter with `?endpoints=`) |
| `GET` | `/api/1/vehicles/{VIN}/state/{key}` | Raw value of a specific ESPHome entity |
| `GET` | `/api/1/vehicles/{VIN}/entities` | List of all discovered entities + metadata |

### Commands

| Fleet command | Verb | URL | JSON body (example) |
|---------------|------|-----|---------------------|
| wake_up | `POST` | `/api/1/vehicles/{VIN}/command/wake_up` | — |
| charge_start / charge_stop | `POST` | `/api/1/vehicles/{VIN}/command/charge_start` | — |
| set_charging_amps | `POST` | `/api/1/vehicles/{VIN}/command/set_charging_amps` | `{ "charging_amps": 5 }` |
| set_charge_limit | `POST` | `/api/1/vehicles/{VIN}/command/set_charge_limit` | `{ "percent": 80 }` |
| auto_conditioning_start / stop | `POST` | `/api/1/vehicles/{VIN}/command/auto_conditioning_start` | — |
| charge_port_door_open / close | `POST` | `/api/1/vehicles/{VIN}/command/charge_port_door_open` | — |
| flash_lights | `POST` | `/api/1/vehicles/{VIN}/command/flash_lights` | — |
| honk_horn | `POST` | `/api/1/vehicles/{VIN}/command/honk_horn` | — |
| unlock_charge_port | `POST` | `/api/1/vehicles/{VIN}/command/unlock_charge_port` | — |
| set_sentry_mode | `POST` | `/api/1/vehicles/{VIN}/command/set_sentry_mode` | `{ "on": true }` |

All responses follow the Fleet format: `{ "response": … }`.

> The bridge also features a **generic handler**: any ESPHome `button`, `switch` or `number` entity can be triggered via `/api/1/vehicles/{VIN}/command/{object_id}`.  
> • `switch` → body `{ "state": true/false }`  
> • `number` → body `{ "value": 42 }`

---

## MQTT

If `mqtt.enable` is `true`, every entity listed in `ENTITY_MAP` is published to:

```text
{base_topic}/{vin}/{simple_name}
```

Example with the default config for a vehicle with VIN `XP7YGCEK5SB617830`:
* `evcc/tesla/XP7YGCEK5SB617830/soc        → 68.5`
* `evcc/tesla/XP7YGCEK5SB617830/connected  → True`

Messages are published with the `retain` flag.

---

## Troubleshooting

* **No connection**: check `host`/`port` and Noise key in `config.json`, ensure port 6053 is open.
* **`not supported argument 'encryption_key'`**: you're running an outdated `aioesphomeapi`; the official image already includes ≥ 32.
* **No MQTT messages**: set `"log_level": "DEBUG"` in `config.json`, inspect the logs and verify broker auth.

---

## License

Distributed under the **MIT** license – see `LICENSE` for details. 