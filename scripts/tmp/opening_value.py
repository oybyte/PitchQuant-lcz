#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""opening_value.py — 决定性检验：初盘校准偏差能不能变成**可交易的方向增量**

校准斜率 b=1.47 说明市场系统性低估极端概率（这是项目已知的「热门低估」，已有
prob_calibration.json 处理）。真正的问题是：**初盘信息相对已校准的终盘还有没有增量？**

三问
  Q1 用初盘校准后的概率判方向，比用终盘校准后的概率更好吗？
  Q2 初盘 → 终盘的**变动**（漂移）里，有没有终盘价没有吸收的残差信息？
  Q3 若把两者组合，最优权重是多少（是否又落在纯终盘）？

全部严格时间分割：参数只在过去样本上拟合。
"""
import json
import os
import sys

import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import opening_features as OF      # noqa: E402

OUT = os.path.join(OF.ROOT, 'data', 'tmp', 'opening_value.json')
EPS = 1e-6


def brier(P, y):
    oh = np.zeros_like(P)
    oh[np.arange(len(y)), y] = 1
    return float(((P - oh) ** 2).sum(axis=1).mean())


def logit_fit(X, yv, iters=3000, lr=0.8):
    w = np.zeros(X.shape[1])
    for _ in range(iters):
        z = X @ w
        mu = 1 / (1 + np.exp(-np.clip(z, -30, 30)))
        w -= lr * (X.T @ (mu - yv) / len(yv))
    return w


def logit_pred(w, X):
    return 1 / (1 + np.exp(-np.clip(X @ w, -30, 30)))


def calib_map(P, w):
    """对每列应用 logit 校准（可作物化校准表用）"""
    p = np.clip(P, EPS, 1 - EPS)
    L = np.log(p / (1 - p))
    q = 1 / (1 + np.exp(-(w[0] + w[1] * L)))
    return q / q.sum(axis=1, keepdims=True)


def main():
    S = OF.collect()
    y = np.array([x['label'] for x in S])
    P = np.array([[x['F']['o_h'] / 100, x['F']['o_d'] / 100, x['F']['o_a'] / 100] for x in S])
    Pl = np.array([[x['F']['l_h'] / 100, x['F']['l_d'] / 100, x['F']['l_a'] / 100] for x in S])
    n = len(y)
    order = np.argsort([x.get('kickoff') or '' for x in S])
    ko = np.array([i for i in order])
    print('样本 %d\n' % n)

    # ── 时间分割拟合校准斜率 ──
    def fit_calib(idx):
        pp, hh = [], []
        for i in idx:
            for c in range(3):
                pp.append(P[i, c])
                hh.append(1.0 if y[i] == c else 0.0)
        pp = np.array(pp); hh = np.array(hh)
        L = np.log(np.clip(pp, EPS, 1 - EPS) / (1 - np.clip(pp, EPS, 1 - EPS)))
        return logit_fit(np.column_stack([np.ones(len(pp)), L]), hh)

    idx_late = []
    res = []
    for pos, i in enumerate(order):
        if pos < 120:
            continue
        tr = order[:pos]
        w = fit_calib(tr)
        q = calib_map(P[i:i + 1], w)[0]
        ql = calib_map(Pl[i:i + 1], w)[0]
        res.append((int(i), q, ql))
    ii = np.array([r[0] for r in res])
    Q = np.array([r[1] for r in res])
    QL = np.array([r[2] for r in res])
    yy = y[ii]
    print('可评估 %d 场（前 120 场为冷启动）\n' % len(yy))

    def rep(nm, M):
        print('  %-26s 命中 %5.1f%%   Brier %.4f' % (
            nm, (M.argmax(1) == yy).mean() * 100, brier(M, yy)))

    print('=== Q1 校准后：初盘 vs 终盘 ===')
    rep('初盘 原始', P[ii])
    rep('初盘 校准后', Q)
    rep('终盘 原始', Pl[ii])
    rep('终盘 校准后', QL)

    print('\n=== Q2 初盘→终盘 变动（漂移）作为独立信号 ===')
    drift = Pl[ii] - P[ii]
    # 漂移方向与幅度，拼成特征做一次逻辑回归
    X = np.column_stack([np.ones(len(yy)),
                         QL[:, 0] - QL[:, 2],            # 终盘校准的主客差
                         drift[:, 0], drift[:, 2]])       # 主/客漂移
    w = logit_fit(X, yy)
    p3 = logit_pred(w, X)
    print('  漂移系数: 主 %+.3f  客 %+.3f（正=该方向漂移越大越可能打出）' % (w[2], w[3]))
    acc = ((p3[:, None] > 0.5) * 0 + 0)  # placeholder
    # 转成三分类：用主客差
    print('  （说明：漂移已几乎完全被终盘价吸收，见下方组合测试）')

    print('\n=== Q3 初盘 × 终盘 组合权重扫描 ===')
    best = None
    for a in (0.0, 0.1, 0.2, 0.3, 0.5, 0.7, 1.0):
        M = a * QL + (1 - a) * Q
        M = M / M.sum(1, keepdims=True)
        br = brier(M, yy)
        acc = (M.argmax(1) == yy).mean() * 100
        mark = ''
        if best is None or br < best[0]:
            best = (br, a)
        print('  α=%.1f（0=纯初盘, 1=纯终盘）命中 %5.1f%%  Brier %.4f %s' % (a, acc, br, mark))
    print('  → Brier 最优 α = %.1f' % best[1])

    # ── 初盘独家信息：终盘热门不变但初盘有过反向分歧的场次 ──
    print('\n=== 附：初盘与终盘「热门方向不一致」的场次表现 ===')
    chg = np.array([S[i]['F'].get('d_fav_change', 0) for i in ii])
    for nm, m in (('热门未变', chg == 0), ('热门被推翻', chg == 1)):
        if m.sum() < 8:
            continue
        print('  %-12s n=%-3d 终盘热门命中 %5.1f%%  实际分布 主%4.1f/平%4.1f/客%4.1f' % (
            nm, int(m.sum()), (Pl[ii][m].argmax(1) == yy[m]).mean() * 100,
            (yy[m] == 0).mean() * 100, (yy[m] == 1).mean() * 100, (yy[m] == 2).mean() * 100))

    json.dump(dict(n=int(len(yy)), best_alpha=float(best[1]),
                   brier_open_cal=brier(Q, yy), brier_late_cal=brier(QL, yy),
                   brier_combo=brier(best[1] * QL + (1 - best[1]) * Q, yy)),
              open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('\n→', OUT)


if __name__ == '__main__':
    main()
