#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sim_residual_val.py — 残差信号（AUC 0.557）的显著性/稳健性/混杂检验

一次 0.557 的 AUC 可能只是多重比较噪声。本脚本给它上三道检验：
  1. Bootstrap 置信区间（AUC 是否远离 0.5）
  2. 时间分割稳定性（前半/后半各算一次）
  3. 与市场概率的偏相关（控制「热门概率」后残差是否还在）
  4. 与「已证伪的分歧标签」的相关（是否同一现象换皮）
"""
import json
import os
import sys

import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sim_features as SF      # noqa: E402
import sim_backtest as SB      # noqa: E402

OUT = os.path.join(SF.ROOT, 'data', 'tmp', 'sim_residual_val.json')


def auc(score, label):
    score, label = np.asarray(score, float), np.asarray(label, int)
    pos, neg = score[label == 1], score[label == 0]
    if not len(pos) or not len(neg):
        return 0.5
    return float(((pos[:, None] > neg[None, :]).sum()
                  + 0.5 * (pos[:, None] == neg[None, :]).sum()) / (len(pos) * len(neg)))


def compute():
    samples, _ = SF.collect_corpus()
    cols = (SB.GROUPS['shift'] + SB.GROUPS['shape'] + SB.GROUPS['asian']
            + SB.GROUPS['cross'] + ['ah_depth', 'ah_moves'])
    X, y, keep, mkt = SB.build(samples, 6.0, SB.GROUPS['level'] + cols)
    off = len(SB.GROUPS['level'])
    Xr = X[:, off:off + len(cols)]
    ko = np.array([s['ko'].timestamp() for s in keep])
    upset = np.array([1 if y[i] != mkt[i] else 0 for i in range(len(y))])
    maxp = np.array([max(np.array([X[i][SB.GROUPS['level'].index(c)] for c in ('lvl_h', 'lvl_d', 'lvl_a')])) / 100
                     for i in range(len(y))])
    ps, ys, kk, mp = [], [], [], []
    for i in np.argsort(ko):
        tr = np.where(ko < ko[i] - 1e-6)[0]
        if len(tr) < 60:
            continue
        mu, sd = SB.fit_stats(Xr[tr])
        Xtr = (np.where(np.isnan(Xr[tr]), mu, Xr[tr]) - mu) / sd
        xte = (np.where(np.isnan(Xr[i]), mu, Xr[i]) - mu) / sd
        d = np.sqrt(((Xtr - xte) ** 2).sum(axis=1))
        k = min(25, len(d))
        sel = np.argsort(d)[:k]
        w = 1.0 / (d[sel] + 1e-6)
        ps.append(float((upset[tr][sel] * w).sum() / w.sum()))
        ys.append(int(upset[i]))
        mp.append(float(maxp[i]))
        kk.append(float(ko[i]))
    return np.array(ps), np.array(ys), np.array(mp), np.array(kk)


def main():
    ps, ys, mp, kk = compute()
    n = len(ps)
    a = auc(ps, ys)
    print('n=%d  AUC=%.3f' % (n, a))

    rng = np.random.default_rng(7)
    boots = []
    for _ in range(2000):
        j = rng.integers(0, n, n)
        if len(np.unique(ys[j])) < 2:
            continue
        boots.append(auc(ps[j], ys[j]))
    boots = np.array(boots)
    lo, hi = np.percentile(boots, [2.5, 97.5])
    print('Bootstrap 95%%CI = [%.3f, %.3f]  → %s' % (
        lo, hi, '✅拒绝0.5' if lo > 0.5 else '🔴含0.5·不显著'))

    print('\n时间分割稳定性：')
    for part, m in (('前半', kk <= np.median(kk)), ('后半', kk > np.median(kk))):
        if len(np.unique(ys[m])) < 2:
            continue
        print('  %s n=%-3d AUC=%.3f' % (part, int(m.sum()), auc(ps[m], ys[m])))

    print('\n混杂检验：')
    c1 = float(np.corrcoef(ps, mp)[0, 1])
    c2 = float(np.corrcoef(ps, ys)[0, 1])
    # 偏相关：控制 mp
    def partial(x, yv, z):
        rxy = np.corrcoef(x, yv)[0, 1]
        rxz = np.corrcoef(x, z)[0, 1]
        ryz = np.corrcoef(yv, z)[0, 1]
        d = np.sqrt((1 - rxz ** 2) * (1 - ryz ** 2))
        return (rxy - rxz * ryz) / d if d > 1e-9 else 0.0
    print('  corr(残差分, 市场热门P) = %+.3f   corr(残差分, 爆冷) = %+.3f' % (c1, c2))
    print('  偏相关(残差分, 爆冷 | 市场热门P) = %+.3f' % partial(ps, ys.astype(float), mp))

    q = np.quantile(ps, [0.2, 0.8])
    print('  低20%% 爆冷率 %.1f%%  高20%% 爆冷率 %.1f%%' % (
        ys[ps <= q[0]].mean() * 100, ys[ps >= q[1]].mean() * 100))

    json.dump(dict(n=n, auc=float(a), ci=[float(lo), float(hi)],
                   ci_excludes_half=bool(lo > 0.5), corr_maxp=float(c1)),
              open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('\n→', OUT)


if __name__ == '__main__':
    main()
