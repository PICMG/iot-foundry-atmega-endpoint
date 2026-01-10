#!/usr/bin/env python3
import sys, time
try:
    import serial
except Exception:
    print('pyserial not installed')
    sys.exit(2)
if len(sys.argv) < 2:
    print('usage: send_probe.py <pty>')
    sys.exit(2)
pty = sys.argv[1]
print('Using PTY', pty)
FRAME = bytes([0x7E,1,3,1,0,1,0xC8,0,0,0x00,0x00,0x7E])
with serial.Serial(pty, 9600, timeout=0.2) as s:
    s.reset_input_buffer()
    time.sleep(0.05)
    s.write(FRAME)
    s.flush()
    t0 = time.time()
    data = bytearray()
    while time.time() - t0 < 1.0:
        n = s.in_waiting
        if n:
            data.extend(s.read(n))
            if len(data) > 0:
                break
        time.sleep(0.01)
    print('Received', len(data), 'bytes')
    if data:
        print(data.hex())
