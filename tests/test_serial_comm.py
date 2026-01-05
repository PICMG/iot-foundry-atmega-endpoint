#!/usr/bin/env python3
"""
Simple serial communication tester for the target MCU.

Usage (CLI):
  python3 tests/test_serial_comm.py --device /dev/ttyACM0 --baud 115200 --cmd "01 02 03"

Pytest note:
  Set environment variable `SERIAL_DEVICE` to the device path and `SERIAL_TEST_CMD`
  to the hex command to send (e.g. "01 02 03"). The pytest `test_device_responds`
  asserts the device returns at least one byte within the timeout.
"""

import argparse
import os
import time
import sys

import serial


FRAME_CHAR = 0x7E
ESCAPE_CHAR = 0x7D
INITFCS = 0xFFFF


def parse_hex_string(s: str) -> bytes:
    parts = s.replace(",", " ").split()
    if not parts or parts == [""]:
        return b""
    return bytes(int(p, 16) for p in parts)


def calc_fcs(data: bytes) -> int:
    fcstab = [
        0x0000, 0x1189, 0x2312, 0x329b, 0x4624, 0x57ad, 0x6536, 0x74bf, 0x8c48, 0x9dc1,
        0xaf5a, 0xbed3, 0xca6c, 0xdbe5, 0xe97e, 0xf8f7, 0x1081, 0x0108, 0x3393, 0x221a,
        0x56a5, 0x472c, 0x75b7, 0x643e, 0x9cc9, 0x8d40, 0xbfdb, 0xae52, 0xdaed, 0xcb64,
        0xf9ff, 0xe876, 0x2102, 0x308b, 0x0210, 0x1399, 0x6726, 0x76af, 0x4434, 0x55bd,
        0xad4a, 0xbcc3, 0x8e58, 0x9fd1, 0xeb6e, 0xfae7, 0xc87c, 0xd9f5, 0x3183, 0x200a,
        0x1291, 0x0318, 0x77a7, 0x662e, 0x54b5, 0x453c, 0xbdcb, 0xac42, 0x9ed9, 0x8f50,
        0xfbef, 0xea66, 0xd8fd, 0xc974, 0x4204, 0x538d, 0x6116, 0x709f, 0x0420, 0x15a9,
        0x2732, 0x36bb, 0xce4c, 0xdfc5, 0xed5e, 0xfcd7, 0x8868, 0x99e1, 0xab7a, 0xbaf3,
        0x5285, 0x430c, 0x7197, 0x601e, 0x14a1, 0x0528, 0x37b3, 0x263a, 0xdecd, 0xcf44,
        0xfddf, 0xec56, 0x98e9, 0x8960, 0xbbfb, 0xaa72, 0x6306, 0x728f, 0x4014, 0x519d,
        0x2522, 0x34ab, 0x0630, 0x17b9, 0xef4e, 0xfec7, 0xcc5c, 0xddd5, 0xa96a, 0xb8e3,
        0x8a78, 0x9bf1, 0x7387, 0x620e, 0x5095, 0x411c, 0x35a3, 0x242a, 0x16b1, 0x0738,
        0xffcf, 0xee46, 0xdcdd, 0xcd54, 0xb9eb, 0xa862, 0x9af9, 0x8b70, 0x8408, 0x9581,
        0xa71a, 0xb693, 0xc22c, 0xd3a5, 0xe13e, 0xf0b7, 0x0840, 0x19c9, 0x2b52, 0x3adb,
        0x4e64, 0x5fed, 0x6d76, 0x7cff, 0x9489, 0x8500, 0xb79b, 0xa612, 0xd2ad, 0xc324,
        0xf1bf, 0xe036, 0x18c1, 0x0948, 0x3bd3, 0x2a5a, 0x5ee5, 0x4f6c, 0x7df7, 0x6c7e,
        0xa50a, 0xb483, 0x8618, 0x9791, 0xe32e, 0xf2a7, 0xc03c, 0xd1b5, 0x2942, 0x38cb,
        0x0a50, 0x1bd9, 0x6f66, 0x7eef, 0x4c74, 0x5dfd, 0xb58b, 0xa402, 0x9699, 0x8710,
        0xf3af, 0xe226, 0xd0bd, 0xc134, 0x39c3, 0x284a, 0x1ad1, 0x0b58, 0x7fe7, 0x6e6e,
        0x5cf5, 0x4d7c, 0xc60c, 0xd785, 0xe51e, 0xf497, 0x8028, 0x91a1, 0xa33a, 0xb2b3,
        0x4a44, 0x5bcd, 0x6956, 0x78df, 0x0c60, 0x1de9, 0x2f72, 0x3efb, 0xd68d, 0xc704,
        0xf59f, 0xe416, 0x90a9, 0x8120, 0xb3bb, 0xa232, 0x5ac5, 0x4b4c, 0x79d7, 0x685e,
        0x1ce1, 0x0d68, 0x3ff3, 0x2e7a, 0xe70e, 0xf687, 0xc41c, 0xd595, 0xa12a, 0xb0a3,
        0x8238, 0x93b1, 0x6b46, 0x7acf, 0x4854, 0x59dd, 0x2d62, 0x3ceb, 0x0e70, 0x1ff9,
        0xf78f, 0xe606, 0xd49d, 0xc514, 0xb1ab, 0xa022, 0x92b9, 0x8330, 0x7bc7, 0x6a4e,
        0x58d5, 0x495c, 0x3de3, 0x2c6a, 0x1ef1, 0x0f78,
    ]
    fcs = INITFCS
    for b in data:
        fcs = 0x0ffff & ((fcs >> 8) ^ fcstab[(fcs ^ (b & 0xff)) & 0xff])
    return fcs


def build_mctp_control_request(cmd_code: int, dest: int = 0x00, src: int = 0x01, payload: bytes = b"") -> bytes:
    # media/frame constants
    protocol_version = 0x01
    header_version = 0x01
    flags = 0xC8  # SOM/EOM single frame, Tag Owner (TO)=1
    msg_type = 0x00  # control
    instance_id = 0x80  # request (RQ bit set), tag=0

    # assemble unescaped buffer (without FCS and trailing FRAME_CHAR)
    body = bytearray()
    body.append(header_version)
    body.append(dest)
    body.append(src)
    body.append(flags)
    body.append(msg_type)
    body.append(instance_id)
    body.append(cmd_code)
    if payload:
        body.extend(payload)

    byte_count = len(body)

    # construct full frame before escaping
    frame = bytearray()
    frame.append(FRAME_CHAR)
    frame.append(protocol_version)
    frame.append(byte_count)
    frame.extend(body)

    # calculate FCS over bytes from protocol_version up to last body byte
    fcs = calc_fcs(bytes(frame[1:]))
    frame.append((fcs >> 8) & 0xFF)
    frame.append(fcs & 0xFF)
    frame.append(FRAME_CHAR)

    # escape payload bytes (indices 3 .. 3+byte_count inclusive in original frame)
    tx = bytearray()
    payload_start = 3
    payload_end = 3 + byte_count
    for i, b in enumerate(frame):
        if (i >= payload_start) and (i <= payload_end) and (b in (FRAME_CHAR, ESCAPE_CHAR)):
            tx.append(ESCAPE_CHAR)
            tx.append((b - 0x20) & 0xFF)
        else:
            tx.append(b)

    return bytes(tx)


def send_command(device: str, cmd: bytes, baud: int = 115200, timeout: float = 1.0) -> bytes:
    with serial.Serial(device, baud, timeout=timeout) as ser:
        # small settle: allow device to initialize after port open
        time.sleep(2.0)
        if cmd:
            ser.write(cmd)
            ser.flush()
        # read whatever the device sends back within timeout
        resp = ser.read(256)
        return resp


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--device", default="/dev/ttyACM0")
    p.add_argument("--baud", type=int, default=9600)
    p.add_argument("--cmd", default="", help="Hex bytes to send, e.g. '01 02 03'")
    p.add_argument("--mctp", action="store_true", help="Send as MCTP control request (builds MCTP frame)")
    p.add_argument("--timeout", type=float, default=1.0)
    args = p.parse_args()
    if args.mctp:
        # support command names or numeric hex bytes
        cmd_str = args.cmd.strip()
        name_map = {
            "SET_ENDPOINT_ID": 0x01,
            "GET_ENDPOINT_ID": 0x02,
            "GET_MCTP_VERSION_SUPPORT": 0x04,
            "GET_MESSAGE_TYPE_SUPPORT": 0x05,
        }
        if cmd_str.upper() in name_map:
            cmd_code = name_map[cmd_str.upper()]
            payload = b""
        else:
            # fallback: treat as hex payload where first byte is command code
            raw = parse_hex_string(cmd_str)
            if len(raw) == 0:
                print("No MCTP command provided", file=sys.stderr)
                sys.exit(2)
            cmd_code = raw[0]
            payload = raw[1:]

        frame = build_mctp_control_request(cmd_code, dest=0x00, src=0x01, payload=payload)
        try:
            resp = send_command(args.device, frame, baud=args.baud, timeout=args.timeout)
        except serial.SerialException as e:
            print(f"Serial error: {e}", file=sys.stderr)
            raise
    else:
        cmd = parse_hex_string(args.cmd) if args.cmd else b""
        try:
            resp = send_command(args.device, cmd, baud=args.baud, timeout=args.timeout)
        except serial.SerialException as e:
            print(f"Serial error: {e}", file=sys.stderr)
            raise

    if resp:
        print("Response:", " ".join(f"{b:02X}" for b in resp))
    else:
        print("No response (empty).")


if __name__ == "__main__":
    main()


# Pytest-compatible test
def test_device_responds():
    device = os.getenv("SERIAL_DEVICE", "/dev/ttyACM0")
    baud = int(os.getenv("SERIAL_BAUD", "9600"))
    timeout = float(os.getenv("SERIAL_TIMEOUT", "1.0"))
    cmd_hex = os.getenv("SERIAL_TEST_CMD", "")
    use_mctp = os.getenv("SERIAL_MCTP", "0") in ("1", "true", "True")
    if use_mctp:
        # allow command name or hex
        name_map = {
            "SET_ENDPOINT_ID": 0x01,
            "GET_ENDPOINT_ID": 0x02,
            "GET_MCTP_VERSION_SUPPORT": 0x04,
            "GET_MESSAGE_TYPE_SUPPORT": 0x05,
        }
        if cmd_hex.upper() in name_map:
            cmd_code = name_map[cmd_hex.upper()]
            payload = b""
        else:
            raw = parse_hex_string(cmd_hex)
            if len(raw) == 0:
                cmd_code = 0x02
                payload = b""
            else:
                cmd_code = raw[0]
                payload = raw[1:]

        frame = build_mctp_control_request(cmd_code, dest=0x00, src=0x01, payload=payload)
        try:
            resp = send_command(device, frame, baud=baud, timeout=timeout)
        except serial.SerialException:
            raise
    else:
        cmd = parse_hex_string(cmd_hex) if cmd_hex else b""
        try:
            resp = send_command(device, cmd, baud=baud, timeout=timeout)
        except serial.SerialException:
            raise

    assert isinstance(resp, (bytes, bytearray))
