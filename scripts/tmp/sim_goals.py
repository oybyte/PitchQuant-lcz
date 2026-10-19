#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sim_goals.py — 方向输了，总进球能不能赢？相似性在「量级」上的严格检验

对比
  基线 A  市场 O2.5 定价方向（用截断点 ou_line/ou_over 推）
  基线 B  全场均值常数
  模型 K  KNN 检索历史相似样本的场均总进球
指标: MAE / 与实际的相关系数 / 大小球 2.5 命中率
"""
import json
import os
import sys

import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sim_features as SF      # noqa: E402
import sim_backtest as SB      # noqa: E402

OUT = os.path.join(SF.ROOT, 'data', 'tmp', 'sim_goals.json')
COLS = SB.GROUPS['level'] + SB.GROUPS['shift'] + SB.GROUPS['total'] + SB.GROUPS['asian']


def main():
    samples, _ = SF.collect_corpus()
    H = 6.0
    rows, ys, tot, keep = [], [], [], []
    for s in samples:
        if s.get('tot') is None:
            continue
        F = SF.features(SF.truncate(s['series'], H))
        if 'lvl_h' not in F:
            continue
        rows.append([F.get(c, np.nan) for c in COLS])
        ys.append(s['label'])
        tot.append(float(s['tot']))
        keep.append(s)
    X = np.array(rows)
    y = np.array(ys)
    T = np.array(tot)
    ko = np.array([k['ko'].timestamp() for k in keep])
    print('样本', len(T), '  场均总进球 %.2f' % T.mean())

    order = np.argsort(ko)
    pred = np.full(len(T), np.nan)
    mkt_line = np.full(len(T), np.nan)
    for i in order:
        tr = np.where(ko < ko[i] - 1e-6)[0]
        if len(tr) < 60:
            continue
        mu, sd = SB.fit_stats(X[tr])
        Xtr = (np.where(np.isnan(X[tr]), mu, X[tr]) - mu) / sd
        xte = (np.where(np.isnan(X[i]), mu, X[i]) - mu) / sd
        d = np.sqrt(((Xtr - xte) ** 2).sum(axis=1))
        idx = np.argsort(d)[:30]
        w = 1.0 / (d[idx] + 1e-6)
        pred[i] = float((T[tr][idx] * w).sum() / w.sum())
        j = COLS.index('ou_line_last') if 'ou_line_last' in COLS else None
        if j is not None:
            mkt_line[i] = X[i][j]

    m = ~np.isnan(pred)
    print('可评估', m.sum())
    p, t = pred[m], T[m]
    ma = np.abs(p - t)
    base = np.abs(T[m].mean() - t)
    print()
    print('MAE    KNN %.3f  vs  常数均值 %.3f   → 改善 %+.3f' % (ma.mean(), base.mean(), base.mean() - ma.mean()))
    print('相关   KNN corr = %.3f' % np.corrcoef(p, t)[0, 1])
    # 大小球 2.5
    hit = ((p > 2.5) == (t > 2.5)).mean() * 100
    base_hit = ((T[m].mean() > 2.5) == (t > 2.5)).mean() * 100
    print('O2.5 命中 KNN %.1f%%  常数 %.1f%%' % (hit, base_hit))
    # 市场线方向
    ml = mkt_line[m]
    ok = ~np.isnan(ml)
    if ok.sum() > 30:
        mh = ((ml[ok] > 2.5) == (t[ok] > 2.5)).mean() * 100
        print('市场线 O2.5 命中 %.1f%%（n=%d）  常数 %.1f%%' % (
            mh, ok.sum(), ((T[m][ok].mean() > 2.5) == (t[ok] > 2.5)).mean() * 100))
        # 与 KNN 融合
        for a in (0.5, 0.7, 0.9):
            mix = a * ml[ok] + (1 - a) * p[ok]
            print('   融合 α=%.1f  MAE %.3f  命中 %.1f%%' % (
                a, np.abs(mix - t[ok]).mean(),
                ((mix > 2.5) == (t[ok] > 2.5)).mean() * 100))
        print('   纯市场线    MAE %.3f' % np.abs(ml[ok] - t[ok]).mean())
        print('   纯 KNN      MAE %.3f' % np.abs(p[ok] - t[ok]).mean())

    json.dump(dict(n=int(m.sum()), mae_knn=float(ma.mean()), mae_base=float(base.mean()),
                   corr=float(np.corrcoef(p, t)[0, 1]), o25_hit=float(hit)),
              open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('\n→', OUT)


if __name__ == '__main__':
    main()
