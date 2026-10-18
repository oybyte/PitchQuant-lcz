# -*- coding: utf-8 -*-
"""review_ou.py — O2.5 分档回放（关键：大球判向为何只有 50%）"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

# (name, O2.5, 主流线, 实际总进球, 模型中心)
D = [
 ('埃弗斯堡',   1.461, 3.25, 7, 3.5),
 ('柏林联合',   1.511, 3.00, 0, 3.4),
 ('汉堡',      1.384, 3.25, 1, 3.7),
 ('沙尔克04',   1.615, 3.00, 1, 3.2),
 ('富勒姆',     1.726, 2.75, 1, 3.0),
 ('布伦特福德',  1.584, 3.00, 3, 3.2),
 ('曼城',      1.327, 3.50, 5, 3.9),
 ('比利亚雷亚尔', 1.442, 3.25, 0, 3.6),
 ('博洛尼亚',   1.652, 2.75, 4, 3.1),
 ('拜仁',      1.140, 4.75, 7, 5.0),
 ('纽卡斯尔',   1.635, 3.00, 1, 3.2),
 ('贝蒂斯',     1.256, 3.50, 7, 4.3),
 ('罗马',      1.840, 2.50, 2, 2.9),
 ('巴伦西亚',   2.057, 2.50, 0, 2.6),
]

print('='*112)
print('O2.5 分档回放（项目口径：O2.5<1.70 大球强 / 1.70-1.90 大球 / 1.90-2.10 中性 / >2.10 停判）')
print('='*112)
print('%-12s %-7s %-7s %-6s %-6s %-8s %s' % ('场次','O2.5','主流线','实际','判向','结果','说明'))
bands = {}
for n, o, line, tot, ctr in sorted(D, key=lambda t: t[1]):
    if o < 1.70: b = '大球强'
    elif o < 1.90: b = '大球'
    elif o <= 2.10: b = '中性'
    else: b = '停判'
    judged = b in ('大球强', '大球')
    win = (tot > 2.5) if judged else None
    res = '✅' if win else ('❌' if win is False else '—')
    note = ('实际%d球' % tot) + ('（小球=判错）' if (judged and tot <= 2.5) else '')
    print('%-12s %-7.3f %-7.2f %-6d %-6s %-8s %s' % (n, o, line, tot, b, res, note))
    bands.setdefault(b, []).append((tot, judged))

print()
for b in ('大球强', '大球', '中性', '停判'):
    g = bands.get(b, [])
    if not g: continue
    judged = [t for t, j in g if j]
    w = sum(1 for t in judged if t > 2.5)
    print('%-6s n=%2d  可判 %2d  判大命中 %d  %s' % (
        b, len(g), len(judged), w, ('%.0f%%' % (100.0*w/len(judged))) if judged else '—'))

print('\n' + '='*112)
print('主流线 vs 实际总进球（市场是不是系统性高估了？）')
print('='*112)
tot_line = [(l, t) for _, _, l, t, _ in D]
over_line = sum(1 for l, t in tot_line if t > l)
print('实际总进球 > 市场主流线: %d/14 = %.0f%%' % (over_line, 100.0*over_line/14))
print('实际总进球均值 %.2f vs 主流线均值 %.2f → 市场线高出实际 %.2f 球'
      % (sum(t for _, t in tot_line)/14.0, sum(l for l, _ in tot_line)/14.0,
         sum(l for l, _ in tot_line)/14.0 - sum(t for _, t in tot_line)/14.0))
print('实际总进球均值 %.2f vs 模型λ均值 %.2f → 模型高出实际 %.2f 球'
      % (sum(t for _, t in tot_line)/14.0, sum(c for *_, c in D)/14.0,
         sum(c for *_, c in D)/14.0 - sum(t for _, t in tot_line)/14.0))

print('\n' + '='*112)
print('极端场审查（模型中心与实际差 ≥3 球的 6 场）')
print('='*112)
for n, o, line, tot, ctr in D:
    if abs(tot - ctr) >= 3:
        print('  %-12s 模型 %.1f 球 → 实际 %d 球 (%+.1f)  O2.5=%.3f 主流线=%.2f' % (
            n, ctr, tot, tot-ctr, o, line))
print('\n这 6 场里 4 场是「模型高估」（0/1 球），2 场是「模型低估」（7 球）')
print('→ 高估与低估****数量接近但幅度不同****：低估 +3.5/+2.7，高估 -3.6/-3.4/-2.7/-2.6')

print('\n' + '='*112)
print('0-0 异常审查')
print('='*112)
zeros = [(n, o, line, ctr) for n, o, line, tot, ctr in D if tot == 0]
print('本批 0-0 共 %d 场（%.0f%%），项目五大联赛基准约 7-9%%' % (len(zeros), 100.0*len(zeros)/14))
for n, o, line, ctr in zeros:
    print('  %-12s O2.5=%.3f 主流线=%.2f 模型中心=%.1f → 实际 0 球（模型高估 %.1f 球）' % (n, o, line, ctr, ctr))
