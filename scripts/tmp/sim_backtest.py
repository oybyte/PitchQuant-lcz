#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sim_backtest.py — 相似性检索的严格时间分割回测（含市场基线对照）

🔴 纪律
  · **只用过去检索未来**：测试样本只能检索 ko 更早的样本。
  · **T-minus 视界对齐**：训练与测试在同一 horizon 截断，双方都看不到该视界之后的盘口。
  · **基线必做**（AGENTS §6）：永远押主胜 / 市场最低赔方向 / 模型反向。
  · 赛果只在评估阶段拼回，特征抽取完全不读赛果。

核心问题不是「KNN 命中率多少」，而是 **KNN 是否比市场定价本身多出信息**：
  因此必须做「一致/分歧」分层 —— 与市场热门同向的子集 + 分歧的子集分别统计。
"""
import json
import os
import sys

import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sim_features as SF   # noqa: E402

ROOT = SF.ROOT
OUT = os.path.join(ROOT, 'data', 'tmp', 'sim_backtest.json')

GROUPS = {
    'level': ['lvl_h', 'lvl_d', 'lvl_a', 'lvl_gap', 'lvl_skew', 'lvl_fav', 'lvl_h_draw'],
    'shift': ['dr_h', 'dr_d', 'dr_a', 'dr_span_h', 'dr_npts',
              'dr24_h', 'dr24_a', 'dr6_h', 'dr6_a', 'dr1_h', 'dr1_a'],
    'shape': ['sh_h_eff', 'sh_h_rev', 'sh_h_tc', 'sh_h_vol', 'sh_a_vol', 'sh_h_rng', 'sh_a_rng'],
    'stage': ['lv%d_%s' % (b, s) for b in (48, 24, 12, 6, 3, 1) for s in ('h', 'd', 'a', 'gap')],
    'asian': ['ah_line_open', 'ah_line_last', 'ah_line_d', 'ah_moves', 'ah_depth',
              'ah_p_open', 'ah_p_last', 'ah_p_d'],
    'total': ['ou_line_open', 'ou_line_last', 'ou_line_d', 'ou_over_open', 'ou_over_last'],
    'cross': ['x_eu_ah', 'x_line_imp'],
}


def build(samples, horizon, cols):
    """→ X, y, keep, mkt（mkt 恒由 lvl_h/d/a 计算，与 cols 是否含 level 无关）"""
    rows, ys, keep, mkt = [], [], [], []
    for s in samples:
        F = SF.features(SF.truncate(s['series'], horizon))
        if 'lvl_h' not in F:
            continue
        rows.append([F.get(c, np.nan) for c in cols])
        ys.append(s['label'])
        keep.append(s)
        v = [F['lvl_h'], F['lvl_d'], F['lvl_a']]
        mkt.append(int(np.argmax(v)))
    X = np.array(rows, dtype=float) if rows else np.zeros((0, len(cols)))
    return X, np.array(ys, dtype=int), keep, np.array(mkt, dtype=int)


def fit_stats(X):
    mu = np.nanmean(X, axis=0)
    mu = np.where(np.isnan(mu), 0.0, mu)
    Xf = np.where(np.isnan(X), mu, X)
    sd = Xf.std(axis=0)
    sd = np.where(sd < 1e-9, 1.0, sd)
    return mu, sd


def knn_proba(Xtr, ytr, xte, k=25, eps=1e-6):
    d = np.sqrt(((Xtr - xte) ** 2).sum(axis=1))
    k = min(k, len(d))
    idx = np.argsort(d)[:k]
    w = 1.0 / (d[idx] + eps)
    p = np.zeros(3)
    for pos, yi in enumerate(ytr[idx]):
        p[yi] += w[pos]
    s = p.sum()
    return p / s if s > 1e-12 else np.array([1 / 3, 1 / 3, 1 / 3])


def market_fav(X, cols, lvl_cols):
    """从特征矩阵取市场热门（lvl_h/d/a 最大者）"""
    ih = cols.index('lvl_h')
    idd = cols.index('lvl_d')
    ia = cols.index('lvl_a')
    out = []
    for row in X:
        v = np.array([row[ih], row[idd], row[ia]])
        if np.isnan(v).any():
            out.append(-1)
        else:
            out.append(int(np.argmax(v)))
    return np.array(out)


def run(horizon=6.0, k=25, groups=('level', 'shift'), min_train=80, ret=False):
    samples, _ = SF.collect_corpus()
    cols = []
    for g in groups:
        cols += GROUPS[g]
    X, y, keep, mkt_all = build(samples, horizon, cols)
    ko = np.array([s['ko'].timestamp() for s in keep])
    order = np.argsort(ko)

    preds = np.full(len(y), -1)
    probs = np.zeros((len(y), 3))
    for i in order:
        tr = np.where(ko < ko[i] - 1e-6)[0]
        if len(tr) < min_train:
            continue
        mu, sd = fit_stats(X[tr])
        Xtr = (np.where(np.isnan(X[tr]), mu, X[tr]) - mu) / sd
        xte = (np.where(np.isnan(X[i]), mu, X[i]) - mu) / sd
        p = knn_proba(Xtr, y[tr], xte, k=k)
        probs[i] = p
        preds[i] = int(p.argmax())

    m = preds >= 0
    Xm, ym, pm = X[m], y[m], probs[m]
    mkt = mkt_all[m]
    out = {'horizon': horizon, 'k': k, 'groups': '+'.join(groups), 'n': int(m.sum()),
           'n_total': int(len(y))}

    def acc(p):
        return round(float((p == ym).mean()) * 100, 2)

    w = np.array([np.bincount(ym, minlength=3) / len(ym)])
    base_rate = np.bincount(ym, minlength=3) / len(ym)
    out['baseline_always_home'] = round(float(base_rate[0]) * 100, 2)
    out['baseline_always_draw'] = round(float(base_rate[1]) * 100, 2)
    out['baseline_always_away'] = round(float(base_rate[2]) * 100, 2)
    out['knn_top1'] = acc(preds[m])
    out['knn_reversed'] = acc(2 - preds[m]) if False else round(float(((2 - preds[m]) == ym).mean()) * 100, 2)
    valid_mkt = mkt >= 0
    if valid_mkt.sum():
        out['market_top1'] = round(float((mkt[valid_mkt] == ym[valid_mkt]).mean()) * 100, 2)
        out['market_n'] = int(valid_mkt.sum())
        same = valid_mkt & (preds[m] == mkt)
        diff = valid_mkt & (preds[m] != mkt)
        out['agree_n'] = int(same.sum())
        out['agree_acc_both'] = round(float((preds[m][same] == ym[same]).mean()) * 100, 2) if same.sum() else None
        out['disagree_n'] = int(diff.sum())
        out['disagree_knn_acc'] = round(float((preds[m][diff] == ym[diff]).mean()) * 100, 2) if diff.sum() else None
        out['disagree_mkt_acc'] = round(float((mkt[diff] == ym[diff]).mean()) * 100, 2) if diff.sum() else None
    oh = np.zeros_like(pm)
    oh[np.arange(len(ym)), ym] = 1
    out['brier'] = round(float(((pm - oh) ** 2).sum(axis=1).mean()), 4)
    out['logloss'] = round(float(-np.mean(np.log(np.clip(pm[np.arange(len(ym)), ym], 1e-9, 1)))), 4)
    # 市场概率的同口径 Brier（用截断点去水概率，深度一热）—— 仅作参照，市场是硬 0/1 型需平滑
    mkt_oh = np.zeros((len(ym), 3))
    mkt_oh[np.arange(len(ym)), mkt] = 1.0
    out['brier_mkt_hard'] = round(float(((mkt_oh - oh) ** 2).sum(axis=1).mean()), 4)
    if ret:
        return out, dict(X=Xm, y=ym, p=pm, mkt=mkt, keep=[keep[i] for i in np.where(m)[0]])
    return out


def show(o):
    print('H=%-4.0f k=%-3d %-24s n=%-4d | KNN %5.1f%% | 市场 %s | 一致n=%-3s(%.1f%%) 分歧n=%-3s KNN %.1f%% vs 市场 %.1f%% | B %.3f' % (
        o['horizon'], o['k'], o['groups'], o['n'], o['knn_top1'],
        ('%5.1f%%' % o['market_top1']) if o.get('market_top1') is not None else '  n/a',
        o.get('agree_n', '-'), o.get('agree_acc_both') or 0,
        o.get('disagree_n', '-'), o.get('disagree_knn_acc') or 0, o.get('disagree_mkt_acc') or 0,
        o['brier']))


if __name__ == '__main__':
    print('=== 相似性检索回测（严格时间分割 · 含市场基线）===')
    print('样本方向分布由数据决定；市场=截断点上 lvl_h/d/a 最大者\n')
    res = []
    for H in (24.0, 12.0, 6.0, 3.0):
        for gs in (('level',), ('level', 'shift'), ('level', 'stage'),
                   ('level', 'shift', 'asian'), ('shift',), ('asian',), ('level', 'cross')):
            o = run(H, k=25, groups=gs)
            show(o)
            res.append(o)
    json.dump(res, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('\n→', OUT)
