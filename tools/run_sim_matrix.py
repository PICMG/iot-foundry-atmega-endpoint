#!/usr/bin/env python3
"""
Run simulator build+test for each configuration in configurations.json.

Workflow per configuration (first entry only of process/uart/pin blocks):
1. Build firmware for the configuration (using make with env overrides).
2. Build simulator (`make sim`).
3. Start simulator in background and capture its PID. Wait for sim/pty_slave.txt to appear.
4. Run `tests/run_mctp_tests.py <pty> 9600` and capture result.
5. Stop the simulator process regardless of test outcome.
6. Report pass/fail for the configuration and continue to next.

Exit code: 0 if all configurations passed; non-zero otherwise.

Notes:
- This script assumes `make sim` produces `sim_bin` and that simulator writes `sim/pty_slave.txt` when ready.
- Firmware build step is generic: it will export SERIAL_UART_INDEX, SERIAL_TX_PORT, SERIAL_TX_PIN, SERIAL_RX_PORT, SERIAL_RX_PIN, SERIAL_BAUD to the environment for `make` if present in the config.
- The script uses timeouts and robust cleanup to ensure simulator is killed on error or Ctrl-C.
"""

import json
import os
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_FILE = ROOT / 'configurations.json'
SIM_PTY_FILE = ROOT / 'sim' / 'pty_slave.txt'
SIM_LOG = ROOT / 'sim.log'
SIM_PID_FILE = ROOT / 'sim' / 'sim.pid'

BUILD_TIMEOUT = 120
SIM_START_TIMEOUT = 5
TEST_TIMEOUT = 30
# Quiet mode: default to quiet for this test runner. Override by setting
# RUN_SIM_MATRIX_QUIET=0 in the environment to see verbose output.
QUIET = os.environ.get('RUN_SIM_MATRIX_QUIET', '1') != '0'


def load_configurations():
    with open(CONFIG_FILE, 'r') as f:
        data = json.load(f)
    # configurations.json groups UARTs by family; normalize into a flat list
    # and expand each entry into all combinations of included_parts x ports
    entries = []
    def collect_and_expand(group):
        for e in (group or []):
            family = 'classic_uarts' if 'type' in e and 'CLASSIC' in (e.get('type') or '') else 'zero_series_uarts'
            name = e.get('name')
            ports = e.get('ports') or []
            included = e.get('included_parts') or []
            # If no included parts, still keep the entry once
            if not included:
                included = [None]
            # If no ports, keep a single empty port option
            if not ports:
                ports = [None]
            for mcu in included:
                for port in ports:
                    newe = {}
                    newe['_family'] = family
                    if name is not None:
                        newe['name'] = name
                    if mcu is not None:
                        newe['included_parts'] = [mcu]
                    else:
                        newe['included_parts'] = []
                    if port is not None:
                        newe['ports'] = [port]
                    else:
                        newe['ports'] = []
                    # copy other fields if present
                    if 'type' in e:
                        newe['type'] = e.get('type')
                    entries.append(newe)

    if isinstance(data, dict):
        collect_and_expand(data.get('classic_uarts'))
        collect_and_expand(data.get('zero_series_uarts'))
    elif isinstance(data, list):
        # legacy shape: treat each element as already granular
        for e in data:
            entries.append(e)
    return entries


def load_raw_configurations():
    """Return a flat list of raw UART entries from configurations.json (preserve grouping).

    This returns each UART entry as it appears in the file (no per-MCU expansion).
    """
    with open(CONFIG_FILE, 'r') as f:
        data = json.load(f)
    entries = []
    if isinstance(data, dict):
        for e in (data.get('classic_uarts') or []):
            entries.append(e)
        for e in (data.get('zero_series_uarts') or []):
            entries.append(e)
    elif isinstance(data, list):
        for e in data:
            entries.append(e)
    return entries


def build_plan_one_processor_each():
    """Build a list of per-config dicts such that we pick one processor (MCU)
    for each discovered MCU and, for that MCU, run all UART/port variants
    that mention that MCU in their `included_parts` list.
    """
    raw = load_raw_configurations()
    # discover unique MCUs mentioned anywhere
    mcus = []
    for e in raw:
        for m in (e.get('included_parts') or []):
            if m not in mcus:
                mcus.append(m)

    plan = []
    for mcu in mcus:
        for e in raw:
            included = e.get('included_parts') or []
            # only consider UART entries that list this MCU
            if included and (mcu not in included):
                continue
            name = e.get('name')
            ports = e.get('ports') or [None]
            # if ports is empty, treat as single None option
            if not ports:
                ports = [None]
            for p in ports:
                newe = {}
                newe['_family'] = 'classic_uarts' if 'type' in e and 'CLASSIC' in (e.get('type') or '') else 'zero_series_uarts'
                if name is not None:
                    newe['name'] = name
                newe['included_parts'] = [mcu]
                if p is not None:
                    newe['ports'] = [p]
                else:
                    newe['ports'] = []
                if 'type' in e:
                    newe['type'] = e.get('type')
                plan.append(newe)
    return plan


def build_plan_one_representative_per_variant():
    """Group UART entries by (type, name, port-variant) and select one
    representative MCU per group. For each grouping we produce exactly one
    per-config dict to run (with included_parts containing the selected MCU).
    """
    raw = load_raw_configurations()
    groups = {}

    def port_key(p):
        if p is None:
            return None
        if isinstance(p, dict):
            return (p.get('txport'), p.get('txpin'), p.get('rxport'), p.get('rxpin'))
        return str(p)

    for e in raw:
        typ = e.get('type')
        name = e.get('name')
        ports = e.get('ports') or [None]
        if not ports:
            ports = [None]
        for p in ports:
            key = (typ, name, port_key(p))
            if key not in groups:
                groups[key] = {
                    'example_entry': e,
                    'ports': [],
                    'mcus': []
                }
            groups[key]['ports'].append(p)
            for m in (e.get('included_parts') or []):
                if m not in groups[key]['mcus']:
                    groups[key]['mcus'].append(m)

    plan = []
    for key, v in groups.items():
        e = v['example_entry']
        # pick representative MCU if available
        rep = v['mcus'][0] if v['mcus'] else None
        # ports list may contain duplicates if multiple entries matched; use unique
        ports_unique = []
        for p in v['ports']:
            if p not in ports_unique:
                ports_unique.append(p)
        for p in ports_unique:
            newe = {}
            newe['_family'] = 'classic_uarts' if 'type' in e and 'CLASSIC' in (e.get('type') or '') else 'zero_series_uarts'
            if e.get('name') is not None:
                newe['name'] = e.get('name')
            if rep is not None:
                newe['included_parts'] = [rep]
            else:
                newe['included_parts'] = []
            if p is not None:
                newe['ports'] = [p]
            else:
                newe['ports'] = []
            if 'type' in e:
                newe['type'] = e.get('type')
            plan.append(newe)
    return plan


## helper removed: build per-config env in `build_and_test_for_config`


def run_make_sim(env=None):
    proc = subprocess.run(['make', 'sim'], cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=BUILD_TIMEOUT)
    ok = proc.returncode == 0
    return ok, proc.stdout


def run_make_firmware(env=None):
    proc = subprocess.run(['make'], cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=BUILD_TIMEOUT)
    ok = proc.returncode == 0
    return ok, proc.stdout


def run_generate_serial_config(env=None):
    # Run only the generator target to produce include/generated_serial_config.h
    env2 = os.environ.copy()
    if env:
        env2.update(env)
    proc = subprocess.run(['make', 'include/generated_serial_config.h'], cwd=ROOT, env=env2, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=BUILD_TIMEOUT)
    ok = proc.returncode == 0
    return ok, proc.stdout


def run_make_download_core(env=None):
    # Run `make download-core` once to pre-populate core sources (network)
    # This can be skipped by setting RUN_SIM_MATRIX_SKIP_DOWNLOAD=1 in the environment.
    if os.environ.get('RUN_SIM_MATRIX_SKIP_DOWNLOAD', '') == '1':
        return True, 'skipped'
    proc = subprocess.run(['make', 'download-core'], cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=BUILD_TIMEOUT)
    ok = proc.returncode == 0
    return ok, proc.stdout


def start_simulator_background():
    # Ensure old pid/log files removed
    try:
        if SIM_PID_FILE.exists():
            SIM_PID_FILE.unlink()
    except Exception:
        pass
    # Start sim_bin in background, redirect output to sim.log
    sim_bin = ROOT / 'sim_bin'
    if not sim_bin.exists():
        return None, None
    out = open(SIM_LOG, 'w')
    proc = subprocess.Popen([str(sim_bin)], cwd=ROOT, stdout=out, stderr=subprocess.STDOUT, preexec_fn=os.setsid)
    # Write PID file too for convenience
    try:
        (ROOT / 'sim').mkdir(exist_ok=True)
        with open(SIM_PID_FILE, 'w') as f:
            f.write(str(proc.pid) + '\n')
    except Exception:
        pass
    # Wait for pty file to appear
    deadline = time.time() + SIM_START_TIMEOUT
    while time.time() < deadline:
        if SIM_PTY_FILE.exists():
            try:
                pty = SIM_PTY_FILE.read_text().strip()
                if pty:
                    return proc, pty
            except Exception:
                pass
        if proc.poll() is not None:
            return proc, None
        time.sleep(0.1)
    return proc, None


def stop_simulator(proc):
    if proc is None:
        return
    try:
        # kill process group
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except Exception:
        try:
            proc.terminate()
        except Exception:
            pass
    # wait briefly
    try:
        proc.wait(timeout=2)
    except Exception:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            pass


def run_tests_against_pty(pty_path):
    # Quick single-frame MCTP test: send SET_ENDPOINT_ID and expect any response.
    # run quietly; caller will print summarized result
    try:
        import serial
    except Exception:
        print('pyserial not available; cannot run inline test')
        return False

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

    def send_and_capture(device: str, frame: bytes, baud: int = 9600, settle: float = 0.2):
        # wait until the PTY file exists and is openable
        deadline = time.time() + 1.0
        while time.time() < deadline:
            if os.path.exists(device):
                try:
                    with serial.Serial(device, baud, timeout=0.01) as ser:
                        ser.reset_input_buffer()
                        time.sleep(settle)
                        ser.write(frame)
                        ser.flush()
                        data = bytearray()
                        last = time.time()
                        deadline2 = time.time() + 1.0
                        while time.time() < deadline2:
                            n = ser.in_waiting
                            if n:
                                data.extend(ser.read(n))
                                last = time.time()
                            else:
                                if data and (time.time() - last) > 0.05:
                                    break
                                time.sleep(0.001)
                        return bytes(data)
                except Exception:
                    # maybe race with PTY creation; retry briefly
                    time.sleep(0.01)
                    continue
            time.sleep(0.01)
        raise IOError('PTY not available: %s' % device)

    # Build SET_ENDPOINT_ID (cmd 0x01) with payload [0x00, 0x08]
    frame = build_mctp_control_request(0x01, payload=bytes([0x00, 0x08]))
    try:
        resp = send_and_capture(pty_path, frame, baud=9600)
        if resp:
            return True, len(resp)
        else:
            return False, 0
    except Exception:
        return False, 0


def build_and_test_for_config(cfg):
    # cfg is one UART entry from configurations.json
    env = os.environ.copy()
    # Pick first included part as MCU and first port option
    included = cfg.get('included_parts') or []
    if included:
        env['MCU'] = included[0]
    else:
        # fallback to a default MCU already present in Makefile
        env['MCU'] = env.get('MCU', '')

    # pick UART name (e.g. "USART0")
    uart_name = cfg.get('name') or ''
    if uart_name:
        env['SERIAL_UART'] = uart_name

    # pick first port option
    ports = cfg.get('ports') or []
    pin_idx = 0
    if ports:
        env['SERIAL_PIN_OPTION'] = '0'
        p0 = ports[0]
        # set explicit TX/RX envs if generator needs them
        if 'txport' in p0:
            env['SERIAL_TX_PORT'] = p0.get('txport')
        if 'txpin' in p0:
            env['SERIAL_TX_PIN'] = str(p0.get('txpin'))
        if 'rxport' in p0:
            env['SERIAL_RX_PORT'] = p0.get('rxport')
        if 'rxpin' in p0:
            env['SERIAL_RX_PIN'] = str(p0.get('rxpin'))

    # always provide a baud (default to 9600)
    env['SERIAL_BAUD'] = env.get('SERIAL_BAUD', '9600')

    # Perform steps; return dict of step results and optional outputs
    t0 = time.time()
    # Instead of rebuilding firmware, generate the serial config header only.
    # This ensures `include/generated_serial_config.h` and related artifacts
    # (include/last_mcu, include/last_fcpu) are produced without compiling AVR sources.
    fw_ok, fw_out = run_generate_serial_config(env=env)
    t_fw = time.time() - t0
    sim_build_ok, sim_out = False, ''
    t_sim_build = 0.0
    if fw_ok:
        t1 = time.time()
        sim_build_ok, sim_out = run_make_sim(env=env)
        t_sim_build = time.time() - t1

    proc, pty = (None, None)
    sim_started_ok = False
    t_sim_start = 0.0
    if sim_build_ok:
        t2 = time.time()
        proc, pty = start_simulator_background()
        t_sim_start = time.time() - t2
        t_after_start = time.time()
        if proc is not None and pty:
            sim_started_ok = True

    tests_ok, resp_len = False, 0
    t_tests = 0.0
    if sim_started_ok:
        try:
            t3 = time.time()
            tests_ok, resp_len = run_tests_against_pty(pty)
            t_tests = time.time() - t3
        except subprocess.TimeoutExpired:
            tests_ok = False

    # always stop simulator if it was started
    t_sim_run = 0.0
    if proc is not None:
        t_before_stop = time.time()
        # compute sim runtime (time between start completion and stop)
        try:
            if 't_after_start' in locals() and t_after_start:
                t_sim_run = t_before_stop - t_after_start
        except Exception:
            t_sim_run = 0.0
        stop_simulator(proc)

    t_total = time.time() - t0

    return {
        'firmware_ok': fw_ok,
        'firmware_out': fw_out,
        'sim_build_ok': sim_build_ok,
        'sim_build_out': sim_out,
        'sim_started_ok': sim_started_ok,
        'sim_pty': pty,
        'tests_ok': tests_ok,
        'resp_len': resp_len,
        'time_fw': t_fw,
        'time_sim_build': t_sim_build,
        'time_sim_start': t_sim_start,
        'time_sim_run': t_sim_run,
        'time_tests': t_tests,
        'time_total': t_total,
    }


def main():
    # Build plan: group by UART type/name/port variant and pick one
    # representative MCU per group.
    configs = build_plan_one_representative_per_variant()
    if not isinstance(configs, list):
        print('configurations.json root is not a list')
        sys.exit(2)

    # Iteratively build+test each configuration (build firmware, build sim,
    # start simulator, run tests, stop simulator) — failures per-stage mark
    # that configuration as FAIL and the runner continues to the next.

    # Run download-core once before the matrix to avoid repeated network fetches
    dl_ok, dl_out = run_make_download_core(env=os.environ.copy())
    if not dl_ok:
        print('Warning: `make download-core` failed or timed out; subsequent builds may download during make')

    # Optional limit: set RUN_SIM_MATRIX_LIMIT to run only first N configs (helpful for benchmarking)
    try:
        limit = int(os.environ.get('RUN_SIM_MATRIX_LIMIT', '0'))
    except Exception:
        limit = 0
    if limit and limit > 0:
        configs = configs[:limit]

    total = len(configs)
    overall_ok = True
    failures = []
    for idx, cfg in enumerate(configs):
        # Print a concise configuration summary (MCU, UART, PIN option)
        included = cfg.get('included_parts') or []
        mcu = included[0] if included else ''
        uart = cfg.get('name') or ''
        ports = cfg.get('ports') or []
        pin_desc = ''
        if ports:
            p0 = ports[0]
            if isinstance(p0, dict):
                txp = p0.get('txport')
                rxp = p0.get('rxport')
                txpin = p0.get('txpin')
                rxpin = p0.get('rxpin')
                if txp and rxp and txp == rxp:
                    pin_desc = f'PORT{txp}[{txpin},{rxpin}]'
                else:
                    pin_desc = f'TX=PORT{txp}[{txpin}] RX=PORT{rxp}[{rxpin}]'
            else:
                pin_desc = str(p0)

        print(f'CONFIG {idx+1}/{total}: MCU={mcu} UART={uart} PIN={pin_desc}')
        try:
            res = build_and_test_for_config(cfg)
        except KeyboardInterrupt:
            print('Interrupted by user')
            sys.exit(130)
        except Exception as e:
            print('Exception during config:', e)
            res = {
                'firmware_ok': False,
                'firmware_out': str(e),
                'sim_build_ok': False,
                'sim_build_out': '',
                'sim_started_ok': False,
                'sim_pty': None,
                'tests_ok': False,
                'resp_len': 0,
            }

        # Print compact stage results
        fw_ok = res.get('firmware_ok')
        sim_build_ok = res.get('sim_build_ok')
        sim_started_ok = res.get('sim_started_ok')
        tests_ok = res.get('tests_ok')

        print('  BUILDING:', 'PASSED' if fw_ok else 'FAILED', flush=True)
        print('  BUILDING SIM:', 'PASSED' if sim_build_ok else 'FAILED', flush=True)
        sim_run_ok = sim_started_ok and tests_ok
        print('  RUNNING SIMULATOR:', 'PASSED' if sim_run_ok else 'FAILED', flush=True)

        # (timing output suppressed)

        # Immediate overall result for this configuration (shown as we go)
        result_str = 'PASS' if (fw_ok and sim_build_ok and sim_run_ok) else 'FAIL'
        print('  RESULT:', result_str, flush=True)

        # If any stage failed, collect diagnostics
        if not (fw_ok and sim_build_ok and sim_run_ok):
            failures.append({
                'idx': idx,
                'mcu': mcu,
                'uart': uart,
                'pin': pin_desc,
                'firmware_ok': fw_ok,
                'sim_build_ok': sim_build_ok,
                'sim_run_ok': sim_run_ok,
            })

        overall_ok = overall_ok and fw_ok and sim_build_ok and sim_run_ok

    # Final summary
    passed = total - len(failures)
    print('\nSUMMARY:')
    print(f'  Total configurations: {total}')
    print(f'  Passed: {passed}')
    print(f'  Failed: {len(failures)}')
    # timing summary intentionally omitted
    if failures:
        print('  Failures:')
        for f in failures:
            print(f"    [{f['idx']+1}] MCU={f['mcu']} UART={f['uart']} PIN={f['pin']} -> fw:{'OK' if f['firmware_ok'] else 'FAIL'} sim_build:{'OK' if f['sim_build_ok'] else 'FAIL'} run:{'OK' if f['sim_run_ok'] else 'FAIL'}")

    print('ALL PASSED' if overall_ok else 'SOME FAILURES')
    sys.exit(0 if overall_ok else 1)


if __name__ == '__main__':
    main()
