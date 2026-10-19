#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_batch.py — 通用批量跑 calc_all（双基线：澳门 + Pinnacle 交叉校验）

run_14.py 是硬编码 batch_14 的一次性脚本；本文件把同一逻辑参数化，
供任意 v259_ingest 产出的批次复用（--dest <批次目录>）。

用法:
    python scripts/tmp/run_batch.py --dest data/tmp/batch_v259W
    python scripts/tmp/run_batch.py --dest data/tmp/batch_v259W --only 10-18  # 只跑文件名含子串的场次

产物: <dest>/out/<base>.txt（澳门基线） + <base>.pin.txt（Pinnacle 基线·交叉校验）
"""
import argparse
import json
import os
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dest', required=True, help='批次目录（含 _manifest.json 与标准 txt）')
    ap.add_argument('--only', default='', help='只跑文件名含该子串的场次')
    ap.add_argument('--no-pin', action='store_true', help='不跑 Pinnacle 基线')
    a = ap.parse_args()

    dest = a.dest if os.path.isabs(a.dest) else os.path.join(ROOT, a.dest)
    out = os.path.join(dest, 'out')
    os.makedirs(out, exist_ok=True)
    man = json.load(open(os.path.join(dest, '_manifest.json'), encoding='utf-8'))
    calc_all = os.path.join(ROOT, 'scripts', 'tmp', 'calc_all.py')
    fails = []
    for m in man:
        base = m['name'].replace(' ', '_')
        if a.only and a.only not in base:
            continue
        txt = os.path.join(dest, base + '.txt')
        if not os.path.exists(txt):
            fails.append((base, 'txt missing'))
            continue
        variants = [('', m.get('eu'))]
        if not a.no_pin:
            variants.append(('.pin', m.get('eu_pin')))
        for tag, eu in variants:
            if not eu:
                continue
            cmd = [sys.executable, calc_all, txt, m['lg'],
                   '--eu', eu, '--handi', ('%.2f' % m['handi']),
                   '--o25', '%.3f' % m['o25'], '--u25', '%.3f' % m['u25'],
                   '--water', ('%.3f' % m['water']) if m.get('water') else '1.90']
            t0 = time.time()
            r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                               errors='replace', timeout=300, cwd=ROOT)
            open(os.path.join(out, base + tag + '.txt'), 'w', encoding='utf-8').write(r.stdout or '')
            if r.returncode != 0:
                fails.append((base + tag, r.returncode, (r.stderr or '')[-300:]))
            print('%-56s %-6s %5.1fs rc=%s' % ((base + tag)[:56], m['lg'],
                                               time.time() - t0, r.returncode))
    print('\nFAILS:', len(fails))
    for f in fails:
        print('  ', f)


if __name__ == '__main__':
    main()
