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
        f.write('#define SERIAL_BAUD %d\n' % baud)
        f.write('#define SERIAL_UART_NAME "%s"\n' % SERIAL_UART)
        f.write('#define SERIAL_UART_TYPE_%s 1\n' % (utype))
        f.write('#define SERIAL_PIN_OPTION %d\n' % pin_idx)
        f.write('#define SERIAL_TX_PORT %s\n' % txport)
        f.write('#define SERIAL_TX_PIN %s\n' % txpin)
        f.write('#define SERIAL_RX_PORT %s\n' % rxport)
        f.write('#define SERIAL_RX_PIN %s\n' % rxpin)
        f.write('#define SERIAL_BAUD_REG_VALUE %d\n' % (0 if baud_reg_value is None else int(baud_reg_value)))
        f.write('#define GENERATED_MCU "%s"\n' % MCU)
        # Emit generated F_CPU macro (prefer raw env string if provided)
        env_fcpu = os.environ.get('F_CPU') or os.environ.get('CPU_FREQ')
        if env_fcpu:
            f.write('#define GENERATED_F_CPU %s\n' % env_fcpu)
        else:
            f.write('#define GENERATED_F_CPU %sUL\n' % (fcpu))

        # Emit board-level aliases expected by src/platform.c and code
        # Map baud and pins
        f.write('\n')
        f.write('/* MCTP platform aliases (auto-generated) */\n')
        f.write('#define MCTP_BAUD %d\n' % baud)
        f.write('#define MCTP_UART_TX_PORT %s\n' % txport)
        f.write('#define MCTP_UART_TX_PIN %s\n' % txpin)
        f.write('#define MCTP_UART_RX_PORT %s\n' % rxport)
        f.write('#define MCTP_UART_RX_PIN %s\n' % rxpin)

        # Create port DIR token. Classic AVRs use DDRx, newer 0-series use PORTx_DIR.
        try:
            if utype == 'USART_CLASSIC':
                f.write('#define MCTP_TX_PORT_DIR DDR%s\n' % txport)
                f.write('#define MCTP_RX_PORT_DIR DDR%s\n' % rxport)
            else:
                f.write('#define MCTP_TX_PORT_DIR PORT%s_DIR\n' % txport)
                f.write('#define MCTP_RX_PORT_DIR PORT%s_DIR\n' % rxport)
        except Exception:
            pass

        # Map register names if available in configuration entry
        regs = chosen.get('registers') or []
        # helper: probe avr-gcc preprocessor to see if a register macro exists
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

        if regs:
            if utype == 'USART_0SERIES':
                # Normalize register tokens for 0-series naming conventions
                # e.g., TXDATAL0 -> USART0_TXDATAL which matches avr/io headers
                mapped_regs = []
                for r in regs:
                    rr = str(r)
                    m = re.match(r'([A-Za-z_]+)(\d+)$', rr)
                    if m:
                        name = m.group(1)
                        idx = m.group(2)
                        mapped = 'USART%s_%s' % (idx, name)
                    else:
                        mapped = rr
                    mapped_regs.append(mapped)

                # regs layout for 0-series: [RXDATALn, RXDATAHn, TXDATALn, TXDATAHn, STATUSn, CTRLAn, CTRLBn, CTRLCn, BAUDn, ...]
                if len(mapped_regs) > 0:
                    f.write('#define MCTP_USART_RXDATAL %s\n' % mapped_regs[0])
                if len(mapped_regs) > 1:
                    f.write('#define MCTP_USART_RXDATAH %s\n' % mapped_regs[1])
                if len(mapped_regs) > 2:
                    f.write('#define MCTP_USART_TXDATAL %s\n' % mapped_regs[2])
                if len(mapped_regs) > 3:
                    f.write('#define MCTP_USART_TXDATAH %s\n' % mapped_regs[3])
                if len(mapped_regs) > 4:
                    f.write('#define MCTP_USART_STATUS %s\n' % mapped_regs[4])
                if len(mapped_regs) > 5:
                    f.write('#define MCTP_USART_CTRLA %s\n' % mapped_regs[5])
                if len(mapped_regs) > 6:
                    f.write('#define MCTP_USART_CTRLB %s\n' % mapped_regs[6])
                if len(mapped_regs) > 7:
                    f.write('#define MCTP_USART_CTRLC %s\n' % mapped_regs[7])
            else:
                # Classic AVR: prefer legacy register tokens without numeric indices
                mapped_regs = []
                for r in regs:
                    rr = str(r)
                    # candidate: strip all digits (e.g., UCSR0A -> UCSRA, UDR0 -> UDR)
                    candidate = re.sub(r'\d+', '', rr)
                    if candidate and register_exists(MCU, candidate):
                        mapped_regs.append(candidate)
                    else:
                        # fallback to original token if probe failed
                        mapped_regs.append(rr)

                if len(mapped_regs) > 0:
                    f.write('#define MCTP_USART_RXDATAL %s\n' % mapped_regs[0])
                    f.write('#define MCTP_USART_TXDATAL %s\n' % mapped_regs[0])
                if len(mapped_regs) > 1:
                    f.write('#define MCTP_USART_CTRLA %s\n' % mapped_regs[1])
                if len(mapped_regs) > 2:
                    f.write('#define MCTP_USART_CTRLB %s\n' % mapped_regs[2])
                if len(mapped_regs) > 3:
                    f.write('#define MCTP_USART_CTRLC %s\n' % mapped_regs[3])
                if len(mapped_regs) > 1:
                    f.write('#define MCTP_USART_STATUS %s\n' % mapped_regs[1])


        # Baud register mapping
        baud_regs = chosen.get('baud_registers') or []
        if baud_regs:
            br = baud_regs[0].get('register')
            if br:
                # try a candidate without digits (e.g., UBRR0 -> UBRR) and prefer it
                brs = str(br)
                candidate = re.sub(r'\d+', '', brs)
                br_mapped = None
                if candidate and register_exists(MCU, candidate):
                    br_mapped = candidate
                else:
                    # fallback to original normalization used previously
                    mbr = re.match(r'([A-Za-z_]+)(\d+)$', brs)
                    if mbr:
                        bname = mbr.group(1)
                        bidx = mbr.group(2)
                        br_mapped = 'USART%s_%s' % (bidx, bname)
                    else:
                        br_mapped = brs

                f.write('#define MCTP_USART_BAUD %s\n' % br_mapped)
                # If we detected a classic-style UBRR (either UBRR or UBRRn) provide a writer that splits H/L
                m = re.match(r'UBRR(\d+)$', brs)
                if m:
                    # original had numeric index (UBRRn) - prefer UBRRnH/UBRRnL if present,
                    # otherwise fall back to UBRRH/UBRRL when those exist in classic headers
                    n = m.group(1)
                    use_pair = None
                    if register_exists(MCU, 'UBRR%sH' % n) and register_exists(MCU, 'UBRR%sL' % n):
                        use_pair = ('UBRR%sH' % n, 'UBRR%sL' % n)
                    elif register_exists(MCU, 'UBRRH') and register_exists(MCU, 'UBRRL'):
                        use_pair = ('UBRRH', 'UBRRL')
                    if use_pair:
                        f.write('\n')
                        f.write('/* Classic UBRR writer for %s */\n' % brs)
                        f.write('#ifndef MCTP_USART_WRITE_UBRR\n')
                        f.write('#define MCTP_USART_WRITE_UBRR(v) do { %s = (uint8_t)(((v)>>8) & 0xff); %s = (uint8_t)((v) & 0xff); } while (0)\n' % (use_pair[0], use_pair[1]))
                        f.write('#endif\n')
                else:
                    # If we selected a stripped candidate like 'UBRR', write to UBRRH/UBRRL
                    if br_mapped and re.match(r'UBRR$', br_mapped):
                        f.write('\n')
                        f.write('/* Classic UBRR writer for %s */\n' % br_mapped)
                        f.write('#ifndef MCTP_USART_WRITE_UBRR\n')
                        f.write('#define MCTP_USART_WRITE_UBRR(v) do { UBRRH = (uint8_t)(((v)>>8) & 0xff); UBRRL = (uint8_t)((v) & 0xff); } while (0)\n')
                        f.write('#endif\n')
                    else:
                        # For single BAUD register (DA/DB family) we let platform.c write directly
                        pass

        # Ensure baud-mode constants are defined so generated header is self-contained
        f.write('\n')
        f.write('/* Baud mode constants (generated) */\n')
        f.write('#ifndef MCTP_BAUD_MODE_DA_DB\n')
        f.write('#define MCTP_BAUD_MODE_DA_DB 1\n')
        f.write('#endif\n')
        f.write('#ifndef MCTP_BAUD_MODE_CLASSIC\n')
        f.write('#define MCTP_BAUD_MODE_CLASSIC 2\n')
        f.write('#endif\n')
        f.write('#ifndef MCTP_BAUD_MODE_AUTO\n')
        f.write('#define MCTP_BAUD_MODE_AUTO 0\n')
        f.write('#endif\n')
        # Set baud mode macro according to UART architecture
        if utype == 'USART_CLASSIC':
            f.write('#define MCTP_BAUD_MODE MCTP_BAUD_MODE_CLASSIC\n')
        elif utype == 'USART_0SERIES':
            f.write('#define MCTP_BAUD_MODE MCTP_BAUD_MODE_DA_DB\n')
            f.write('#define MCTP_USART_0SERIES 1\n')
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
