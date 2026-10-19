#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sim_probe3.py — 相似性之外的三条「想象力支路」严格检验

上面已证伪：朴素 KNN 方向判定全面输给市场（Brier 0.585 vs 0.536，分歧子集更差）。
本脚本改测三个**真正可能产生增量**的角度，全部严格时间分割：

  A. 覆盖增量：市场 top2 ∪ KNN top2 是否提高「2 向覆盖」命中（项目主口径 direction_hit_any）
  B. 条件边：给定「变动形态」条件，某一方向的实际胜率是否显著偏离市场定价（二项检验）
  C. 校准残差：在高相似度邻域内，市场隐含概率与实现频率是否存在系统性偏差

输出: data/tmp/sim_probe3.json
"""
import json
import math
import os
import sys

import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sim_features as SF       # noqa: E402
import sim_backtest as SB       # noqa: E402

OUT = os.path.join(SF.ROOT, 'data', 'tmp', 'sim_probe3.json')
COLS = SB.GROUPS['level'] + SB.GROUPS['shift'] + SB.GROUPS['asian']


def rolling(horizon=6.0, k=25, min_train=80):
    samples, _ = SF.collect_corpus()
    X, y, keep, mkt = SB.build(samples, horizon, COLS)
    ko = np.array([s['ko'].timestamp() for s in keep])
    order = np.argsort(ko)
    recs = []
    for i in order:
        tr = np.where(ko < ko[i] - 1e-6)[0]
        if len(tr) < min_train:
            continue
        mu, sd = SB.fit_stats(X[tr])
        Xtr = (np.where(np.isnan(X[tr]), mu, X[tr]) - mu) / sd
        xte = (np.where(np.isnan(X[i]), mu, X[i]) - mu) / sd
        p = SB.knn_proba(Xtr, y[tr], xte, k=k)
        F = SF.features(SF.truncate(keep[i]['series'], horizon))
        v = np.array([F.get('lvl_h', np.nan), F.get('lvl_d', np.nan), F.get('lvl_a', np.nan)])
        mk = v / v.sum() if not np.isnan(v).any() else np.array([1/3]*3)
        recs.append(dict(i=int(i), y=int(y[i]), p=p, mkt=mk, fav=int(mkt[i]),
                         league=keep[i]['league'], name=keep[i]['name'], ko=keep[i]['ko'],
                         F=F, act=keep[i]['act'], score=keep[i].get('score')))
    return recs


def binom_p(k, n, p0):
    """单侧二项检验 p 值（H1: 真实 > p0）"""
    if n == 0:
        return 1.0
    # 正态近似（n>=30 足够）
    if n < 30:
        return None
    se = math.sqrt(p0 * (1 - p0) / n)
    z = (k / n - p0) / se if se > 0 else 0
    return 0.5 * math.erfc(z / math.sqrt(2))


def main():
    res = {}
    recs = rolling(6.0, k=25)
    n = len(recs)
    print('可评估场次', n)

    # ── A. 覆盖增量 ──
    def any2(v):
        t2 = np.argsort(-v)[:2]
        return t2
    hit_m = hit_k = hit_u = 0
    need3 = 0
    for r in recs:
        t2m = any2(r['mkt'])
        t2k = any2(r['p'])
        if r['y'] in t2m:
            hit_m += 1
        if r['y'] in t2k:
            hit_k += 1
        # 并集策略：优先市场 top2，若 KNN top1 不在市场 top2 中则用三向
        if r['y'] in t2m:
            hit_u += 1
        else:
            need3 += 1
            if r['y'] in t2k:
                hit_u += 1
    print('\n[A] 2 向覆盖（direction_hit_any 口径）')
    print('  市场 top2        %.1f%%' % (hit_m / n * 100))
    print('  KNN  top2        %.1f%%' % (hit_k / n * 100))
    print('  并集(市场top2 + KNN补第3)  %.1f%%   需扩到第3向的场次 %d/%d (%.0f%%)' % (
        hit_u / n * 100, need3, n, need3 / n * 100))
    res['A'] = dict(market_top2=hit_m / n, knn_top2=hit_k / n,
                    union_with_3rd=hit_u / n, need_3rd=need3, n=n)

    # ── B. 条件边（变动形态 → 方向胜率 vs 市场定价）──
    print('\n[B] 条件边检验（收益=实际胜率 − 市场隐含概率）')
    conds = {
        '主赔走低 dr6_h>+1pp':      lambda F: F.get('dr6_h', 0) > 1.0,
        '主赔走高 dr6_h<-1pp':      lambda F: F.get('dr6_h', 0) < -1.0,
        '客赔走低 dr6_a<-1pp':      lambda F: F.get('dr6_a', 0) < -1.0,
        '客赔走高 dr6_a>+1pp':      lambda F: F.get('dr6_a', 0) > 1.0,
        '盘口加深 ah_line_d<0':     lambda F: F.get('ah_line_d', 0) < -1e-9,
        '盘口变浅 ah_line_d>0':     lambda F: F.get('ah_line_d', 0) > 1e-9,
        '主赔降但盘口未深(剪刀差)': lambda F: F.get('dr6_h', 0) > 1.0 and F.get('ah_line_d', 0) >= -1e-9,
        '主赔升但盘口加深(逆)':     lambda F: F.get('dr6_h', 0) < -1.0 and F.get('ah_line_d', 0) < -1e-9,
        '欧亚背离 |x|>8pp':         lambda F: abs(F.get('x_eu_ah', 0)) > 8,
        '低水 ah_p_last<45%':       lambda F: F.get('ah_p_last', 50) < 45,
    }
    rows = []
    for nm, fn in conds.items():
        sub = [r for r in recs if fn(r['F'])]
        if len(sub) < 25:
            rows.append((nm, len(sub), None, None, None, None, None))
            continue
        best = None
        for cls, lab in ((0, '主'), (1, '平'), (2, '客')):
            k = sum(1 for r in sub if r['y'] == cls)
            p0 = float(np.mean([r['mkt'][cls] for r in sub]))
            act = k / len(sub)
            edge = act - p0
            pv = binom_p(k, len(sub), p0)
            rec = (lab, act * 100, p0 * 100, edge * 100, pv)
            if best is None or (edge is not None and rec[3] > best[3]):
                best = rec
        rows.append((nm, len(sub)) + best)
        print('  %-24s n=%-3d 最优向=%s 实际%5.1f%% 市场%5.1f%% 边际%+5.1fpp p=%s' % (
            nm, len(sub), best[0], best[1], best[2], best[3],
            ('%.4f' % best[4]) if best[4] is not None else 'n/a'))
    res['B'] = [dict(cond=r[0], n=r[1], side=r[2], actual=r[3], market=r[4],
                     edge=r[5], p=(r[6] if len(r) > 6 else None)) for r in rows]

    # ── C. 校准残差：高相似度邻域 ──
    print('\n[C] 校准残差（市场 vs 实现，按市场热门概率分档）')
    rowsC = []
    for lo, hi in ((0, .45), (.45, .55), (.55, .65), (.65, 1.01)):
        sub = [r for r in recs if lo <= max(r['mkt']) < hi]
        if len(sub) < 20:
            continue
        favp = float(np.mean([max(r['mkt']) for r in sub]))
        real = float(np.mean([1 if r['fav'] == r['y'] else 0 for r in sub]))
        rowsC.append((lo, hi, len(sub), favp, real))
        print('  热门P∈[%.2f,%.2f) n=%-3d 市场均值%.1f%%  实际%.1f%%  残差%+.1fpp' % (
            lo, hi, len(sub), favp * 100, real * 100, (real - favp) * 100))
    res['C'] = [dict(lo=r[0], hi=r[1], n=r[2], market=r[3], actual=r[4]) for r in rowsC]

    json.dump(res, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('\n→', OUT)


if __name__ == '__main__':
    main()
