#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sim_filter.py — 唯一正向发现的严格验证：「相似性分歧 = 低置信过滤器」

背景（已证伪的用法）
  · KNN 直接判方向：Brier 0.586 vs 市场 0.536 → 输
  · 融合扫描：最优 α=1.0（纯市场）→ 相似性零增量
  · 条件边：全部 p>0.2，不显著

待验证的用法（本脚本）
  相似性检索**不预测方向**，只回答「这场的盘口形态在历史里常见吗」。
  当 KNN 最近邻的多数方向 ≠ 市场热门方向时（分歧态），市场方向的历史命中率显著更低
  → 可作为**置信度降档器**（不改方向，只降档），符合项目「只调不反转」铁律。

严格性
  · 时间分割（只检索过去）
  · 二项检验 + Wilson 区间
  · 分年份/分联赛稳健性
  · 与「市场自身概率低」这一竞争解释做对比（区分增益是否只是市场不确定性的代理）
"""
import json
import math
import os
import sys

import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sim_features as SF      # noqa: E402
import sim_backtest as SB      # noqa: E402

OUT = os.path.join(SF.ROOT, 'data', 'tmp', 'sim_filter.json')
COLS = SB.GROUPS['level'] + SB.GROUPS['shift'] + SB.GROUPS['asian']


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - r) / d, (c + r) / d)


def binomial_two_sided(k1, n1, k2, n2):
    """两比例 z 检验"""
    if n1 == 0 or n2 == 0:
        return 1.0
    p1, p2 = k1 / n1, k2 / n2
    p = (k1 + k2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    if se == 0:
        return 1.0
    z = (p1 - p2) / se
    return math.erfc(abs(z) / math.sqrt(2))


def rolling(horizon=6.0, k=25, min_train=60):
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
        # 最近邻距离（越远=形态越罕见）
        d_all = np.sqrt(((Xtr - xte) ** 2).sum(axis=1))
        dmin = float(np.sort(d_all)[:k].mean())
        v = np.array([X[i][COLS.index(c)] for c in ('lvl_h', 'lvl_d', 'lvl_a')])
        s = v.sum()
        mk = v / s if s > 0 else np.array([1 / 3] * 3)
        recs.append(dict(y=int(y[i]), p=p, mkt=mk, fav=int(mk.argmax()),
                         knn_fav=int(p.argmax()), dmin=dmin,
                         league=keep[i]['league'], name=keep[i]['name'],
                         ko=keep[i]['ko'], total=keep[i].get('tot')))
    return recs


def main():
    res = {}
    recs = rolling(6.0, 25, 60)
    n = len(recs)
    print('可评估场次', n)

    def stat(sub, label):
        if not sub:
            return None
        k = sum(1 for r in sub if r['y'] == r['fav'])
        a = sum(1 for r in sub if r['y'] == r['knn_fav'])
        lo, hi = wilson(k, len(sub))
        return dict(label=label, n=len(sub), mkt_hit=k, mkt_rate=k / len(sub),
                    knn_hit=a, knn_rate=a / len(sub), ci=[lo, hi])

    agree = [r for r in recs if r['knn_fav'] == r['fav']]
    dis = [r for r in recs if r['knn_fav'] != r['fav']]
    A, D = stat(agree, '一致'), stat(dis, '分歧')

    print('\n=== 1. 分歧 vs 一致（市场方向命中率）===')
    for s in (A, D):
        print('  %-4s n=%-4d 市场命中 %-3d = %5.1f%%  [95%%CI %.1f–%.1f]   KNN自身 %5.1f%%' % (
            s['label'], s['n'], s['mkt_hit'], s['mkt_rate'] * 100,
            s['ci'][0] * 100, s['ci'][1] * 100, s['knn_rate'] * 100))
    pv = binomial_two_sided(A['mkt_hit'], A['n'], D['mkt_hit'], D['n'])
    print('  两比例检验 p = %.4f' % pv)
    res['split'] = dict(agree=A, disagree=D, p_value=pv)

    print('\n=== 2. 竞争解释：是不是「市场自己也没把握」的代理？===')
    # 分层：在相同市场热门概率区间内，比较一致/分歧
    for lo, hi in ((0, .45), (.45, .55), (.55, .70), (.70, 1.01)):
        a2 = [r for r in agree if lo <= max(r['mkt']) < hi]
        d2 = [r for r in dis if lo <= max(r['mkt']) < hi]
        if len(a2) < 10 and len(d2) < 10:
            continue
        ra = (sum(1 for r in a2 if r['y'] == r['fav']) / len(a2) * 100) if a2 else float('nan')
        rd = (sum(1 for r in d2 if r['y'] == r['fav']) / len(d2) * 100) if d2 else float('nan')
        print('  热门P∈[%.2f,%.2f)  一致 n=%-3d %5.1f%%   分歧 n=%-3d %5.1f%%   差 %+.1fpp' % (
            lo, hi, len(a2), ra, len(d2), rd, (rd - ra) if (a2 and d2) else float('nan')))
    res['stratified'] = True

    print('\n=== 3. 稳健性：按时间前后半段 ===')
    recs_sorted = sorted(recs, key=lambda r: r['ko'])
    half = len(recs_sorted) // 2
    for part, sub in (('前半', recs_sorted[:half]), ('后半', recs_sorted[half:])):
        a3 = [r for r in sub if r['knn_fav'] == r['fav']]
        d3 = [r for r in sub if r['knn_fav'] != r['fav']]
        ra = (sum(1 for r in a3 if r['y'] == r['fav']) / len(a3) * 100) if a3 else float('nan')
        rd = (sum(1 for r in d3 if r['y'] == r['fav']) / len(d3) * 100) if d3 else float('nan')
        print('  %s  一致 n=%-3d %5.1f%%   分歧 n=%-3d %5.1f%%' % (part, len(a3), ra, len(d3), rd))

    print('\n=== 4. 分歧态下「扩到第3向」能不能救 ===')
    if dis:
        t3 = np.array([np.argsort(-r['mkt'])[:3] for r in dis])
        hit3 = np.mean([r['y'] in t3[j] for j, r in enumerate(dis)]) * 100
        hit2 = np.mean([r['y'] in np.argsort(-r['mkt'])[:2] for r in dis]) * 100
        knn_in = np.mean([r['knn_fav'] in np.argsort(-r['mkt'])[:3] for r in dis]) * 100
        print('  分歧态 市场 top2 %.1f%% · 市场 top3 %.1f%% · KNN首选落在市场top3 的比例 %.1f%%' % (
            hit2, hit3, knn_in))
        res['disagree_3way'] = dict(top2=hit2, top3=hit3, knn_in_top3=knn_in, n=len(dis))

    json.dump(res, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1,
              default=str)
    print('\n→', OUT)


if __name__ == '__main__':
    main()
