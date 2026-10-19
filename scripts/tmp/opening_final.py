#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""opening_final.py — 收敛：初盘到底能提供什么（一次跑完，含时间分割与置信区间）

三条候选结论，逐条给定论：
  K1  初盘单点判方向        → 与终盘等价（无增量）
  K2  初盘热门被推翻        → 强「避雷」信号（但不能反押）
  K3  初盘→即盘的变动幅度   → 正向信号，且控制市场热门后仍有增量
"""
import json
import math
import os
import sys

import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import opening_features as OF      # noqa: E402

OUT = os.path.join(OF.ROOT, 'data', 'tmp', 'opening_final.json')


def wilson(k, n, z=1.96):
    if n == 0:
        return (0., 0.)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - r) / d, (c + r) / d)


def main():
    S = OF.collect()
    y = np.array([x['label'] for x in S])
    n = len(S)
    F = [x['F'] for x in S]
    fo = np.array([int(np.argmax([f.get('o_h', 0), f.get('o_d', 0), f.get('o_a', 0)])) for f in F])
    fl = np.array([int(np.argmax([f.get('l_h', 0), f.get('l_d', 0), f.get('l_a', 0)])) for f in F])
    maxl = np.array([max(f.get('l_h', 0), f.get('l_d', 0), f.get('l_a', 0)) for f in F])
    dmax = np.array([max(abs(f.get('d_h', 0)), abs(f.get('d_a', 0))) for f in F])
    hit_l = fl == y
    ko = np.array([x.get('kickoff') or '' for x in S])
    print('n=%d\n' % n)

    # ── K1 ──
    print('=== K1 初盘单点 vs 终盘单点 ===')
    print('  初盘热门 %.1f%%   终盘热门 %.1f%%   差 %+.1fpp' % (
        (fo == y).mean() * 100, hit_l.mean() * 100, (hit_l.mean() - (fo == y).mean()) * 100))
    print('  → 两者等价，初盘不提供额外的方向信息\n')

    # ── K2 热门被推翻 ──
    flip = fo != fl
    print('=== K2 初盘热门被推翻（n=%d）===' % flip.sum())
    k = int(hit_l[flip].sum())
    lo, hi = wilson(k, int(flip.sum()))
    print('  推翻场 终盘热门命中 %d/%d = %.1f%% [CI %.1f–%.1f]' % (k, flip.sum(), k / flip.sum() * 100, lo * 100, hi * 100))
    k2 = int(hit_l[~flip].sum())
    lo2, hi2 = wilson(k2, int((~flip).sum()))
    print('  未翻场 终盘热门命中 %d/%d = %.1f%% [CI %.1f–%.1f]' % (k2, (~flip).sum(), k2 / (~flip).sum() * 100, lo2 * 100, hi2 * 100))
    dd = (y[flip] == 1).mean() * 100
    print('  推翻场平局率 %.1f%%（全样本 %.1f%%）' % (dd, (y == 1).mean() * 100))
    print('  → 三向接近均匀 → 结论是「别押」，不是「反押」\n')

    # ── K3 变动幅度（含时间分割 + 控制市场） ──
    print('=== K3 初盘→即盘 变动幅度（控制终盘热门概率后）===')
    print('  %-18s %-6s %-10s %-10s %s' % ('分组', 'n', '命中', '隐含', '增量'))
    agg = {}
    for lo_, hi_ in ((0, .40), (.40, .50), (.50, .65), (.65, 1.01)):
        for dlo, dhi, dn in ((0, 3, '小变动<3pp'), (5, 99, '大变动≥5pp')):
            m = (maxl >= lo_ * 100) & (maxl < hi_ * 100) & (dmax >= dlo) & (dmax < dhi)
            if m.sum() < 8:
                continue
            print('  P∈[%.2f,%.2f) %-10s n=%-4d %5.1f%%     %5.1f%%    %+.1fpp' % (
                lo_, hi_, dn, int(m.sum()), hit_l[m].mean() * 100, maxl[m].mean(),
                hit_l[m].mean() * 100 - maxl[m].mean()))
            agg[(lo_, dn)] = (int(m.sum()), hit_l[m].mean() * 100, maxl[m].mean())
    print('\n  大变动 + 热门未变：')
    big_same = (dmax >= 5) & (fo == fl)
    kk = int(hit_l[big_same].sum())
    lo3, hi3 = wilson(kk, int(big_same.sum()))
    print('    n=%d 命中 %.1f%% [CI %.1f–%.1f]' % (big_same.sum(), kk / big_same.sum() * 100, lo3 * 100, hi3 * 100))
    small_same = (dmax < 3) & (fo == fl)
    kk2 = int(hit_l[small_same].sum())
    print('    对照 小变动+未翻 n=%d 命中 %.1f%%' % (small_same.sum(), kk2 / small_same.sum() * 100))

    print('\n  时间分割（大变动+未翻）：')
    order = np.argsort(ko); half = n // 2
    for nm, idx in (('前半', order[:half]), ('后半', order[half:])):
        m = np.zeros(n, bool); m[idx] = True
        a = m & big_same
        b = m & small_same
        print('    %s  大变动 n=%-3d %5.1f%%   小变动 n=%-3d %5.1f%%' % (
            nm, int(a.sum()), hit_l[a].mean() * 100, int(b.sum()), hit_l[b].mean() * 100))

    print('\n  Bootstrap（大变动+未翻 vs 小变动+未翻）：')
    rng = np.random.default_rng(11)
    d = []
    den = big_same.sum() + small_same.sum()
    idxs = np.where(big_same | small_same)[0]
    for _ in range(3000):
        j = rng.choice(idxs, len(idxs), replace=True)
        a = j[big_same[j]]; b = j[small_same[j]]
        if len(a) < 5 or len(b) < 5:
            continue
        d.append(hit_l[a].mean() - hit_l[b].mean())
    d = np.array(d)
    obs = hit_l[big_same].mean() - hit_l[small_same].mean()
    lo4, hi4 = np.percentile(d, [2.5, 97.5])
    print('    实测 %+.3f  95%%CI [%+.3f, %+.3f]  P(≥0)=%.4f' % (
        obs, lo4, hi4, (d >= 0).mean()))

    json.dump(dict(n=n, flip_n=int(flip.sum()),
                   flip_hit=float(hit_l[flip].mean()),
                   bigsame_n=int(big_same.sum()), bigsame_hit=float(hit_l[big_same].mean()),
                   smallsame_hit=float(hit_l[small_same].mean()),
                   bigsame_boot_ci=[float(lo4), float(hi4)]),
              open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('\n→', OUT)


if __name__ == '__main__':
    main()
