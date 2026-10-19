#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sim_probe2.py — 在「方向 KNN 全面输给市场」的负结果之上，进一步定位相似性到底能不能用

四个假设逐个检验（严格时间分割，同 sim_backtest 口径）
  H1 市场热门够强时，KNN 是否被稀释 → 分档看
  H2 相似性别的不说，能不能预测「爆冷」（实际 ≠ 市场热门）→ AUC
  H3 平局是唯一可能被相似性捡到的类 → 平局精确率（top-decile）
  H4 跨联赛混池破坏信号 → 只检索同联赛

输出: data/tmp/sim_probe2.json
"""
import json
import os
import sys

import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sim_features as SF       # noqa: E402
import sim_backtest as SB       # noqa: E402

OUT = os.path.join(SF.ROOT, 'data', 'tmp', 'sim_probe2.json')
COLS = SB.GROUPS['level'] + SB.GROUPS['shift'] + SB.GROUPS['asian']


def walk(horizon=6.0, k=25, min_train=80, same_league=False):
    """逐场滚动：只用过去样本，返回逐场记录"""
    samples, _ = SF.collect_corpus()
    X, y, keep, mkt = SB.build(samples, horizon, COLS)
    ko = np.array([s['ko'].timestamp() for s in keep])
    lg = np.array([s['league'] for s in keep])
    order = np.argsort(ko)
    recs = []
    for i in order:
        tr = np.where(ko < ko[i] - 1e-6)[0]
        if same_league:
            tr = tr[lg[tr] == lg[i]]
        if len(tr) < min_train:
            continue
        mu, sd = SB.fit_stats(X[tr])
        Xtr = (np.where(np.isnan(X[tr]), mu, X[tr]) - mu) / sd
        xte = (np.where(np.isnan(X[i]), mu, X[i]) - mu) / sd
        p = SB.knn_proba(Xtr, y[tr], xte, k=k)
        # 市场概率（截断点去水）
        mh, md, ma = [X[i][COLS.index(c)] for c in ('lvl_h', 'lvl_d', 'lvl_a')]
        s = mh + md + ma
        mk = np.array([mh, md, ma]) / s if s > 0 else np.array([1/3]*3)
        recs.append(dict(i=int(i), y=int(y[i]), p=p, mkt=mk, fav=int(mkt[i]),
                         league=lg[i], name=keep[i]['name'], ko=keep[i]['ko']))
    return recs


def auc(score, label):
    """label=1 为正类；score 越大越像正类"""
    score = np.asarray(score, float)
    label = np.asarray(label, int)
    pos, neg = score[label == 1], score[label == 0]
    if not len(pos) or not len(neg):
        return None
    a = 0.0
    for x in pos:
        a += (neg < x).sum() + 0.5 * (neg == x).sum()
    return float(a / (len(pos) * len(neg)))


def main():
    res = {}
    recs = walk(6.0, k=25)
    n = len(recs)
    print('可评估场次', n)

    # ── H1 市场热门概率分档 ──
    print('\n[H1] 按市场热门概率分档（KNN vs 市场 top1）')
    rows = []
    for lo, hi in ((0, .40), (.40, .50), (.50, .60), (.60, .75), (.75, 1.01)):
        sub = [r for r in recs if lo <= max(r['mkt']) < hi]
        if len(sub) < 15:
            continue
        ka = np.mean([r['p'].argmax() == r['y'] for r in sub]) * 100
        ma = np.mean([r['fav'] == r['y'] for r in sub]) * 100
        rows.append((lo, hi, len(sub), ka, ma))
        print('  热门P∈[%.2f,%.2f) n=%-3d KNN %5.1f%%  市场 %5.1f%%' % (lo, hi, len(sub), ka, ma))
    res['H1'] = rows

    # ── H2 爆冷预测（非热门方胜出）──
    upset = np.array([1 if r['y'] != r['fav'] else 0 for r in recs])
    knn_fav_p = np.array([r['p'][r['fav']] for r in recs])
    mkt_fav_p = np.array([r['mkt'][r['fav']] for r in recs])
    a_knn = auc(-knn_fav_p, upset)     # KNN 给热门低概率 → 更像爆冷
    a_mkt = auc(-mkt_fav_p, upset)
    print('\n[H2] 爆冷识别 AUC  KNN=%.3f  市场=%.3f  (基准0.5)  爆冷率=%.1f%%' % (
        a_knn, a_mkt, upset.mean() * 100))
    res['H2'] = dict(auc_knn=a_knn, auc_mkt=a_mkt, upset_rate=float(upset.mean()))

    # ── H3 平局：top-decile 精确率 ──
    draws = np.array([1 if r['y'] == 1 else 0 for r in recs])
    kd = np.array([r['p'][1] for r in recs])
    md = np.array([r['mkt'][1] for r in recs])
    nn = max(10, int(len(recs) * 0.2))
    for nm, sc in (('KNN', kd), ('市场', md)):
        top = np.argsort(-sc)[:nn]
        print('[H3] %s 平局 top-%d 精确率 %.1f%%（全样本平局率 %.1f%%）' % (
            nm, nn, draws[top].mean() * 100, draws.mean() * 100))
    res['H3'] = dict(nn=nn, knn=float(draws[np.argsort(-kd)[:nn]].mean()),
                     mkt=float(draws[np.argsort(-md)[:nn]].mean()),
                     base=float(draws.mean()),
                     auc_knn=auc(kd, draws), auc_mkt=auc(md, draws))

    # ── H4 同联赛检索 ──
    print('\n[H4] 只检索同联赛（min_train 降到 25）')
    recs4 = walk(6.0, k=25, min_train=25, same_league=True)
    if recs4:
        ka = np.mean([r['p'].argmax() == r['y'] for r in recs4]) * 100
        ma = np.mean([r['fav'] == r['y'] for r in recs4]) * 100
        print('  n=%d  KNN %.1f%%  市场 %.1f%%' % (len(recs4), ka, ma))
        res['H4'] = dict(n=len(recs4), knn=ka, mkt=ma)
    else:
        print('  同联赛样本不足以训练（每联赛 <25 场）')
        res['H4'] = dict(n=0)

    # ── 市场 vs KNN 的校准对比（Brier，用市场软概率）──
    oh = np.zeros((n, 3))
    for j, r in enumerate(recs):
        oh[j, r['y']] = 1
    pm = np.array([r['p'] for r in recs])
    pk = np.array([r['mkt'] for r in recs])
    print('\n[校准] KNN Brier=%.4f  市场 Brier=%.4f  (越低越好)' % (
        ((pm - oh) ** 2).sum(1).mean(), ((pk - oh) ** 2).sum(1).mean()))
    res['calib'] = dict(brier_knn=float(((pm - oh) ** 2).sum(1).mean()),
                        brier_mkt=float(((pk - oh) ** 2).sum(1).mean()))

    json.dump(res, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('\n→', OUT)


if __name__ == '__main__':
    main()
