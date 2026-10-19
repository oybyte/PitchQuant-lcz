#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sim_steam.py — 不走 KNN，直接测三条最经典的「盘口变化」假设

KNN 已全面证伪，但那是「找相似」这条路。变化趋势本身可能是更直接的信息源。
本脚本直接检验，不经过任何相似性模型：

  S1 蒸汽流(steam)：收盘相对开盘的隐含概率变动，是否预测方向（超越收盘价本身）
  S2 反转(reversal)：先大幅移动再部分回撤，是否比单向移动更可信
  S3 早/晚节奏(timing)：变动集中在早盘 vs 临场，命中率是否不同

每个假设都用「实际 − 收盘市场隐含」的边际做量纲，并给二项检验。
"""
import json
import math
import os
import sys

import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sim_features as SF      # noqa: E402

OUT = os.path.join(SF.ROOT, 'data', 'tmp', 'sim_steam.json')
H = 6.0
LAB = {0: '主胜', 1: '平局', 2: '客胜'}


def binom_p(k, n, p0):
    if n < 20:
        return None
    se = math.sqrt(max(p0 * (1 - p0), 1e-9) / n)
    z = (k / n - p0) / se
    return 0.5 * math.erfc(z / math.sqrt(2))


def main():
    samples, _ = SF.collect_corpus()
    rows = []
    for s in samples:
        F = SF.features(SF.truncate(s['series'], H))
        if 'lvl_h' not in F or 'dr_h' not in F:
            continue
        p = np.array([F['lvl_h'], F['lvl_d'], F['lvl_a']]) / 100.0
        rows.append(dict(y=s['label'], p=p, F=F, act=s['act']))
    print('样本', len(rows), '\n')

    def report(name, sel_fn, side_fn):
        sub = [r for r in rows if sel_fn(r)]
        if len(sub) < 20:
            print('  %-38s n=%-3d (样本不足)' % (name, len(sub)))
            return None
        side = side_fn()
        k = sum(1 for r in sub if r['y'] == side)
        p0 = float(np.mean([r['p'][side] for r in sub]))
        act = k / len(sub)
        edge = (act - p0) * 100
        pv = binom_p(k, len(sub), p0)
        print('  %-38s n=%-3d 押%s 实际%5.1f%% 市场%5.1f%% 边际%+5.1fpp p=%.3f' % (
            name, len(sub), LAB[side], act * 100, p0 * 100, edge,
            pv if pv is not None else float('nan')))
        return dict(name=name, n=len(sub), side=LAB[side], actual=act * 100,
                    market=p0 * 100, edge=edge, p=pv)

    print('=== S1 蒸汽流：收盘相对开盘的主队隐含变动 ===')
    out = []
    for th in (1.0, 2.0, 3.0):
        out.append(report('主队隐含升 %.0fpp 以上 → 押主' % th,
                          lambda r, t=th: r['F']['dr_h'] >= t, lambda: 0))
        out.append(report('主队隐含降 %.0fpp 以上 → 押客' % th,
                          lambda r, t=th: r['F']['dr_h'] <= -t, lambda: 2))

    print('\n=== S2 反转形态：单边性低（来回拉锯）vs 高（单边碾压）===')
    for lo, hi, nm in ((-1.01, -0.4, '强反转(eff<-0.4)'),
                       (-0.4, 0.4, '震荡(|eff|<0.4)'),
                       (0.4, 1.01, '强单边(eff>0.4)')):
        report('%s → 押市场热门' % nm,
               lambda r, a=lo, b=hi: a <= r['F'].get('sh_h_eff', 0) / 100 < b
               if r['F'].get('sh_h_eff') is not None else False,
               lambda: 0)

    print('\n=== S3 节奏：变动重心在早盘 vs 临场 ===')
    for lo, hi, nm in ((0, 0.35, '早盘集中(tc<0.35)'), (0.65, 1.01, '临场集中(tc>0.65)')):
        report('%s → 押主队' % nm,
               lambda r, a=lo, b=hi: a <= r['F'].get('sh_h_tc', -1) / 100 < b,
               lambda: 0)

    print('\n=== S4 波动：路径波动大是否= 方向更不可测（押热门会否更差）===')
    vols = np.array([r['F'].get('sh_h_vol', 0) for r in rows])
    if vols.std() > 0:
        cut = np.median(vols)
        for nm, m in (('低波动', vols <= cut), ('高波动', vols > cut)):
            sub = [r for i, r in enumerate(rows) if m[i]]
            if len(sub) < 20:
                continue
            fav = [int(np.argmax(r['p'])) for r in sub]
            k = sum(1 for j, r in enumerate(sub) if r['y'] == fav[j])
            p0 = float(np.mean([r['p'][fav[j]] for j, r in enumerate(sub)]))
            print('  %-38s n=%-3d 市场热门命中%5.1f%% 市场均值%5.1f%% 边际%+5.1fpp' % (
                nm, len(sub), k / len(sub) * 100, p0 * 100, (k / len(sub) - p0) * 100))

    json.dump([x for x in out if x], open(OUT, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('\n→', OUT)


if __name__ == '__main__':
    main()
