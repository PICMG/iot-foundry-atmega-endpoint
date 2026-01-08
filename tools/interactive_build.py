#!/usr/bin/env python3
"""Interactive build parameter setter.

Prompts the user for common build parameters and writes them to
`include/last_build.make` as simple Makefile assignments. Existing
values are shown as defaults and accepted by pressing Enter.

This file is intended to be invoked via `make interactive`.
"""
import os
import re

import os
import re
import json

ROOT = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
OUT = os.path.join(ROOT, 'include', 'last_build.make')
CONFIG = os.path.join(ROOT, 'configurations.json')

DEFAULTS = {
    'MCU': 'atmega328p',
    'F_CPU': '16000000UL',
    'SERIAL_BAUD': '115200',
    'SERIAL_UART': '',
    'SERIAL_PIN_OPTION': '',
    'PROG': '',
    'PORT': '/dev/ttyUSB1',
    'PROG_BAUD': '115200',
}

COMMON_PROGS = ['arduino', 'stk500v1', 'stk500v2', 'usbasp', 'usbtiny', 'avrisp', 'avr109']


def load_existing(path):
    vals = {}
    if not os.path.exists(path):
        return vals
    with open(path, 'r') as f:
        for ln in f:
            m = re.match(r'^\s*([A-Za-z0-9_]+)\s*[:?]?=\s*(.*)$', ln)
            if m:
                k = m.group(1).strip()
                v = m.group(2).strip()
                vals[k] = v
    return vals


def prompt_simple(key, cur):
    prompt_text = f"{key} [{cur}]: " if cur != '' else f"{key} []: "
    val = input(prompt_text).strip()
    return val if val != '' else cur


def choose_from_list(prompt_text, options, cur):
    # Display numbered options and allow selection by number or direct value
    print(prompt_text)
    for i, opt in enumerate(options, start=1):
        print(f"  {i}) {opt}")
    sel = input(f"Choose [1-{len(options)}] or enter value [{cur}]: ").strip()
    if sel == '':
        return cur
    if sel.isdigit():
        idx = int(sel)
        if 1 <= idx <= len(options):
            return options[idx - 1]
    return sel


def load_config():
    if not os.path.exists(CONFIG):
        return []
    with open(CONFIG, 'r') as f:
        return json.load(f)


def mcus_from_config(cfg):
    s = set()
    for entry in cfg:
        for p in entry.get('part_numbers', []):
            s.add(p)
    return sorted(s)


def serial_options_for_mcu(cfg, mcu):
    opts = []
    for entry in cfg:
        for sp in entry.get('serial_ports', []):
            if 'included_parts' in sp:
                # match MCU case-insensitively (users may enter lowercase)
                matched = any(p.lower() == mcu.lower() for p in sp['included_parts'])
                if not matched:
                    continue
                # Create a label that includes the name and a brief ports summary
                ports = sp.get('ports', [])
                if len(ports) == 1:
                    p = ports[0]
                    label = f"{sp.get('name')} (tx {p.get('txport')}{p.get('txpin')} rx {p.get('rxport')}{p.get('rxpin')})"
                else:
                    label = f"{sp.get('name')} ({len(ports)} pin options)"
                opts.append({'name': sp.get('name'), 'label': label, 'entry': sp})
    # collapse by name preferring first occurrence
    seen = {}
    out = []
    for o in opts:
        if o['name'] not in seen:
            seen[o['name']] = o
            out.append(o)
    return out


def pin_options_for_serial(entry):
    ports = entry.get('ports', [])
    opts = []
    for p in ports:
        opts.append(f"tx {p.get('txport')}{p.get('txpin')} rx {p.get('rxport')}{p.get('rxpin')}")
    return opts


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    existing = load_existing(OUT)
    cfg = load_config()

    params = {}

    # MCU: show count of supported MCUs but allow free-form input
    mcus = mcus_from_config(cfg)
    ex_mcu = existing.get('MCU', os.environ.get('MCU', DEFAULTS['MCU']))
    print(f"Detected {len(mcus)} supported MCUs in configurations.json.")
    mcu = prompt_simple('MCU', ex_mcu)
    params['MCU'] = mcu

    # Offer SERIAL_UART choices based on the selected MCU
    ser_opts = serial_options_for_mcu(cfg, mcu)
    if ser_opts:
        labels = [o['label'] for o in ser_opts]
        ex_uart = existing.get('SERIAL_UART', os.environ.get('SERIAL_UART', DEFAULTS['SERIAL_UART']))
        chosen_label = choose_from_list('Available serial interfaces for MCU:', labels, ex_uart)
        # map back to name
        chosen = None
        for o in ser_opts:
            if o['label'] == chosen_label or o['name'] == chosen_label:
                chosen = o
                break
        if chosen is None and chosen_label.isdigit():
            idx = int(chosen_label) - 1
            if 0 <= idx < len(ser_opts):
                chosen = ser_opts[idx]
        if chosen:
            params['SERIAL_UART'] = chosen['name']
            # Present pin options if multiple
            pin_opts = pin_options_for_serial(chosen['entry'])
            if pin_opts:
                ex_pin = existing.get('SERIAL_PIN_OPTION', os.environ.get('SERIAL_PIN_OPTION', DEFAULTS['SERIAL_PIN_OPTION']))
                # If existing pin is stored as a numeric zero-based index, present it as 1-based for display
                display_pin = ex_pin
                try:
                    if isinstance(ex_pin, str) and ex_pin.isdigit():
                        display_pin = str(int(ex_pin) + 1)
                except Exception:
                    display_pin = ex_pin

                chosen_pin = choose_from_list('Select pin option:', pin_opts, display_pin)
                # Interpret numeric choices robustly: allow 1-based (user-friendly) or 0-based index
                if chosen_pin.isdigit():
                    idx = int(chosen_pin)
                    if 1 <= idx <= len(pin_opts):
                        params['SERIAL_PIN_OPTION'] = str(idx - 1)
                    elif 0 <= idx < len(pin_opts):
                        params['SERIAL_PIN_OPTION'] = str(idx)
                    else:
                        params['SERIAL_PIN_OPTION'] = str(idx)
                else:
                    # If user typed or selected a label, try to map it back to an index
                    if chosen_pin in pin_opts:
                        params['SERIAL_PIN_OPTION'] = str(pin_opts.index(chosen_pin))
                    else:
                        # store raw description if user typed something custom
                        params['SERIAL_PIN_OPTION'] = chosen_pin
        else:
            params['SERIAL_UART'] = existing.get('SERIAL_UART', DEFAULTS['SERIAL_UART'])
            params['SERIAL_PIN_OPTION'] = existing.get('SERIAL_PIN_OPTION', DEFAULTS['SERIAL_PIN_OPTION'])
    else:
        params['SERIAL_UART'] = existing.get('SERIAL_UART', DEFAULTS['SERIAL_UART'])
        params['SERIAL_PIN_OPTION'] = existing.get('SERIAL_PIN_OPTION', DEFAULTS['SERIAL_PIN_OPTION'])

    # Other simple prompts
    params['F_CPU'] = prompt_simple('F_CPU', existing.get('F_CPU', os.environ.get('F_CPU', DEFAULTS['F_CPU'])))
    params['SERIAL_BAUD'] = prompt_simple('SERIAL_BAUD', existing.get('SERIAL_BAUD', os.environ.get('SERIAL_BAUD', DEFAULTS['SERIAL_BAUD'])))

    # NOTE: Programmer selection and programmer baud are intentionally
    # omitted here; they are flash-specific and are collected by
    # `tools/interactive_flash.py` when running the flash-interactive flow.

    # Merge new params into any existing settings so we don't clobber
    # flash-related values (PORT/PROG) that are handled by
    # `tools/interactive_flash.py`.
    merged = dict(existing)
    merged.update(params)

    with open(OUT, 'w') as f:
        f.write('# Generated by tools/interactive_build.py\n')
        for k in sorted(merged.keys()):
            f.write(f"{k} = {merged[k]}\n")

    print('Wrote', OUT)
    build_now = input('Run build now? [Y/n]: ').strip().lower()
    if build_now in ('', 'y', 'yes'):
        os.execvp('make', ['make', 'all'])


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nInterrupted.')
        raise
