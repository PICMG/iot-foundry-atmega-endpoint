#!/usr/bin/env python3
import os
import re
import json
import glob
import shlex

ROOT = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
MAKEFILE = os.path.join(ROOT, 'Makefile')

def read_var(name, text):
    m = re.search(r'^\s*' + re.escape(name) + r'\s*=\s*(.+)$', text, flags=re.M)
    if not m:
        return None
    return m.group(1).strip()

def main():
    with open(MAKEFILE, 'r') as f:
        mf = f.read()

    cc = read_var('CC', mf) or 'gcc'
    cflags = read_var('CFLAGS', mf) or ''

    # resolve common workspace-relative source patterns
    srcs = glob.glob(os.path.join(ROOT, 'src', '*.c')) + glob.glob(os.path.join(ROOT, 'src', 'core', '*.c'))
    srcs = [os.path.relpath(p, ROOT) for p in srcs]

    entries = []
    for src in srcs:
        cmd = ' '.join([shlex.quote(cc)] + cflags.split() + ['-c', shlex.quote(src)])
        entries.append({
            'directory': ROOT,
            'command': cmd,
            'file': os.path.join(ROOT, src)
        })

    out = os.path.join(ROOT, 'compile_commands.json')
    with open(out, 'w') as f:
        json.dump(entries, f, indent=2)
    print('Wrote', out)

if __name__ == '__main__':
    main()
