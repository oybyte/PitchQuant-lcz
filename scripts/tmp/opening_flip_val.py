#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""opening_flip_val.py — 给「热门被推翻」信号上最后的严格性

已知
  推翻 n=21，终盘热门命中 33.3%（vs 未翻 59.8%），p=0.0082，前后半段 31.2%/40.0% 同向。
  分布恰好三向各 33.3%，平局率 +13.2pp。

必须排除
  ① 抽样噪声（Bootstrap）
  ② 「只是弱共识的换皮」（与初盘 skew / 分歧幅度对比）
  ③ 样本量是否支撑「可直接用」
"""
import json
import math
import os
import sys

import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import opening_features as OF      # noqa: E402

OUT = os.path.join(OF.ROOT, 'data', 'tmp', 'opening_flip_val.json')


def main():
    S = OF.collect()
    y = np.array([x['label'] for x in S])
    n = len(S)
    fo = np.array([int(np.argmax([x['F'].get('o_h', 0), x['F'].get('o_d', 0), x['F'].get('o_a', 0)])) for x in S])
    fl = np.array([int(np.argmax([x['F'].get('l_h', 0), x['F'].get('l_d', 0), x['F'].get('l_a', 0)])) for x in S])
    skew_o = np.array([x['F'].get('o_skew', np.nan) for x in S])
    flip = fo != fl
    hit_l = fl == y
    print('n=%d  推翻 %d (%.1f%%)' % (n, flip.sum(), flip.mean() * 100))

    # ① Bootstrap
    rng = np.random.default_rng(42)
    diffs = []
    for _ in range(5000):
        j = rng.integers(0, n, n)
        if flip[j].sum() < 5 or (~flip[j]).sum() < 5:
            continue
        diffs.append(hit_l[j][flip[j]].mean() - hit_l[j][~flip[j]].mean())
    diffs = np.array(diffs)
    obs = hit_l[flip].mean() - hit_l[~flip].mean()
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    print('\n① Bootstrap（5000 次重抽）')
    print('   实测差 %+.3f   95%%CI [%.3f, %.3f]   P(差≥0) = %.4f' % (
        obs, lo, hi, (diffs >= 0).mean()))

    # ② 与 skew 的关系：推翻场是不是本就弱共识？
    print('\n② 竞争解释：推翻场是否只是「初盘本来就没共识」？')
    for nm, m in (('未翻', ~flip), ('推翻', flip)):
        s = skew_o[m]
        s = s[~np.isnan(s)]
        print('   %-4s n=%-3d 初盘 skew 中位 %.0f%%  均值 %.0f%%  <150%%占比 %.0f%%' % (
            nm, int(m.sum()), np.median(s), s.mean(), (s < 150).mean() * 100))
    # 控制 skew：只在 skew>=150 的场里看推翻效应
    strong = skew_o >= 150
    for nm, m in (('skew≥150 未翻', strong & ~flip), ('skew≥150 推翻', strong & flip)):
        if m.sum() < 4:
            print('   %-14s n=%d（样本不足）' % (nm, int(m.sum())))
            continue
        print('   %-14s n=%-3d 终盘热门命中 %5.1f%%' % (nm, int(m.sum()), hit_l[m].mean() * 100))

    # ③ 变动幅度是否比「是否推翻」更有信息
    print('\n③ 「是否推翻」vs「变动幅度」哪个更有信息？')
    dmax = np.array([max(abs(x['F'].get('d_h', 0)), abs(x['F'].get('d_a', 0))) for x in S])
    for thr in (1.0, 2.0, 3.0, 5.0):
        m = dmax >= thr
        if m.sum() < 15:
            continue
        print('   变动≥%.1fpp  n=%-3d 终盘热门命中 %5.1f%%  (推翻在其中占 %.0f%%)' % (
            thr, int(m.sum()), hit_l[m].mean() * 100, flip[m].mean() * 100))

    # ④ 结论强度
    print('\n④ 结论强度评估')
    print('   n=21 推翻场；命中 7/21。Wilson 95%%CI = [17.2%%, 54.6%%]')
    print('   区间上界 54.6%% 仍低于未翻场的 59.8%% → 方向一致但幅度不可靠')
    print('   → 可用作「降档/并列」触发，不可用作「反向押」')

    # ⑤ 今日直接套用会命中几场？
    print('\n⑤ 今日 19 场里有多少满足「热门被推翻」？')
    print('   需今日终盘（当前抓取即盘）vs 初盘 —— 见 opening_apply.py')

    json.dump(dict(n=n, flip_n=int(flip.sum()), obs=float(obs),
                   ci=[float(lo), float(hi)], p_ge0=float((diffs >= 0).mean())),
              open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('\n→', OUT)


if __name__ == '__main__':
    main()
