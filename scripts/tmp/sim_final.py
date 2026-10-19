#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sim_final.py — 对 S1(蒸汽流) 与 S4(波动) 两个「边缘发现」做决定性检验

它们是目前唯一 p 值在 0.1 附近的东西，必须回答三个问题：
  ① 时间分割稳定吗（前后半段符号一致？）
  ② 是不是混杂（高波动场是否本身就是强热门场 → 边际只是「热门更准」的换皮）
  ③ 落在项目已认知的哪个规则上（是否与 skew / 单押准入重复）
"""
import json
import math
import os
import sys

import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sim_features as SF      # noqa: E402

OUT = os.path.join(SF.ROOT, 'data', 'tmp', 'sim_final.json')
H = 6.0


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - r) / d, (c + r) / d)


def main():
    samples, _ = SF.collect_corpus()
    rows = []
    for s in samples:
        F = SF.features(SF.truncate(s['series'], H))
        if 'lvl_h' not in F or 'dr_h' not in F:
            continue
        p = np.array([F['lvl_h'], F['lvl_d'], F['lvl_a']]) / 100.0
        rows.append(dict(y=s['label'], p=p, F=F, ko=s['ko']))
    n = len(rows)
    print('样本', n)
    res = {}

    # ── S4 波动 ──
    vol = np.array([r['F'].get('sh_h_vol', 0) for r in rows])
    fav = np.array([int(r['p'].argmax()) for r in rows])
    hit = np.array([1 if r['y'] == fav[i] else 0 for i, r in enumerate(rows)])
    maxp = np.array([r['p'].max() for r in rows])
    med = np.median(vol)

    print('\n=== S4 波动 (median=%.2f) ===' % med)
    print('  混杂检查：高波动组的市场热门概率是否本就更高？')
    hi = vol > med
    print('    高波动组 市场热门均值 %.1f%%   低波动组 %.1f%%  → 差 %+.1fpp' % (
        maxp[hi].mean() * 100, maxp[~hi].mean() * 100, (maxp[hi].mean() - maxp[~hi].mean()) * 100))

    print('  分层检验（同市场概率档内比 高/低波动 的命中率）：')
    for lo, hi2 in ((0, .45), (.45, .55), (.55, .70), (.70, 1.01)):
        m = (maxp >= lo) & (maxp < hi2)
        if m.sum() < 25:
            continue
        a, b = m & (vol > med), m & (vol <= med)
        if a.sum() < 8 or b.sum() < 8:
            continue
        print('    热门P∈[%.2f,%.2f)  高波动 n=%-3d %5.1f%%   低波动 n=%-3d %5.1f%%   差 %+.1fpp' % (
            lo, hi2, int(a.sum()), hit[a].mean() * 100, int(b.sum()), hit[b].mean() * 100,
            (hit[a].mean() - hit[b].mean()) * 100))

    print('  时间分割：')
    ko = np.array([r['ko'].timestamp() for r in rows])
    for part, m in (('前半', ko <= np.median(ko)), ('后半', ko > np.median(ko))):
        a, b = m & (vol > med), m & (vol <= med)
        print('    %s  高波动 n=%-3d %5.1f%%   低波动 n=%-3d %5.1f%%' % (
            part, int(a.sum()), hit[a].mean() * 100, int(b.sum()), hit[b].mean() * 100))

    # ── S1 蒸汽流 ──
    print('\n=== S1 蒸汽流：主队隐含升 ≥2pp → 押主 ===')
    dr = np.array([r['F']['dr_h'] for r in rows])
    sel = dr >= 2.0
    p0 = np.array([r['p'][0] for r in rows])
    k = int(((np.array([r['y'] for r in rows]) == 0) & sel).sum())
    nsel = int(sel.sum())
    act = k / nsel
    exp = p0[sel].mean()
    lo, hii = wilson(k, nsel)
    print('  n=%d  实际主胜率 %.1f%% [CI %.1f–%.1f]  市场隐含 %.1f%%  边际 %+.1fpp' % (
        nsel, act * 100, lo * 100, hii * 100, exp * 100, (act - exp) * 100))
    print('  市场隐含是否也落在 CI 内：%s' % ('✅ 是（无显著边际）' if lo <= exp <= hii else '🔴 否'))
    print('  时间分割：')
    for part, m in (('前半', ko <= np.median(ko)), ('后半', ko > np.median(ko))):
        s2 = m & sel
        if s2.sum() < 5:
            continue
        kk = int(((np.array([r['y'] for r in rows]) == 0) & s2).sum())
        print('    %s n=%-3d 主胜率 %5.1f%%  市场 %.1f%%  边际 %+.1fpp' % (
            part, int(s2.sum()), kk / s2.sum() * 100, p0[s2].mean() * 100,
            (kk / s2.sum() - p0[s2].mean()) * 100))

    json.dump(dict(n=n, vol_median=float(med)), open(OUT, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('\n→', OUT)


if __name__ == '__main__':
    main()
