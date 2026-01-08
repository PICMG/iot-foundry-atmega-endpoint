#!/usr/bin/env python3
"""Toggle DTR on a serial device using ioctl (no pyserial dependency).

Usage: toggle_dtr.py /dev/ttyACM0 [pulse_ms]
"""
import sys
import os
import time
import struct
import fcntl
import termios

def ioctl_get(fd, req):
    buf = struct.pack('I', 0)
    out = fcntl.ioctl(fd, req, buf)
    return struct.unpack('I', out)[0]

def ioctl_set(fd, req, val):
    buf = struct.pack('I', val)
    fcntl.ioctl(fd, req, buf)

def pulse_dtr(path, pulse_ms=100):
    fd = os.open(path, os.O_RDWR | os.O_NOCTTY)
    try:
        TIOCMGET = getattr(termios, 'TIOCMGET', 0x5415)
        TIOCMSET = getattr(termios, 'TIOCMSET', 0x5418)
        TIOCM_DTR = getattr(termios, 'TIOCM_DTR', 0x002)

        flags = ioctl_get(fd, TIOCMGET)
        # Clear DTR
        ioctl_set(fd, TIOCMSET, flags & ~TIOCM_DTR)
        time.sleep(pulse_ms / 1000.0)
        # Restore previous DTR state
        ioctl_set(fd, TIOCMSET, flags)
    finally:
        os.close(fd)

def main():
    if len(sys.argv) < 2:
        print('Usage: toggle_dtr.py /dev/ttyX [pulse_ms]', file=sys.stderr)
        return 2
    path = sys.argv[1]
    try:
        pulse = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    except Exception:
        pulse = 100
    try:
        pulse_dtr(path, pulse)
    except Exception as e:
        print('toggle_dtr failed:', e, file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    sys.exit(main())
