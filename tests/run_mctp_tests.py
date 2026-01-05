#!/usr/bin/env python3
"""Run a sequence of MCTP control requests and print decoded responses.

Sends: SET_ENDPOINT_ID (EID=8), GET_ENDPOINT_ID, GET_MCTP_VERSION_SUPPORT,
GET_MESSAGE_TYPE_SUPPORT and decodes the replies.
"""
import time
import serial
import sys

FRAME_CHAR = 0x7E
ESCAPE_CHAR = 0x7D
INITFCS = 0xFFFF

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


def calc_fcs(data: bytes) -> int:
    fcs = INITFCS
    for b in data:
        fcs = 0x0ffff & ((fcs >> 8) ^ fcstab[(fcs ^ (b & 0xff)) & 0xff])
    return fcs


def unescape_body(raw: bytes) -> bytes:
    out = bytearray()
    i = 0
    while i < len(raw):
        b = raw[i]
        if b == ESCAPE_CHAR:
            i += 1
            if i >= len(raw):
                break
            out.append((raw[i] + 0x20) & 0xFF)
        else:
            out.append(b)
        i += 1
    return bytes(out)


def parse_frame(data: bytes):
    if not data:
        return None
    try:
        start = data.index(FRAME_CHAR)
        end = data.rindex(FRAME_CHAR)
    except ValueError:
        return None
    payload = data[start + 1:end]
    payload = unescape_body(payload)
    if len(payload) < 6:
        return None
    protocol = payload[0]
    byte_count = payload[1]
    header_version = payload[2]
    dest = payload[3]
    src = payload[4]
    flags = payload[5]
    msg_type = payload[6]
    instance = payload[7]
    # payload layout: [protocol(1), byte_count(1), body(byte_count), fcs_hi(1), fcs_lo(1)]
    # total payload length == 2 + byte_count + 2
    if len(payload) < (2 + byte_count + 2):
        return None
    fcs_calc = calc_fcs(payload[:2 + byte_count])
    msg_fcs = (payload[2 + byte_count] << 8) | payload[2 + byte_count + 1]
    cmd_idx = 8
    cmd_code = None
    extra = b""
    if len(payload) > cmd_idx:
        cmd_code = payload[cmd_idx]
        extra = payload[cmd_idx + 1:2 + byte_count]
    return {
        'protocol': protocol,
        'byte_count': byte_count,
        'header_version': header_version,
        'dest': dest,
        'src': src,
        'flags': flags,
        'msg_type': msg_type,
        'instance': instance,
        'cmd_code': cmd_code,
        'extra': extra,
        'fcs_ok': (fcs_calc == msg_fcs),
        'raw_fcs': msg_fcs,
        'fcs_calc': fcs_calc,
    }


def build_mctp_control_request(cmd_code: int, dest: int = 0x00, src: int = 0x01, payload: bytes = b"") -> bytes:
    protocol_version = 0x01
    header_version = 0x01
    flags = 0xC8
    msg_type = 0x00
    instance_id = 0x80
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
    frame = bytearray()
    frame.append(FRAME_CHAR)
    frame.append(protocol_version)
    frame.append(byte_count)
    frame.extend(body)
    fcs = calc_fcs(bytes(frame[1:]))
    frame.append((fcs >> 8) & 0xFF)
    frame.append(fcs & 0xFF)
    frame.append(FRAME_CHAR)
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


def send_and_capture(device: str, frame: bytes, baud: int = 9600, settle: float = 2.0):
    with serial.Serial(device, baud, timeout=0.01) as ser:
        ser.reset_input_buffer()
        time.sleep(settle)
        ser.write(frame)
        ser.flush()
        data = bytearray()
        last = time.time()
        deadline = time.time() + 2.0
        while time.time() < deadline:
            n = ser.in_waiting
            if n:
                data.extend(ser.read(n))
                last = time.time()
            else:
                if data and (time.time() - last) > 0.2:
                    break
                time.sleep(0.001)
        return bytes(data)


CMD_NAMES = {
    0x01: 'SET_ENDPOINT_ID',
    0x02: 'GET_ENDPOINT_ID',
    0x04: 'GET_MCTP_VERSION_SUPPORT',
    0x05: 'GET_MESSAGE_TYPE_SUPPORT',
}


def pretty_print_response(resp: bytes):
    print('Raw:', ' '.join(f"{b:02X}" for b in resp))
    info = parse_frame(resp)
    if not info:
        print('  Could not parse frame')
        return
    print('  Protocol:', info['protocol'])
    print('  Byte count:', info['byte_count'])
    print('  Src->Dst: {} -> {}'.format(info['src'], info['dest']))
    flags = info['flags']
    print('  Flags: 0x{:02X} (Tag/flags={:02X})'.format(flags, flags & 0xFF))
    print('  Msg type:', info['msg_type'])
    print('  Instance:', hex(info['instance']))
    cmd = info['cmd_code']
    print('  Command code:', cmd, CMD_NAMES.get(cmd, 'UNKNOWN'))
    extra = info['extra']
    if extra:
        print('  Payload/Response bytes:', ' '.join(f"{b:02X}" for b in extra))
    print('  Calculated FCS: 0x{:04X}'.format(info.get('fcs_calc', 0)))
    print('  Expected  FCS: 0x{:04X}'.format(info.get('raw_fcs', 0)))
    print('  FCS ok:', info['fcs_ok'])


def run(device='/dev/ttyACM0', baud=9600):
    tests = [
        ('SET_ENDPOINT_ID', build_mctp_control_request(0x01, payload=bytes([0x00, 0x08]))),
        ('GET_ENDPOINT_ID', build_mctp_control_request(0x02)),
        ('GET_MCTP_VERSION_SUPPORT', build_mctp_control_request(0x04)),
        ('GET_MESSAGE_TYPE_SUPPORT', build_mctp_control_request(0x05)),
    ]

    for name, frame in tests:
        print('\n===> Sending', name)
        resp = send_and_capture(device, frame, baud)
        if resp:
            pretty_print_response(resp)
        else:
            print('  No response')


if __name__ == '__main__':
    dev = '/dev/ttyACM0'
    baud = 9600
    if len(sys.argv) > 1:
        dev = sys.argv[1]
    if len(sys.argv) > 2:
        baud = int(sys.argv[2])
    run(dev, baud)
