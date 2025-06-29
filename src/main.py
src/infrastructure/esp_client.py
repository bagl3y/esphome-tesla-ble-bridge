import asyncio
import logging
from typing import Callable

esp_tasks = []

@app.on_event("startup")
async def startup():
    # Create a connection task for each configured vehicle
    for vehicle in settings.vehicles:
        if not vehicle.vin:
            logging.warning("Skipping vehicle without VIN in config: %s", vehicle.host)
            continue
        logging.info("Starting connection handler for vehicle %s (%s)", vehicle.vin, vehicle.host)
        task = asyncio.create_task(esp_run(vehicle, publish))
        esp_tasks.append(task)

@app.on_event("shutdown")
async def shutdown():
    # Cleanly cancel all running ESPHome connection tasks
    logging.info("Cancelling ESPHome connection tasks...")
    for task in esp_tasks:
        task.cancel()
    
    if esp_tasks:
        await asyncio.gather(*esp_tasks, return_exceptions=True)
        logging.info("All ESPHome tasks cancelled.")

    if mqtt_cli:
        logging.info("Disconnecting MQTT client...")
        mqtt_cli.loop_stop()
        mqtt_cli.disconnect()
        logging.info("MQTT client disconnected.")

async def run(vehicle: Vehicle, publish: Callable[[str, str, str], None]):
    vehicle_state = await state_manager.get_vehicle_state(vehicle.vin)

    # ... (state_cb function)

    while True:
        client = None
        try:
            # ... (client connection logic)
            
            # This block now also handles cancellation
            try:
                # ... (keepalive logic with asyncio.gather)
            except AttributeError:
                # ...
            except asyncio.CancelledError:
                logger.info("Connection handler for %s cancelled.", vehicle.vin)
                if vehicle_state.client:
                    await vehicle_state.client.disconnect()
                break # Exit the while loop to terminate the task

        except asyncio.CancelledError:
            # This outer catch ensures cancellation is handled even during connection attempts
            logger.info("Connection handler for %s cancelled during connection phase.", vehicle.vin)
            break
        except Exception as e:
            # ... (existing exception handling) 