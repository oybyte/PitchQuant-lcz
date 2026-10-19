#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sim_apply.py — 把「已通过严格检验」的那一部分用到今日 19 场

只做两件有回测支撑的事，其余一律不掺：
  ① 相似度检索：给出每场的最近邻历史样本（人工可核对，透明可审计）
  ② 分歧标记：KNN 多数方向 ≠ 市场热门时 → 打「相似性分歧」标签
     （回测：分歧态市场方向命中 32.4%，一致态 60.1%，p=0.0020）
     用法严格限定为**置信度降档器**，不改方向、不进方向合成。

⚠️ 明确不做：不用 KNN 的概率做方向/比分/大小球输出（回测已证伪）。
"""
import json
import os
import sys

import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sim_features as SF      # noqa: E402
import sim_backtest as SB      # noqa: E402

OUT = os.path.join(SF.ROOT, 'data', 'tmp', 'sim_today.json')
COLS = SB.GROUPS['level'] + SB.GROUPS['shift'] + SB.GROUPS['asian']
H = 6.0
K = 25


def main():
    samples, _ = SF.collect_corpus()
    X, y, keep, mkt = SB.build(samples, H, COLS)
    mu, sd = SB.fit_stats(X)
    Xs = (np.where(np.isnan(X), mu, X) - mu) / sd
    ko = np.array([s['ko'].timestamp() for s in keep])
    LAB = {0: '主胜', 1: '平局', 2: '客胜'}

    targets = SF.collect_targets()
    print('今日待赛 %d 场｜历史检索池 %d 场（全部早于今日）\n' % (len(targets), len(X)))

    out = []
    for t in targets:
        F = SF.features(SF.truncate(t['series'], H))
        if 'lvl_h' not in F:
            print('SKIP', t['name'])
            continue
        xte = np.array([F.get(c, np.nan) for c in COLS])
        xte = (np.where(np.isnan(xte), mu, xte) - mu) / sd
        d = np.sqrt(((Xs - xte) ** 2).sum(axis=1))
        # 🔴 只检索比本场更早开赛的样本
        tko = t['ko'].timestamp()
        older = ko < tko - 1e-6
        d = np.where(older, d, np.inf)
        idx = np.argsort(d)[:K]
        w = 1.0 / (d[idx] + 1e-6)
        prob = np.zeros(3)
        for j, yi in enumerate(y[idx]):
            prob[yi] += w[j]
        prob /= prob.sum()

        v = np.array([F['lvl_h'], F['lvl_d'], F['lvl_a']])
        mk = v / v.sum()
        mkt_fav = int(mk.argmax())
        knn_fav = int(prob.argmax())
        n_nb = int(older.sum())
        agree = (knn_fav == mkt_fav)
        nn = []
        for j in idx[:5]:
            s = keep[j]
            nn.append('%s %s(%s %s)' % (s['league'], s['name'][:22], s['act'],
                                        s.get('score') or '?'))
        rec = dict(name=t['name'], mt=t['mt'], league=t['league'],
                   market=dict(h=round(mk[0] * 100, 1), d=round(mk[1] * 100, 1),
                               a=round(mk[2] * 100, 1), fav=LAB[mkt_fav]),
                   knn=dict(h=round(prob[0] * 100, 1), d=round(prob[1] * 100, 1),
                            a=round(prob[2] * 100, 1), fav=LAB[knn_fav]),
                   agree=bool(agree), n_neighbors=n_nb,
                   mean_dist=round(float(np.mean(d[idx])), 3),
                   nearest=nn)
        out.append(rec)

        flag = '✅一致' if agree else '🔴分歧'
        print('%s  %s' % (t['mt'], t['name']))
        print('    市场 %-4s %.1f/%.1f/%.1f   KNN %-4s %.1f/%.1f/%.1f   %s  (池 %d)' % (
            LAB[mkt_fav], mk[0] * 100, mk[1] * 100, mk[2] * 100,
            LAB[knn_fav], prob[0] * 100, prob[1] * 100, prob[2] * 100, flag, n_nb))
        for s in nn[:3]:
            print('       ↳', s)
        print()

    json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    n_dis = sum(1 for r in out if not r['agree'])
    print('分歧场次 %d / %d  → %s' % (n_dis, len(out), OUT))


if __name__ == '__main__':
    main()
