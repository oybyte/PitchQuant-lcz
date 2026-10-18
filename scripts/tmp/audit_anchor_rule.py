# -*- coding: utf-8 -*-
"""audit_anchor_rule.py — A/B 回测「大球档主锚必须≥N球」这条规则本身

用 435 场真实赛果 + 各场实际 Top1/Top2 候选，量化：
  A 组（现行规则 O2.5<1.70 → 主锚≥3球；1.70-1.90 → 主锚≥2球）
  B 组（照搬 Top1，不设下限）
比较两组「主锚总进球 ≥ N」的真实命中率——若规则抬高的方向并不更常命中，规则就是负贡献。
"""
import json, os, sys
from collections import Counter
sys.stdout.reconfigure(encoding='utf-8')
R = r'E:\footbal-github\PitchQuant\data\tmp'
seen = {}
for b in ('batch_203', 'batch_140', 'batch_74', 'batch_2_5_8'):
    p = os.path.join(R, b, 'result_compare.json')
    if not os.path.exists(p): continue
    for r in json.load(open(p, encoding='utf-8')):
        seen[r['slug']] = r
rows = [r for r in seen.values() if r.get('o25') and r.get('score')]

def tot(s):
    try:
        h, a = map(int, s.split(':'))
        return h + a
    except Exception:
        return None

print('样本 %d 场\n' % len(rows))
print('='*100)
print('核心问题: 「大球档 → 主锚必须 ≥N 球」抬高后的锚，真的更常命中吗？')
print('='*100)

# 按档位看「实际总进球」分布
for lo, hi, need in ((1.00, 1.70, 3), (1.70, 1.90, 2)):
    g = [r for r in rows if lo <= r['o25'] < hi]
    if not g: continue
    tr = [tot(r['a1']) for r in g]
    ta = [tot(r['score']) for r in g]
    tr = [x for x in tr if x is not None]
    ta = [x for x in ta if x is not None]
    ge = sum(1 for x in ta if x >= need)
    print('\n档 %.2f-%.2f  规则要求主锚 ≥%d 球' % (lo, hi, need))
    print('  该档 n=%d' % len(g))
    print('  实际总进球 ≥%d 的比例: %d/%d = %.1f%%' % (need, ge, len(ta), 100.0*ge/len(ta)))
    print('  脚本 Top1 锚的总进球均值 %.2f' % (sum(tr)/len(tr) if tr else 0))
    print('  实际比分总进球均值   %.2f' % (sum(ta)/len(ta) if ta else 0))
    # 规则抬高后是否更准：Top1 的总进球 vs 实际
    ok1 = sum(1 for r in g if tot(r['a1']) is not None and tot(r['a1']) >= need)
    print('  Top1 本身已满足 ≥%d 的场次: %d/%d = %.0f%%（其余需被规则抬高）'
          % (need, ok1, len(g), 100.0*ok1/len(g)))

print('\n' + '='*100)
print('A/B 对照：规则抬高 vs 不抬高，谁的主锚更接近实际？')
print('='*100)
print('%-12s %6s %10s %10s %10s' % ('档位','n','Top1命中','抬高后命中','差'))
for lo, hi, need in ((1.00, 1.70, 3), (1.70, 1.90, 2)):
    g = [r for r in rows if lo <= r['o25'] < hi]
    if not g: continue
    # A: 照搬 Top1
    aA = sum(1 for r in g if tot(r['a1']) is not None and tot(r['a1']) == tot(r['score']))
    # B: 若 Top1 不满足下限，则用次锚/下一个满足下限的候选替换
    aB = 0
    for r in g:
        cand = [r['a1'], r['a2'], r.get('a3')]
        cand = [c for c in cand if c and tot(c) is not None]
        pick = None
        for c in cand:
            if tot(c) >= need:
                pick = c; break
        if pick is None and cand:
            pick = cand[0]
        if pick and tot(pick) == tot(r['score']):
            aB += 1
    print('%-12s %6d %9d %9d %+10d' % ('%.2f-%.2f' % (lo, hi), len(g), aA, aB, aB-aA))

print('\n' + '='*100)
print('全档合计')
print('='*100)
gA = sum(1 for r in rows if tot(r['a1']) is not None and tot(r['a1']) == tot(r['score']))
gB = 0
for r in rows:
    lo = r['o25']
    need = 3 if lo < 1.70 else (2 if lo < 1.90 else 0)
    cand = [c for c in [r['a1'], r['a2'], r.get('a3')] if c and tot(c) is not None]
    pick = None
    for c in cand:
        if tot(c) >= need:
            pick = c; break
    if pick is None and cand:
        pick = cand[0]
    if pick and tot(pick) == tot(r['score']):
        gB += 1
print('照搬 Top1          : %d/%d = %.1f%%' % (gA, len(rows), 100.0*gA/len(rows)))
print('按档位下限抬高      : %d/%d = %.1f%%' % (gB, len(rows), 100.0*gB/len(rows)))
print('差 %+d 场 (%.1fpp)' % (gB-gA, 100.0*(gB-gA)/len(rows)))
