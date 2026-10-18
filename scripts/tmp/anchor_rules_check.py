# -*- coding: utf-8 -*-
"""anchor_rules_check.py — 主锚是否满足 O2.5 档位铁律（大球强→主锚≥3球 / 大球→主锚≥2球）
仅校验报告里的锚，不重算任何数值。"""
import re, sys
sys.stdout.reconfigure(encoding='utf-8')
t = open(r'E:\footbal-github\PitchQuant\reports\2026-10-17_14场_分析报告.md', encoding='utf-8').read()
seg = t.split('## 1. 总览结论表')[1].split('---')[0]
rows = [[x.strip() for x in l.strip().strip('|').split('|')] for l in seg.split('\n') if re.match(r'^\|\s*\d+\s*\|', l)]
o25 = [1.461, 1.511, 1.384, 1.615, 1.726, 1.584, 1.327, 1.442, 1.652, 1.140, 1.635, 1.256, 1.840, 2.057]
bad = 0
for r, o in zip(rows, o25):
    num, ko, lg, tm, dirn, conf, a1, a2, bs, goal, trust = r
    g1 = sum(int(x) for x in a1.split(':'))
    g2 = sum(int(x) for x in a2.split(':'))
    need_hi = o < 1.70          # 大球强 → 主锚 ≥3
    need_mid = 1.70 <= o < 1.90  # 大球 → 主锚 ≥2
    ok = (g1 >= 3) if need_hi else ((g1 >= 2) if need_mid else True)
    tag = '大球强(≥3)' if need_hi else ('大球(≥2)' if need_mid else '中性(不限)')
    flag = 'OK ' if ok else '❌ 违规'
    if not ok:
        bad += 1
    print('%2s %-24s O2.5=%.3f %-12s 主锚 %s(=%d球) 次锚 %s(=%d球) %s' % (num, tm[:24], o, tag, a1, g1, a2, g2, flag))
print('\n违规场次:', bad)
