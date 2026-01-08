#!/usr/bin/env python3
import os
import sys
import json
import subprocess
import tempfile
import re
from math import floor

ROOT = os.path.dirname(os.path.dirname(__file__))
CONFIG = os.path.join(ROOT, 'configurations.json')
OUT_DIR = os.path.join(ROOT, 'include')
OUT_FILE = os.path.join(OUT_DIR, 'generated_serial_config.h')


def parse_int(s):
    if s is None:
        return None
    ss = str(s).upper().strip()
    # remove common suffixes
    for suf in ['UL', 'U', 'L']:
        if ss.endswith(suf):
            ss = ss[: -len(suf)]
    try:
        return int(ss, 0)
    except Exception:
        return None


def find_entries_for_mcu(cfg, mcu):
    mcu_u = mcu.upper()
    entries = []
    def collect_from_list(lst):
        for entry in lst:
            parts = entry.get('included_parts') or []
            for p in parts:
                if p.upper() == mcu_u:
                    entries.append(entry)
                    break

    # Support both new object shape and legacy array-of-groups
    if isinstance(cfg, dict):
        collect_from_list(cfg.get('classic_uarts', []))
        collect_from_list(cfg.get('zero_series_uarts', []))
    else:
        for group in cfg:
            collect_from_list(group.get('serial_ports', []))
    return entries


def compute_classic_ubrr(fcpu, baud):
    if baud <= 0:
        return None
    val = (fcpu / (16.0 * baud)) - 1.0
    return max(0, int(round(val)))


def compute_0series_bd(fcpu, baud):
    if baud <= 0:
        return None
    val = fcpu / (2.0 * baud)
    return max(1, int(round(val)))


def main():
    if not os.path.exists(CONFIG):
        print('configurations.json not found', file=sys.stderr)
        return 2

    cfg = json.load(open(CONFIG))
    MCU = os.environ.get('MCU') or os.environ.get('TARGET_MCU')
    if not MCU:
        print('MCU environment variable is required (e.g. MCU=ATmega328P)', file=sys.stderr)
        return 2

    SERIAL_BAUD = os.environ.get('SERIAL_BAUD')
    if not SERIAL_BAUD:
        print('SERIAL_BAUD environment variable is required (e.g. SERIAL_BAUD=115200)', file=sys.stderr)
        return 2

    SERIAL_UART = os.environ.get('SERIAL_UART')
    SERIAL_PIN_OPTION = os.environ.get('SERIAL_PIN_OPTION')
    # Treat empty-string env vars as not-provided (Makefile may pass empty values)
    if SERIAL_PIN_OPTION == '':
        SERIAL_PIN_OPTION = None
    F_CPU = os.environ.get('F_CPU') or os.environ.get('CPU_FREQ')
    fcpu = parse_int(F_CPU) if F_CPU else None
    if fcpu is None:
        # try a sensible default if not provided
        fcpu = 16000000

    baud = parse_int(SERIAL_BAUD)
    if baud is None:
        print('Invalid SERIAL_BAUD: %r' % SERIAL_BAUD, file=sys.stderr)
        return 2

    entries = find_entries_for_mcu(cfg, MCU)
    if not entries:
        print('MCU %s not found in configurations.json' % MCU, file=sys.stderr)
        return 2

    # collect available UART names
    names = [e.get('name') for e in entries]

    chosen = None
    if SERIAL_UART:
        for e in entries:
            if e.get('name') == SERIAL_UART:
                chosen = e
                break
        if chosen is None:
            print('Requested SERIAL_UART %s not valid for %s. Valid: %s' % (SERIAL_UART, MCU, ', '.join(names)), file=sys.stderr)
            return 2
    else:
        # if only one UART available, pick
        if len(entries) == 1:
            chosen = entries[0]
            SERIAL_UART = chosen.get('name')
        else:
            print('MCU %s exposes multiple UARTs: %s. Please set SERIAL_UART.' % (MCU, ', '.join(names)), file=sys.stderr)
            return 2

    ports = chosen.get('ports') or []
    nports = len(ports)
    pin_idx = None
    if SERIAL_PIN_OPTION is not None:
        try:
            pin_idx = int(SERIAL_PIN_OPTION)
        except Exception:
            print('Invalid SERIAL_PIN_OPTION: %r' % SERIAL_PIN_OPTION, file=sys.stderr)
            return 2
        if not (0 <= pin_idx < max(1, nports)):
            print('SERIAL_PIN_OPTION out of range for %s (%d options). Valid 0..%d' % (SERIAL_UART, nports, max(0, nports - 1)), file=sys.stderr)
            return 2
    else:
        if nports <= 1:
            pin_idx = 0
        else:
            print('UART %s has %d pin options. Please set SERIAL_PIN_OPTION (0..%d).' % (SERIAL_UART, nports, nports - 1), file=sys.stderr)
            return 2

    # Determine ports selection
    if ports:
        port_sel = ports[pin_idx]
        txport = port_sel.get('txport')
        txpin = port_sel.get('txpin')
        rxport = port_sel.get('rxport')
        rxpin = port_sel.get('rxpin')
        # optional muxing fields for 0-series devices
        muxreg = port_sel.get('muxreg')
        andmask = port_sel.get('andmask')
        ormask = port_sel.get('ormask')
    else:
        # fallback to tx_ports / rx_ports naming used by some entries
        tx = chosen.get('tx_ports', [])
        rx = chosen.get('rx_ports', [])
        if tx:
            txport = tx[0].get('port')
            txpin = tx[0].get('pin')
        else:
            txport = 'UNKNOWN'
            txpin = 0
        if rx:
            rxport = rx[0].get('port')
            rxpin = rx[0].get('pin')
        else:
            rxport = 'UNKNOWN'
            rxpin = 0

    utype = chosen.get('type')
    baud_reg_value = None
    achieved = None
    if utype == 'USART_CLASSIC':
        baud_reg_value = compute_classic_ubrr(fcpu, baud)
        if baud_reg_value is None:
            print('Failed to compute UBRR', file=sys.stderr)
            return 2
        achieved = fcpu / (16.0 * (baud_reg_value + 1))
    elif utype == 'USART_0SERIES':
        baud_reg_value = compute_0series_bd(fcpu, baud)
        achieved = fcpu / (2.0 * baud_reg_value) if baud_reg_value else None
    else:
        # unknown types: still output minimal macros
        baud_reg_value = 0

    err_pct = None
    if achieved:
        err_pct = abs(achieved - baud) / float(baud) * 100.0

    # ensure output dir
    os.makedirs(OUT_DIR, exist_ok=True)

    # write header
    with open(OUT_FILE, 'w') as f:
        f.write('/* generated by tools/generate_serial_config.py */\n')
        f.write('#ifndef GENERATED_SERIAL_CONFIG_H\n')
        f.write('#define GENERATED_SERIAL_CONFIG_H\n\n')

        # helper to avoid emitting duplicate defines when `macros` are provided
        emitted = set()
        def emit_define(name, rhs):
            if name in emitted:
                return
            f.write(f'#define {name} {rhs}\n')
            emitted.add(name)

        # If the chosen entry explicitly defines macros, emit them first and
        # record their names so later generated tokens don't overwrite them.
        for m in (chosen.get('macros') or []):
            mn = m.get('macro')
            mv = m.get('value')
            if mn and mv is not None:
                # write the RHS exactly as provided (caller may include quotes)
                emit_define(mn, mv)

        emit_define('SERIAL_BAUD', str(baud))
        emit_define('SERIAL_UART_NAME', '"%s"' % SERIAL_UART)
        # Emit numeric UART index (e.g., USART0 -> 0) for simpler platform code
        m_idx = re.search(r'(\d+)$', SERIAL_UART)
        uart_idx = int(m_idx.group(1)) if m_idx else 0
        emit_define('SERIAL_UART_INDEX', str(uart_idx))
        emit_define(f'SERIAL_UART_TYPE_{utype}', '1')
        emit_define('SERIAL_PIN_OPTION', str(pin_idx))
        emit_define('SERIAL_TX_PORT', str(txport))
        emit_define('SERIAL_TX_PIN', str(txpin))
        emit_define('SERIAL_RX_PORT', str(rxport))
        emit_define('SERIAL_RX_PIN', str(rxpin))
        # mux fields (muxreg/andmask/ormask) are mapped later after probing
        # available register tokens; store values in local vars above for use
        emit_define('SERIAL_BAUD_REG_VALUE', str(0 if baud_reg_value is None else int(baud_reg_value)))
        emit_define('GENERATED_MCU', '"%s"' % MCU)
        # Emit generated F_CPU macro (prefer raw env string if provided)
        env_fcpu = os.environ.get('F_CPU') or os.environ.get('CPU_FREQ')
        if env_fcpu:
            emit_define('GENERATED_F_CPU', env_fcpu)
        else:
            emit_define('GENERATED_F_CPU', f'{fcpu}UL')

        # Helper: probe avr-gcc preprocessor to see if a register macro exists
        reg_exists_cache = {}
        def register_exists(mcu_name, regname):
            key = (mcu_name.lower(), regname)
            if key in reg_exists_cache:
                return reg_exists_cache[key]
            php = '#include <avr/io.h>\n'
            try:
                with tempfile.NamedTemporaryFile('w', delete=False, suffix='.c') as tf:
                    tf.write(php)
                    tfpath = tf.name
                cmd = ['avr-gcc', '-std=gnu11', '-mmcu=%s' % mcu_name.lower(), '-E', '-dM', tfpath]
                out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, universal_newlines=True)
                found = False
                pat = r'#define\s+%s\b' % re.escape(regname)
                if re.search(pat, out):
                    found = True
            except Exception:
                found = False
            finally:
                try:
                    os.unlink(tfpath)
                except Exception:
                    pass
            reg_exists_cache[key] = found
            return found

        # If the selected port specified muxing configuration (for example
        # `muxreg`/`andmask`/`ormask`) attempt to map the named register to
        # a token in the MCU headers. Prefer the raw token if present, else
        # try a PORTMUX_ prefixed variant (common on some AVR headers).
        try:
            if 'muxreg' in (port_sel or {}):
                def parse_mask(v):
                    if v is None:
                        return None
                    s = str(v).strip()
                    if re.fullmatch(r'[01]+', s):
                        return int(s, 2)
                    try:
                        return int(s, 0)
                    except Exception:
                        return None

                # Candidate tokens to probe
                candidates = []
                if muxreg:
                    candidates.append(str(muxreg))
                    candidates.append('PORTMUX_' + str(muxreg))

                chosen_mux = None
                for cand in candidates:
                    if register_exists(MCU, cand):
                        chosen_mux = cand
                        break

                if chosen_mux:
                    emit_define('SERIAL_MUXREG', chosen_mux)
                am = parse_mask(andmask)
                om = parse_mask(ormask)
                if am is not None:
                    emit_define('SERIAL_MUX_ANDMASK', f'0x{am:02X}')
                if om is not None:
                    emit_define('SERIAL_MUX_ORMASK', f'0x{om:02X}')
        except Exception:
            pass

        if utype == 'USART_0SERIES':
            emit_define('MCTP_USART_0SERIES', '1')

        if err_pct is not None:
            f.write('/* achieved baud: %.2f Hz (error %.3f%%) */\n' % (achieved, err_pct))
        f.write('\n#endif /* GENERATED_SERIAL_CONFIG_H */\n')

    # print summary for user
    print('Wrote', OUT_FILE)
    print('MCU=%s UART=%s PIN_OPTION=%d BAUD=%d' % (MCU, SERIAL_UART, pin_idx, baud))
    if achieved:
        print('achieved baud: %.2f Hz (error %.3f%%)' % (achieved, err_pct))

    # also write a small file recording the last MCU used so other make targets
    # (for example `make flash`) can use the same MCU without passing it.
    lastpath = os.path.join(OUT_DIR, 'last_mcu')
    try:
        with open(lastpath, 'w') as lm:
            lm.write('%s\n' % MCU)
    except Exception:
        print('Warning: failed to write %s' % lastpath, file=sys.stderr)

    # Persist F_CPU so subsequent `make`/`make flash` runs can reuse it
    last_fcpu_path = os.path.join(OUT_DIR, 'last_fcpu')
    try:
        fstr = os.environ.get('F_CPU') or os.environ.get('CPU_FREQ')
        if not fstr:
            fstr = str(fcpu) + 'UL'
        with open(last_fcpu_path, 'w') as lf:
            lf.write('%s\n' % fstr)
    except Exception:
        print('Warning: failed to write %s' % last_fcpu_path, file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
