#!/usr/bin/env python3
import sys
import time
try:
    import serial
except Exception:
    serial = None

def main():
    if len(sys.argv) < 2:
        print('usage: touch_reset.py PORT [touch_seconds] [post_seconds]')
        return 2
    port = sys.argv[1]
    touch = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
    post = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
    print(f'Touch reset on {port}: touch={touch}s post={post}s')
    if serial is None:
        print('pyserial not available; falling back to stty touch')
        try:
            import subprocess
            subprocess.run(['stty','-F',port,str(int(1200))], check=False)
            time.sleep(touch)
        except Exception:
            return 1
        time.sleep(post)
        return 0

    try:
        s = serial.Serial(port, 1200)
        time.sleep(touch)
        s.close()
        time.sleep(post)
    except Exception:
        return 1
    return 0

if __name__ == '__main__':
    sys.exit(main())
