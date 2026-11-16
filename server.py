
#!/usr/bin/env python3

"""
Glenns Home Office Automation API Server
--------------------------
Controls the SV04 four-channel USB switch via its RS232 interface, and monitor via DDC.

HTTP endpoints:
    GET  /api/v1/health
    POST /api/v1/sv04/select
    GET  /api/v1/sv04/channel/{channel}
    POST /api/v1/ddc/input
    GET  /api/v1/ddc/input/{value}

Example:
    POST http://office-bridge:8000/api/v1/sv04/select
    Body: {"channel": 2}

    POST http://office-bridge:8000/api/v1/ddc/input
    Body: {"value": "0x11"}

Serial configuration:
    115200 baud, 8 data bits, no parity, 1 stop bit.
"""

import argparse
import logging
import os
import threading
from datetime import datetime, timezone

import serial
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

import ddc


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

DEFAULT_DEVICE = "/dev/ttyUSB0"
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8000

BAUDRATE = 115200

# SV04 channel commands
COMMANDS = {
    1: bytes.fromhex("AA 00 56"),
    2: bytes.fromhex("AA 01 55"),
    3: bytes.fromhex("AA 02 54"),
    4: bytes.fromhex("AA 03 53"),
}


# ---------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

log = logging.getLogger("sv04-api")


# ---------------------------------------------------------------------
# Serial controller
# ---------------------------------------------------------------------

class SV04Controller:

    def __init__(self, device):
        self.device = device
        self.lock = threading.Lock()
        self.last_command = None
        self.last_channel = None
        self.last_command_time = None

    def select_channel(self, channel):

        if channel not in COMMANDS:
            raise ValueError("Channel must be between 1 and 4")

        command = COMMANDS[channel]

        # Ensure that only one request accesses the serial device
        # at a time.
        with self.lock:

            log.info(
                "Selecting channel %s via %s",
                channel,
                self.device,
            )

            try:
                # Open the serial port for this command.
                # exclusive=True prevents another process opening
                # the same serial port on Linux.
                with serial.Serial(
                    port=self.device,
                    baudrate=BAUDRATE,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=1,
                    write_timeout=2,
                    exclusive=True,
                ) as ser:

                    written = ser.write(command)
                    ser.flush()

                    if written != len(command):
                        raise serial.SerialException(
                            f"Incomplete write: {written}/{len(command)} bytes"
                        )

                self.last_channel = channel
                self.last_command = command.hex(" ").upper()
                self.last_command_time = datetime.now(
                    timezone.utc
                ).isoformat()

                log.info(
                    "Command transmitted: channel %s [%s]",
                    channel,
                    self.last_command,
                )

                return {
                    "device": "sv04",
                    "requested_channel": channel,
                    "command": self.last_command,
                    "status": "transmitted",
                    "timestamp": self.last_command_time,
                    "note": "Transmission confirmed; switch state not independently verified.",
                }

            except (serial.SerialException, OSError) as exc:
                log.error("Serial communication failed: %s", exc)
                raise


# ---------------------------------------------------------------------
# API setup
# ---------------------------------------------------------------------

device = os.environ.get("SV04_DEVICE", DEFAULT_DEVICE)
controller = SV04Controller(device)

app = FastAPI(
    title="Office Automation API",
    description="HTTP control interface for the HUASION / EKL SV04 USB switch.",
    version="1.0.0",
)


# ---------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------

class ChannelRequest(BaseModel):
    channel: int = Field(
        ge=1,
        le=4,
        description="SV04 input channel (1-4)",
    )


class DDCInputRequest(BaseModel):
    value: str = Field(
        description="Monitor input source as hex, e.g. 0x11 or 0f (00-FF)",
    )


# ---------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------

@app.get("/")
def root():
    return {
        "service": "Office Automation API",
        "device": "HUASION / EKL SV04",
        "version": "1.0.0",
        "documentation": "/docs",
    }


@app.get("/api/v1/health")
def health():

    return {
        "status": "running",
        "device": "sv04",
        "serial_device": controller.device,
        "serial_device_exists": os.path.exists(controller.device),
        "baudrate": BAUDRATE,
        "last_channel_requested": controller.last_channel,
        "last_command": controller.last_command,
        "last_command_time": controller.last_command_time,
    }


@app.post("/api/v1/sv04/select")
def select_channel(request: ChannelRequest):

    return send_channel_command(request.channel)


@app.get("/api/v1/sv04/channel/{channel}")
def select_channel_path(channel: int):

    if channel not in COMMANDS:
        raise HTTPException(
            status_code=400,
            detail="Channel must be between 1 and 4",
        )

    return send_channel_command(channel)


@app.post("/api/v1/ddc/input")
def set_ddc_input(request: DDCInputRequest):

    return send_ddc_input(request.value)


@app.get("/api/v1/ddc/input/{value}")
def set_ddc_input_path(value: str):

    return send_ddc_input(value)


# ---------------------------------------------------------------------
# Shared command handlers
# ---------------------------------------------------------------------

def send_channel_command(channel):

    try:
        return controller.select_channel(channel)

    except (serial.SerialException, OSError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Unable to communicate with SV04: {exc}",
        )


def send_ddc_input(value):

    try:
        return ddc.set_input(value)

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    except ddc.DDCError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Unable to set monitor input: {exc}",
        )


# ---------------------------------------------------------------------
# Run directly
# ---------------------------------------------------------------------

if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="HUASION / EKL SV04 HTTP API server"
    )

    parser.add_argument(
        "--device",
        default=device,
        help=f"Serial device (default: {device})",
    )

    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"Interface to listen on (default: {DEFAULT_HOST})",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"HTTP port (default: {DEFAULT_PORT})",
    )

    args = parser.parse_args()

    controller.device = args.device

    log.info("Starting SV04 API server")
    log.info("Serial device: %s", args.device)
    log.info("Listening on: %s:%s", args.host, args.port)

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="info",
    )
