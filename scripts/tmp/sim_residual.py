#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sim_residual.py — 最后的翻盘尝试：把「市场已经定价的部分」减掉，只检索残差

思路
  前三轮 KNN 输给市场，很可能因为特征里最大方差就是「谁热门」——KNN 实际上在
  重算市场已经算过的东西。若把「市场隐含概率」作为基线减掉，只在**残差空间**
  （形态偏离市场预期的那部分）检索，才可能看到正交信息。

  实现：目标 = 实际赛果（0/1/2）对应的「市场是否猜错」→ 残差二分类
       label = 1 若 实际方向 ≠ 市场热门方向
  特征：把所有 level 特征替换成「偏离市场热门」的形态量（不含市场概率本身）
"""
import json
import os
import sys

import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sim_features as SF      # noqa: E402
import sim_backtest as SB      # noqa: E402

OUT = os.path.join(SF.ROOT, 'data', 'tmp', 'sim_residual.json')


def residual_cols():
    return (SB.GROUPS['shift'] + SB.GROUPS['shape'] + SB.GROUPS['asian']
            + SB.GROUPS['cross'] + ['ah_depth', 'ah_moves'])


def auc(score, label):
    score, label = np.asarray(score, float), np.asarray(label, int)
    pos, neg = score[label == 1], score[label == 0]
    if not len(pos) or not len(neg):
        return 0.5
    return float(((pos[:, None] > neg[None, :]).sum()
                  + 0.5 * (pos[:, None] == neg[None, :]).sum()) / (len(pos) * len(neg)))


def main():
    samples, _ = SF.collect_corpus()
    H = 6.0
    cols = residual_cols()
    X, y, keep, mkt = SB.build(samples, H, SB.GROUPS['level'] + cols)
    # 只取形态列
    idx = [SB.GROUPS['level'].__len__() + i for i in range(len(cols))]
    Xr = X[:, idx]
    ko = np.array([s['ko'].timestamp() for s in keep])
    order = np.argsort(ko)

    upset = np.array([1 if y[i] != mkt[i] else 0 for i in range(len(y))])
    print('样本', len(y), ' 市场猜错率 %.1f%%' % (upset.mean() * 100))

    ps, ys2 = [], []
    for i in order:
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
        ys2.append(int(upset[i]))
    ps, ys2 = np.array(ps), np.array(ys2)
    print('可评估', len(ps))
    print()
    a = auc(ps, ys2)
    print('残差 AUC = %.3f  (0.5=无信息)' % a)
    # top/bottom decile 对比
    q = np.quantile(ps, [0.2, 0.8])
    lo = ys2[ps <= q[0]].mean() * 100
    hi = ys2[ps >= q[1]].mean() * 100
    print('KNN 残差最低 20%%: 市场猜错率 %.1f%%  最高 20%%: %.1f%%  (全样本 %.1f%%)' % (
        lo, hi, ys2.mean() * 100))
    print('→ 差距 %+.1fpp' % (hi - lo))

    json.dump(dict(n=int(len(ps)), auc=float(a), lo=float(lo), hi=float(hi),
                   base=float(ys2.mean() * 100)),
              open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('\n→', OUT)


if __name__ == '__main__':
    main()
