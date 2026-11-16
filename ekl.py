#!/usr/bin/env python3

import argparse
import serial
import sys

COMMANDS = {
    1: bytes.fromhex("AA 00 56"),
    2: bytes.fromhex("AA 01 55"),
    3: bytes.fromhex("AA 02 54"),
    4: bytes.fromhex("AA 03 53"),
}


def main():
    parser = argparse.ArgumentParser(
        description="Control the EKL/HUASION SV04 USB switch via RS232"
    )

    parser.add_argument(
        "channel",
        type=int,
        choices=range(1, 5),
        help="Input channel to select (1-4)"
    )

    parser.add_argument(
        "-dev",
        default="/dev/ttyUSB0",
        help="Serial device (default: /dev/ttyUSB0)"
    )

    args = parser.parse_args()

    command = COMMANDS[args.channel]

    try:
        with serial.Serial(
            port=args.dev,
            baudrate=115200,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=1
        ) as ser:
            ser.write(command)
            ser.flush()

        print(
            f"Selected channel {args.channel} "
            f"(sent: {command.hex(' ').upper()})"
        )

    except serial.SerialException as e:
        print(f"Serial error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
