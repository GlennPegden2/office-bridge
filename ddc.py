#!/usr/bin/env python3

"""
DDC/CI monitor input switching via ddcutil.

Sets VCP feature 0x60 (Input Source) on the default monitor using:
    ddcutil setvcp 60 <hex value>

Usage:
    python ddc.py 0x11
    python ddc.py 0f
"""

import argparse
import logging
import re
import subprocess
import sys
import threading

VCP_INPUT_SOURCE = "60"
DDCUTIL_TIMEOUT = 15

log = logging.getLogger("ddc")

# Serialise access: concurrent ddcutil calls on the same I2C bus can fail.
_lock = threading.Lock()


class DDCError(RuntimeError):
    """Raised when ddcutil is missing or fails to set the input."""


def parse_input_value(value):
    """Return the input value as an int in the range 0x00-0xFF.

    Accepts strings such as "0x11", "11" or "0F", or an int.
    """
    if isinstance(value, int):
        number = value
    else:
        match = re.fullmatch(r"(?:0x)?([0-9a-fA-F]{1,2})", str(value).strip())
        if not match:
            raise ValueError(f"Invalid hex input value: {value!r}")
        number = int(match.group(1), 16)

    if not 0x00 <= number <= 0xFF:
        raise ValueError(f"Input value out of range 0x00-0xFF: {value!r}")

    return number


def set_input(value):
    """Set the default monitor's input source to the given hex value."""
    number = parse_input_value(value)
    command = ["ddcutil", "setvcp", VCP_INPUT_SOURCE, f"0x{number:02x}"]

    with _lock:
        log.info("Setting monitor input to 0x%02X", number)

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=DDCUTIL_TIMEOUT,
            )
        except FileNotFoundError as exc:
            raise DDCError("ddcutil is not installed or not on PATH") from exc
        except subprocess.TimeoutExpired as exc:
            raise DDCError("ddcutil timed out") from exc

    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise DDCError(f"ddcutil failed (exit {result.returncode}): {detail}")

    return {
        "device": "ddc",
        "vcp_feature": "0x" + VCP_INPUT_SOURCE.upper(),
        "input_value": f"0x{number:02X}",
        "command": " ".join(command),
        "status": "set",
    }


def main():
    parser = argparse.ArgumentParser(
        description="Set the default monitor input via ddcutil (VCP 0x60)"
    )

    parser.add_argument(
        "value",
        help="Input source value in hex, e.g. 0x11 or 0f",
    )

    args = parser.parse_args()

    try:
        result = set_input(args.value)
    except (ValueError, DDCError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Set input to {result['input_value']}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
