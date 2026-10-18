# -*- coding: utf-8 -*-
"""verify_review.py — 核对复盘报告里的每个数字是否与 _review.json / 计算结果一致"""
import json, os, re, sys
sys.stdout.reconfigure(encoding='utf-8')
R = r'E:\footbal-github\PitchQuant\reports\2026-10-17_14场_复盘.md'
D = r'E:\footbal-github\PitchQuant\data\tmp\batch_14\_review.json'
t = open(R, encoding='utf-8').read()
rows = json.load(open(D, encoding='utf-8'))
bad = []

def chk(label, cond, got):
    if not cond:
        bad.append('%s → %s' % (label, got))
    print('%s %-46s %s' % ('OK ' if cond else 'FAIL', label, got))

h1 = sum(1 for x in rows if x['hit1']); ha = sum(1 for x in rows if x['hitany'])
sh = sum(1 for x in rows if x['sh']); tr = sum(1 for x in rows if x['tr'])
ouj = [x for x in rows if x['ou'] is not None]; oum = sum(1 for x in ouj if x['ou'] is True)
hcw = sum(1 for x in rows if x['hc'] in ('win','half-win'))
arbh = sum(1 for x in rows if x['arb_hit'])

chk('方向 top1 7/14', h1 == 7, h1)
chk('方向 any 8/14', ha == 8, ha)
chk('比分 0/14', sh == 0, sh)
chk('总进球区间 4/14', tr == 4, tr)
chk('大小球 6/13', (oum, len(ouj)) == (6, 13), '%d/%d' % (oum, len(ouj)))
chk('让球主赢盘 7', hcw == 7, hcw)
chk('裁决后 8/14', arbh == 8, arbh)
chk('报告含 50.0%', '50.0%' in t, '50.0%' in t)
chk('报告含 57.1%', '57.1%' in t, '57.1%' in t)
chk('报告含 46.2%', '46.2%' in t, '46.2%' in t)
chk('报告含 P=0.016', '0.016' in t, '0.016' in t)
chk('报告含 P=0.942', '0.942' in t, '0.942' in t)

# 置信度分层
for c, exp_n, exp_h in (('HIGH',2,1), ('MID',2,2), ('MID-LOW',3,2), ('LOW',7,2)):
    g = [x for x in rows if x['conf'] == c]
    chk('置信度 %s n=%d 命中=%d' % (c, exp_n, exp_h),
        (len(g), sum(1 for x in g if x['hit1'])) == (exp_n, exp_h),
        '%d/%d' % (len(g), sum(1 for x in g if x['hit1'])))

# 逐场方向一致性（报告表 vs 计算结果）
seg = t.split('## 1. 逐场明细')[1].split('---')[0]
tbl = [l for l in seg.split('\n') if re.match(r'^\|\s*\d+\s*\|', l)]
chk('逐场表 14 行', len(tbl) == 14, len(tbl))
for l, x in zip(tbl, rows):
    cells = [c.strip() for c in l.strip().strip('|').split('|')]
    okd = ('✅' in cells[5]) if x['hit1'] else ('❌' in cells[5])
    if not okd:
        bad.append('方向标记不符: %s' % x['name'])
    a1, a2 = cells[6].split('/')
    if (a1.strip() != x['a1']) or (a2.strip() != x['a2']):
        bad.append('锚不符: %s 表=%s/%s 算=%s/%s' % (x['name'], a1, a2, x['a1'], x['a2']))
chk('逐场方向/锚标记逐行一致', all('不符' not in b for b in bad), bad[:2])

print('\n' + ('✅ 报告数字与计算结果全部一致' if not bad else '❌ 不一致项:\n  ' + '\n  '.join(bad)))
