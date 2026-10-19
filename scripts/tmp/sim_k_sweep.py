#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sim_k_sweep.py — 决定性的参数稳健性：换 k、换邻域、换权重，结论会不会翻

如果 KNN 只在某一个 k 上打平市场，那是过拟合；如果所有 k 都输，结论才可信。
顺带检查「距离加权 vs 等权」「特征标准化 vs 不标准化」。
"""
import json
import os
import sys

import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sim_features as SF      # noqa: E402
import sim_backtest as SB      # noqa: E402

OUT = os.path.join(SF.ROOT, 'data', 'tmp', 'sim_k_sweep.json')
COLS = SB.GROUPS['level'] + SB.GROUPS['shift'] + SB.GROUPS['asian']
H = 6.0


def run(k=25, weighted=True, scale=True, min_train=60):
    samples, _ = SF.collect_corpus()
    X, y, keep, mkt = SB.build(samples, H, COLS)
    ko = np.array([s['ko'].timestamp() for s in keep])
    probs, ys = [], []
    for i in np.argsort(ko):
        tr = np.where(ko < ko[i] - 1e-6)[0]
        if len(tr) < min_train:
            continue
        if scale:
            mu, sd = SB.fit_stats(X[tr])
            Xtr = (np.where(np.isnan(X[tr]), mu, X[tr]) - mu) / sd
            xte = (np.where(np.isnan(X[i]), mu, X[i]) - mu) / sd
        else:
            Xtr = np.nan_to_num(X[tr])
            xte = np.nan_to_num(X[i])
        d = np.sqrt(((Xtr - xte) ** 2).sum(axis=1))
        sel = np.argsort(d)[:k]
        w = 1.0 / (d[sel] + 1e-6) if weighted else np.ones(len(sel))
        p = np.zeros(3)
        for j, yi in enumerate(y[tr][sel]):
            p[yi] += w[j]
        probs.append(p / p.sum())
        ys.append(int(y[i]))
    probs, ys = np.array(probs), np.array(ys)
    oh = np.zeros((len(ys), 3))
    oh[np.arange(len(ys)), ys] = 1
    return dict(k=k, weighted=weighted, scale=scale, n=len(ys),
                top1=float((probs.argmax(1) == ys).mean()),
                brier=float(((probs - oh) ** 2).sum(1).mean()))


def main():
    print('=== KNN 参数稳健性（若全部劣于市场，说明不是调参问题）===')
    res = []
    for k in (5, 10, 15, 25, 40, 60):
        for w in (True, False):
            r = run(k=k, weighted=w)
            res.append(r)
            print('  k=%-3d 加权=%-5s  n=%-3d  top1=%.1f%%  Brier=%.4f' % (
                r['k'], r['weighted'], r['n'], r['top1'] * 100, r['brier']))
    r = run(k=25, weighted=True, scale=False)
    res.append(r)
    print('  k=25  不标准化  n=%d  top1=%.1f%%  Brier=%.4f' % (r['n'], r['top1'] * 100, r['brier']))

    best = min(res, key=lambda x: x['brier'])
    print('\n  最优 Brier = %.4f（k=%d, 加权=%s）' % (best['brier'], best['k'], best['weighted']))
    print('  市场 Brier ≈ 0.5359（见 sim_blend）→ 差距 %+.4f' % (best['brier'] - 0.5359))
    json.dump(res, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
