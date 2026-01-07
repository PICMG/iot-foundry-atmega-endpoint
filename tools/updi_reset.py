#!/usr/bin/env python3
import sys
import time

try:
    import serial
except Exception:
    # If pyserial isn't available, fail silently (Makefile will continue)
    sys.exit(0)

def main():
    port = sys.argv[1] if len(sys.argv) > 1 else '/dev/ttyACM0'
    try:
        baud = int(sys.argv[2]) if len(sys.argv) > 2 else 1200
    except Exception:
        baud = 1200

    try:
        s = serial.Serial(port, baud, timeout=1)
        s.setDTR(False)
        time.sleep(0.05)
        s.setDTR(True)
        s.close()
        # short settle
        time.sleep(0.2)
    except Exception as e:
        print('updi reset failed:', e, file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
