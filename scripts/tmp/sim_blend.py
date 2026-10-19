#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sim_blend.py — 市场 × 相似性 融合的严格检验（决定 KNN 到底能不能用）

检验项
  1. 融合权重扫描 α：p = α·市场 + (1−α)·KNN，看最优 α 是否 = 1（=纯市场，即 KNN 无用）
  2. 公平 2 选对比：市场 top2 / KNN top2 / 融合 top2（direction_hit_any 口径）
  3. KNN 一致度作为「置信度调节」而非「方向来源」：一致度分档看市场命中率
"""
import json
import os
import sys

import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sim_features as SF      # noqa: E402
import sim_backtest as SB      # noqa: E402

OUT = os.path.join(SF.ROOT, 'data', 'tmp', 'sim_blend.json')
COLS = SB.GROUPS['level'] + SB.GROUPS['shift'] + SB.GROUPS['asian']


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
        v = np.array([X[i][COLS.index(c)] for c in ('lvl_h', 'lvl_d', 'lvl_a')])
        s = v.sum()
        mk = v / s if s > 0 else np.array([1/3]*3)
        recs.append(dict(y=int(y[i]), p=p, mkt=mk, fav=int(mk.argmax()),
                         league=keep[i]['league'], name=keep[i]['name'], ko=keep[i]['ko']))
    return recs


def metrics(arr_p, y):
    oh = np.zeros((len(y), 3))
    oh[np.arange(len(y)), y] = 1
    top1 = float((arr_p.argmax(1) == y).mean()) * 100
    t2 = np.argsort(-arr_p, axis=1)[:, :2]
    any2 = float(np.mean([y[i] in t2[i] for i in range(len(y))])) * 100
    return top1, any2, float(((arr_p - oh) ** 2).sum(1).mean())


def main():
    recs = rolling(6.0, 25, 60)
    y = np.array([r['y'] for r in recs])
    P = np.array([r['p'] for r in recs])
    M = np.array([r['mkt'] for r in recs])
    print('可评估场次', len(recs), '\n')

    print('=== 1. 融合权重扫描 p = α·市场 + (1−α)·KNN ===')
    best = None
    rows = []
    for a in (0.0, .2, .3, .4, .5, .6, .7, .8, .9, 1.0):
        mix = a * M + (1 - a) * P
        t1, a2, br = metrics(mix, y)
        rows.append(dict(alpha=a, top1=t1, any2=a2, brier=br))
        print('  α=%.1f  top1 %5.1f%%  any2 %5.1f%%  Brier %.4f' % (a, t1, a2, br))
        if best is None or br < best['brier']:
            best = rows[-1]
    print('  → Brier 最优 α = %.1f（α=1.0 表示纯市场；若最优接近 1 → 相似性无增量）' % best['alpha'])

    print('\n=== 2. 公平两组对比（2 选预算）===')
    t1m, a2m, brm = metrics(M, y)
    t1k, a2k, brk = metrics(P, y)
    print('  市场 top2 = %.1f%%   KNN top2 = %.1f%%   差 %+.1fpp' % (a2m, a2k, a2k - a2m))

    print('\n=== 3. KNN 一致度 → 市场命中率（置信度调节可用性）===')
    cons = []
    for r in recs:
        kf = int(r['p'].argmax())
        cons.append(1.0 if kf == r['fav'] else 0.0)
    cons = np.array(cons)
    for lo, hi, lab in ((0, .01, 'KNN 与市场分歧'), (0.99, 1.01, 'KNN 与市场一致')):
        m = (cons >= lo) & (cons <= hi)
        if m.sum() < 20:
            continue
        acc = float((M[m].argmax(1) == y[m]).mean()) * 100
        acck = float((P[m].argmax(1) == y[m]).mean()) * 100
        print('  %-16s n=%-3d 市场 top1 %.1f%%   KNN top1 %.1f%%' % (lab, int(m.sum()), acc, acck))

    print('\n=== 4. 市场概率分位 vs 实际（有无系统性偏差）===')
    for lo, hi in ((0, .45), (.45, .55), (.55, .65), (.65, 1.01)):
        m = (M.max(1) >= lo) & (M.max(1) < hi)
        if m.sum() < 20:
            continue
        print('  热门P∈[%.2f,%.2f) n=%-3d 市场 %.1f%%  实际 %.1f%%' % (
            lo, hi, int(m.sum()), M[m].max(1).mean() * 100,
            (M[m].argmax(1) == y[m]).mean() * 100))

    json.dump(dict(sweep=rows, best=best), open(OUT, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('\n→', OUT)


if __name__ == '__main__':
    main()
