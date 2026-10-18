# -*- coding: utf-8 -*-
"""audit_zero_goal.py — 0 球是否被 g01 合并吃掉了？用 435 场真实赛果量化
结论直接决定 P0 的修法：如果 0 球率随档位变化显著，就必须独立拆出来。
"""
import json, os, sys
from collections import Counter
sys.stdout.reconfigure(encoding='utf-8')
R = r'E:\footbal-github\\..\\PitchQuant\\data\\tmp'
R = r'E:\footbal-github\PitchQuant\data\tmp'
rows = []
seen = {}
for b in ('batch_203', 'batch_140', 'batch_74', 'batch_2_5_8'):
    p = os.path.join(R, b, 'result_compare.json')
    if not os.path.exists(p): continue
    for r in json.load(open(p, encoding='utf-8')):
        r['_b'] = b
        seen[r['slug']] = r
rows = list(seen.values())
print('样本 %d 场\n' % len(rows))

BANDS = [(1.00,1.30),(1.30,1.50),(1.50,1.70),(1.70,1.90),(1.90,2.10),(2.10,2.30),(2.30,2.60),(2.60,99)]
print('='*104)
print('按 O2.5 档位：0球 / 1球 / 0-1合并 / 2球 / 3球 / 4+球  实际分布')
print('='*104)
print('%-12s %5s %8s %8s %10s %8s %8s %8s' % ('档位','n','0球%','1球%','g01(表内)%','2球%','3球%','4+球%'))
tot0_all = 0
for lo, hi in BANDS:
    g = [r for r in rows if lo <= (r.get('o25') or 0) < hi]
    if not g: continue
    n = len(g)
    tc = Counter(r['tot'] for r in g)
    z = 100.0*tc.get(0,0)/n; o = 100.0*tc.get(1,0)/n
    tot0_all += tc.get(0,0)
    print('%-12s %5d %7.1f%% %7.1f%% %9.1f%% %7.1f%% %7.1f%% %7.1f%%' % (
        '%.2f-%.2f' % (lo, hi), n, z, o, z+o,
        100.0*tc.get(2,0)/n, 100.0*tc.get(3,0)/n,
        100.0*sum(v for k,v in tc.items() if k >= 4)/n))

print('\n' + '='*104)
print('0 球率随档位的分离度（决定是否需要独立拆出）')
print('='*104)
lo_g = [r for r in rows if (r.get('o25') or 9) < 1.70]
hi_g = [r for r in rows if (r.get('o25') or 0) > 2.10]
def zr(g):
    return 100.0*sum(1 for r in g if r['tot'] == 0)/len(g) if g else 0
print('大球强档(O2.5<1.70) n=%d  0球率 %.1f%%' % (len(lo_g), zr(lo_g)))
print('小球档  (O2.5>2.10) n=%d  0球率 %.1f%%' % (len(hi_g), zr(hi_g)))
print('差 %.1fpp → 0 球率**随档位显著变化** → 必须独立拆出，不能并进 g01' % (zr(hi_g)-zr(lo_g)))
print('\n全样本 0 球: %d/%d = %.1f%%   （若并入 g01，模型在结构上看不到这 %.1f%%）'
      % (tot0_all, len(rows), 100.0*tot0_all/len(rows), 100.0*tot0_all/len(rows)))

print('\n' + '='*104)
print('若把 0 球独立建模，理论收益（用本批 14 场验证）')
print('='*104)
B14 = [(3.25,7),(3.00,0),(3.25,1),(3.00,1),(2.75,1),(3.00,3),(3.50,5),(3.25,0),
       (2.75,4),(4.75,7),(3.00,1),(3.50,7),(2.50,2),(2.50,0)]
z14 = sum(1 for _,t in B14 if t == 0)
print('本批 14 场 0 球: %d 场 = %.0f%%（常态约 %.1f%%）' % (z14, 100.0*z14/14, 100.0*tot0_all/len(rows)))
print('若模型能单独给 0 球出口，这 %d 场的"方向+比分"至少有出口可比，而不是被判成 3.4 球的对攻' % z14)
