#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_14.py — 批量跑 calc_all（机构通道=澳门基线 + Pinnacle 交叉校验基线）"""
import json, os, subprocess, sys, time
sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEST = os.path.join(ROOT, 'data', 'tmp', 'batch_14')
OUT = os.path.join(DEST, 'out')
os.makedirs(OUT, exist_ok=True)
man = json.load(open(os.path.join(DEST, '_manifest.json'), encoding='utf-8'))
fail = []
for m in man:
    base = m['name'].replace(' ', '_')
    txt = os.path.join(DEST, base + '.txt')
    for tag, eu in (('', m['eu']), ('.pin', m.get('eu_pin'))):
        if not eu:
            continue
        cmd = [sys.executable, os.path.join(ROOT, 'scripts', 'tmp', 'calc_all.py'), txt, m['lg'],
               '--eu', eu, '--handi', ('%.2f' % m['handi']),
               '--o25', '%.3f' % m['o25'], '--u25', '%.3f' % m['u25'],
               '--water', ('%.3f' % m['water']) if m.get('water') else '1.90']
        t0 = time.time()
        r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                           errors='replace', timeout=300, cwd=ROOT)
        open(os.path.join(OUT, base + tag + '.txt'), 'w', encoding='utf-8').write(r.stdout or '')
        if r.returncode != 0:
            fail.append((base + tag, r.returncode, (r.stderr or '')[-300:]))
        print('%-52s %-4s %5.1fs rc=%s' % ((base + tag)[:52], m['lg'], time.time() - t0, r.returncode))
print('\nFAILS:', len(fail))
for f in fail:
    print('  ', f)
