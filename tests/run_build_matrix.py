#!/usr/bin/env python3
"""Run a build matrix over configurations.json combinations.

Usage: tools/run_build_matrix.py --list
       tools/run_build_matrix.py --run --baud 115200 --fcpu 16000000

Defaults to listing combinations. Use --run to invoke `make platform_build`
for each combo. Produces a CSV report when --report is given.
"""
import os
import sys
import json
import argparse
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'configurations.json'


def load_config():
    with open(CONFIG) as f:
        return json.load(f)


def enumerate_combinations(cfg):
    combos = []
    # Accept either new object shape or legacy array-of-groups
    entries = []
    if isinstance(cfg, dict):
        entries = cfg.get('classic_uarts', []) + cfg.get('zero_series_uarts', [])
    else:
        for group in cfg:
            entries += group.get('serial_ports', [])

    for entry in entries:
        name = entry.get('name')
        parts = entry.get('included_parts') or []
        ports = entry.get('ports') or []
        for p in parts:
            if ports:
                for idx in range(len(ports)):
                    combos.append({'mcu': p, 'uart': name, 'pin_idx': idx, 'entry': entry})
            else:
                combos.append({'mcu': p, 'uart': name, 'pin_idx': None, 'entry': entry})
    return combos


def run_build(combo, baud, fcpu, make_target='platform_build', timeout=300):
    env = os.environ.copy()
    env.update({'MCU': combo['mcu'], 'SERIAL_BAUD': str(baud), 'F_CPU': str(fcpu), 'SERIAL_UART': combo['uart']})
    if combo['pin_idx'] is not None:
        env['SERIAL_PIN_OPTION'] = str(combo['pin_idx'])
    # Run make for the single target (no clean by default)
    start = time.time()
    try:
        p = subprocess.run(['make', make_target], cwd=str(ROOT), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        duration = time.time() - start
        out = p.stdout.decode(errors='replace')
        err = p.stderr.decode(errors='replace')

        # Verify expected artifact(s) exist. Common outputs: atmega.hex, atmega.elf
        artifacts = [ROOT / 'atmega.hex', ROOT / 'atmega.elf']
        found = None
        for a in artifacts:
            try:
                if a.exists() and a.stat().st_size > 0:
                    # ensure artifact is newer than build start
                    if a.stat().st_mtime >= start - 1:
                        found = str(a)
                        break
            except Exception:
                continue

        ok = (p.returncode == 0) and (found is not None)
        return (ok, p.returncode, out, err, duration, found)
    except subprocess.TimeoutExpired as e:
        return (False, -1, '', 'timeout', timeout, None)


def mcu_supported(mcu, timeout=5):
    """Return True if avr-gcc accepts -mmcu=<mcu> on this host."""
    # Prefer a precomputed list if available (faster and more reliable in CI)
    gcc_list = ROOT / 'reports' / 'gcc_only.txt'
    if gcc_list.exists():
        try:
            supported = set(line.strip().upper() for line in open(gcc_list) if line.strip())
            if mcu.upper() in supported:
                return True
            # If not listed, fall through to a live probe in case the list is stale
        except Exception:
            pass
    # Probe avr-gcc directly as authoritative
    try:
        # Match Makefile behavior: avr-gcc expects lowercase canonical part names
        mcu_lower = mcu.lower()
        p = subprocess.run(['avr-gcc', '-mmcu=' + mcu_lower, '-x', 'c', '-', '-c', '-o', '/dev/null'], input=b'', stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout)
        return p.returncode == 0
    except Exception:
        return False


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument('--list', action='store_true', help='List combinations and exit (default)')
    ap.add_argument('--run', action='store_true', help='Run builds for each combination')
    ap.add_argument('--clean', action='store_true', help='Run `make clean` before each build')
    ap.add_argument('--baud', type=int, default=115200, help='Baud to use when running builds')
    ap.add_argument('--fcpu', type=int, default=16000000, help='F_CPU to use when running builds')
    ap.add_argument('--limit', type=int, default=0, help='Limit number of combinations to test (0 = all)')
    ap.add_argument('--report', type=str, help='Path to write CSV report when --run is used')
    ap.add_argument('--make-target', type=str, default='platform_build', help='Make target to build')
    args = ap.parse_args(argv)

    cfg = load_config()
    combos = enumerate_combinations(cfg)

    if args.limit > 0:
        combos = combos[:args.limit]

    print('Found %d combinations' % len(combos))
    if args.list or not args.run:
        # print a short table
        for c in combos:
            print('%s  %s  pin_option=%s' % (c['mcu'], c['uart'], str(c['pin_idx'])))
        return 0

    # run builds
    report_rows = []
    for i, c in enumerate(combos, 1):
        print('[%d/%d] Building %s %s pin=%s' % (i, len(combos), c['mcu'], c['uart'], str(c['pin_idx'])))
        # Skip combinations where the local avr-gcc doesn't support the MCU
        if not mcu_supported(c['mcu']):
            print(' -> SKIP (MCU not supported by local avr-gcc)')
            report_rows.append((c['mcu'], c['uart'], c['pin_idx'], False, -3, 0.0, None, '', 'unsupported'))
            continue
        # Optionally clean between builds to ensure a full rebuild per combo
        if args.clean:
            subprocess.run(['make', 'clean'], cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ok, code, out, err, dur, artifact = run_build(c, args.baud, args.fcpu, make_target=args.make_target)
        print(' -> %s in %.1fs (artifact=%s)' % ('OK' if ok else 'FAIL', dur, artifact or 'none'))
        report_rows.append((c['mcu'], c['uart'], c['pin_idx'], ok, code, dur, artifact, out, err))

    if args.report:
        import csv
        with open(args.report, 'w', newline='') as csvf:
            w = csv.writer(csvf)
            w.writerow(['mcu', 'uart', 'pin_idx', 'ok', 'retcode', 'duration_s', 'artifact'])
            for r in report_rows:
                w.writerow([r[0], r[1], r[2], r[3], r[4], r[5], r[6]])
        print('Wrote report to', args.report)

    # return non-zero if any failed
    failed = [r for r in report_rows if not r[3]]
    if failed:
        print('Failures: %d' % len(failed))
        return 2
    print('All builds succeeded')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
