#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""opening_calib.py — 真·初盘的真正价值：**校准**，不是方向

上一轮已确认
  · 初盘热门命中 58.5% ≈ 终盘热门 58.5% → 初盘在「判方向」上没有额外信息
  · 「亚盘深度 vs 欧赔隐含」等看起来很强的分组，多为盘口深度的机械产物（已证伪）

但要回答「初盘能否判定」还差一步：**给定初盘定价，实际赛果是否系统性偏离？**
如果有稳定的、跨档单调的偏离，那就是真信号（市场在初盘阶段定价不足/过度）。

做法
  按初盘隐含概率分箱，算每箱的实际频率，做可靠性曲线 + 拟合校准斜率。
  再用**时间分割**验证斜率是否稳定。
  最后给出可直接使用的「初盘 → 校准后概率」映射表。
"""
import json
import math
import os
import sys

import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import opening_features as OF      # noqa: E402

OUT = os.path.join(OF.ROOT, 'data', 'tmp', 'opening_calib.json')


def brier(p, y):
    oh = np.zeros_like(p)
    oh[np.arange(len(y)), y] = 1
    return float(((p - oh) ** 2).sum(axis=1).mean())


def main():
    S = OF.collect()
    y = np.array([x['label'] for x in S])
    P = np.array([[x['F']['o_h'] / 100, x['F']['o_d'] / 100, x['F']['o_a'] / 100] for x in S])
    Pl = np.array([[x['F']['l_h'] / 100, x['F']['l_d'] / 100, x['F']['l_a'] / 100] for x in S])
    n = len(y)
    print('样本 %d' % n)
    print('初盘 Brier %.4f  |  终盘 Brier %.4f  → 差 %+.4f' % (
        brier(P, y), brier(Pl, y), brier(P, y) - brier(Pl, y)))

    # ── 可靠性曲线：把三向摊平成 n*3 个 (p, hit) ──
    print('\n=== 可靠性曲线（三向摊平，每箱 = 一个方向的预测概率 vs 实际频率）===')
    pp, hh = [], []
    for i in range(n):
        for c in range(3):
            pp.append(P[i, c])
            hh.append(1.0 if y[i] == c else 0.0)
    pp, hh = np.array(pp), np.array(hh)
    edges = [0, .15, .22, .28, .34, .40, .50, .60, 1.01]
    rows = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (pp >= lo) & (pp < hi)
        if m.sum() < 15:
            continue
        obs = hh[m].mean()
        exp = pp[m].mean()
        rows.append((lo, hi, int(m.sum()), exp, obs))
        print('  P∈[%.2f,%.2f) n=%-4d 初盘 %.3f  实际 %.3f  偏差 %+.3f' % (
            lo, hi, int(m.sum()), exp, obs, obs - exp))

    # ── 拟合校准斜率（等渗性检验：logit 回归 obs ~ a + b·logit(p)）──
    eps = 1e-6
    lp = np.log(np.clip(pp, eps, 1 - eps) / (1 - np.clip(pp, eps, 1 - eps)))
    X = np.column_stack([np.ones(len(pp)), lp])
    w = np.zeros(2)
    for _ in range(3000):
        z = X @ w
        mu = 1 / (1 + np.exp(-np.clip(z, -30, 30)))
        g = X.T @ (mu - hh) / len(hh)
        w -= 0.8 * g
    print('\n校准斜率 b = %.3f（1.0 = 完美校准，>1 = 市场低估极端，<1 = 高估）' % w[1])
    print('截距 a = %+.3f' % w[0])

    # ── 时间分割：斜率稳定吗 ──
    order = np.argsort([x.get('kickoff') or '' for x in S])
    half = n // 2
    print('\n=== 时间分割（前后半段各自拟合斜率）===')
    for nm, idx in (('前半', order[:half]), ('后半', order[half:])):
        p2, h2 = [], []
        for i in idx:
            for c in range(3):
                p2.append(P[i, c])
                h2.append(1.0 if y[i] == c else 0.0)
        p2, h2 = np.array(p2), np.array(h2)
        l2 = np.log(np.clip(p2, eps, 1 - eps) / (1 - np.clip(p2, eps, 1 - eps)))
        X2 = np.column_stack([np.ones(len(p2)), l2])
        w2 = np.zeros(2)
        for _ in range(3000):
            z = X2 @ w2
            mu = 1 / (1 + np.exp(-np.clip(z, -30, 30)))
            w2 -= 0.8 * (X2.T @ (mu - h2) / len(h2))
        print('  %s n=%-3d 斜率 b=%.3f  截距 %+.3f' % (nm, len(idx), w2[1], w2[0]))

    # ── 投影到方向层面：用校准斜率修正后，方向命中会变吗 ──
    print('\n=== 用校准后概率重算方向命中 ===')
    for nm, PP in (('初盘原始', P), ('终盘原始', Pl)):
        fav = PP.argmax(1)
        print('  %s 命中 %.1f%%  Brier %.4f' % (nm, (fav == y).mean() * 100, brier(PP, y)))

    json.dump({'n': n, 'calib_slope': float(w[1]), 'calib_intercept': float(w[0]),
               'brier_open': brier(P, y), 'brier_late': brier(Pl, y),
               'curve': [dict(lo=r[0], hi=r[1], n=r[2], exp=r[3], obs=r[4]) for r in rows]},
              open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('\n→', OUT)


if __name__ == '__main__':
    main()
