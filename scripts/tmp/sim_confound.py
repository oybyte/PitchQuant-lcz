#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sim_confound.py — 关键反证：分歧信号是不是「市场自己没把握」的代理？

如果分歧态的多为「市场热门概率本身低」的场次，那分歧标签没有独立信息，
只是把市场的置信度重算了一遍。本脚本做三件事：

  1. 分歧率 vs 市场热门概率的相关（若强负相关 → 代理嫌疑成立）
  2. 逻辑回归 + 时间分割：特征 A = 市场热门概率；特征 B = 分歧哑变量
     比较 A 单独 vs A+B 的 AUC / 对数似然 —— 增量是否显著
  3. 「同档内」置换检验：在相同市场概率档内随机置换分歧标签，看实际差值落在分布何处
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

OUT = os.path.join(SF.ROOT, 'data', 'tmp', 'sim_confound.json')
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
        mk = v / v.sum()
        recs.append(dict(y=int(y[i]), fav=int(mk.argmax()), maxp=float(mk.max()),
                         disagree=int(p.argmax() != mk.argmax()),
                         hit=int(mk.argmax() == y[i])))
    return recs


def auc(score, label):
    score, label = np.asarray(score, float), np.asarray(label, int)
    pos, neg = score[label == 1], score[label == 0]
    if not len(pos) or not len(neg):
        return 0.5
    return float(((pos[:, None] > neg[None, :]).sum()
                  + 0.5 * (pos[:, None] == neg[None, :]).sum()) / (len(pos) * len(neg)))


def logit_fit(Xm, yv, iters=400, lr=0.5):
    w = np.zeros(Xm.shape[1])
    for _ in range(iters):
        z = Xm @ w
        p = 1 / (1 + np.exp(-np.clip(z, -30, 30)))
        g = Xm.T @ (p - yv) / len(yv)
        w -= lr * g
    return w


def logit_pred(w, Xm):
    return 1 / (1 + np.exp(-np.clip(Xm @ w, -30, 30)))


def main():
    recs = rolling()
    n = len(recs)
    maxp = np.array([r['maxp'] for r in recs])
    dis = np.array([r['disagree'] for r in recs])
    miss = np.array([1 - r['hit'] for r in recs])     # 1 = 市场猜错
    print('可评估', n, ' 分歧', int(dis.sum()), ' 市场错', int(miss.sum()))

    print('\n=== 1. 分歧率 vs 市场热门概率（分层）===')
    print('  若分歧集中出现在低概率档 → 分歧只是「市场没把握」的代理')
    for lo, hi in ((0, .40), (.40, .50), (.50, .60), (.60, .75), (.75, 1.01)):
        m = (maxp >= lo) & (maxp < hi)
        if m.sum() < 10:
            continue
        print('  热门P∈[%.2f,%.2f) n=%-3d 分歧率 %5.1f%%  市场错率 %5.1f%%' % (
            lo, hi, int(m.sum()), dis[m].mean() * 100, miss[m].mean() * 100))
    r_ = float(np.corrcoef(maxp, dis)[0, 1])
    print('  corr(市场热门概率, 分歧) = %+.3f' % r_)

    print('\n=== 2. 逻辑回归：分歧是否有独立增量（预测「市场猜错」）===')
    # 时间分割：前 60% 训练，后 40% 测试
    idx = np.argsort([r['maxp'] for r in recs])   # 保持确定性顺序
    cut = int(n * 0.6)
    trn, tst = np.arange(cut), np.arange(cut, n)
    def build(cols):
        M = np.column_stack([np.ones(n)] + cols)
        return M[:, :]
    A = np.column_stack([np.ones(n), -maxp])       # 概率越低越可能猜错
    B = np.column_stack([np.ones(n), -maxp, dis])
    wA = logit_fit(A[trn], miss[trn])
    wB = logit_fit(B[trn], miss[trn])
    pA = logit_pred(wA, A[tst])
    pB = logit_pred(wB, B[tst])
    print('  仅市场概率      AUC=%.3f   对数损失=%.4f' % (
        auc(pA, miss[tst]), -np.mean(miss[tst] * np.log(np.clip(pA, 1e-6, 1))
                                     + (1 - miss[tst]) * np.log(np.clip(1 - pA, 1e-6, 1)))))
    print('  市场概率+分歧   AUC=%.3f   对数损失=%.4f' % (
        auc(pB, miss[tst]), -np.mean(miss[tst] * np.log(np.clip(pB, 1e-6, 1))
                                     + (1 - miss[tst]) * np.log(np.clip(1 - pB, 1e-6, 1)))))
    print('  分歧系数 = %+.3f（正=分歧加剧猜错风险）' % wB[2])

    print('\n=== 3. 同档内置换检验（控制市场概率后，分歧还剩下多少）===')
    rng = np.random.default_rng(20261018)
    # 按市场概率六分位分箱，箱内置换分歧标签
    qs = np.quantile(maxp, np.linspace(0, 1, 7))
    bins = np.digitize(maxp, qs[1:-1])
    obs = miss[dis == 1].mean() - miss[dis == 0].mean()
    null = []
    for _ in range(500):
        d2 = dis.copy()
        for b in np.unique(bins):
            m = bins == b
            d2[m] = rng.permutation(d2[m])
        if (d2 == 1).sum() == 0 or (d2 == 0).sum() == 0:
            continue
        null.append(miss[d2 == 1].mean() - miss[d2 == 0].mean())
    null = np.array(null)
    pv = float((null >= obs).mean())
    print('  实测 分歧−一致 的错误率差 = %+.3f' % obs)
    print('  同档置换零分布  均值 %+.3f  σ=%.3f' % (null.mean(), null.std()))
    print('  置换检验 p = %.3f  → %s' % (
        pv, '分歧仍有独立信息' if pv < 0.05 else '🔴控制市场概率后不显著（代理嫌疑成立）'))

    json.dump(dict(n=n, disagree=int(dis.sum()), corr=float(r_),
                   auc_mkt=auc(pA, miss[tst]), auc_both=auc(pB, miss[tst]),
                   coef_dis=float(wB[2]), perm_p=pv, perm_obs=float(obs)),
              open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('\n→', OUT)


if __name__ == '__main__':
    main()
