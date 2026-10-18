#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v259d_run.py — 批量跑 calc_all（澳门基线 + Pinnacle 交叉校验基线）"""
import json
import os
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEST = os.path.join(ROOT, 'data', 'tmp', 'batch_v259d')
OUT = os.path.join(DEST, 'out')
os.makedirs(OUT, exist_ok=True)
man = json.load(open(os.path.join(DEST, '_manifest.json'), encoding='utf-8'))

fail = []
for m in man:
    base = m['name'].replace(' ', '_').replace('(', '').replace(')', '')
    txt = os.path.join(DEST, base + '.txt')
    for tag, eu in (('', m['eu']), ('.pin', m.get('eu_pin'))):
        if not eu:
            continue
        cmd = [sys.executable, os.path.join(ROOT, 'scripts', 'tmp', 'calc_all.py'), txt, m['lg'],
               '--eu', eu, '--handi', '%g' % m['handi'],
               '--o25', '%.3f' % m['o25'], '--u25', '%.3f' % m['u25'],
               '--water', '%.3f' % m['water']]
        t0 = time.time()
        r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                           errors='replace', timeout=300, cwd=ROOT)
        open(os.path.join(OUT, base + tag + '.txt'), 'w', encoding='utf-8').write(r.stdout or '')
        if r.returncode != 0:
            fail.append((base + tag, r.returncode, (r.stderr or '')[-300:]))
        print('%-56s %-6s %5.1fs rc=%s' % ((base + tag)[:56], m['lg'], time.time() - t0, r.returncode), flush=True)
print('\nFAILS:', len(fail))
for f in fail:
    print('  ', f)
