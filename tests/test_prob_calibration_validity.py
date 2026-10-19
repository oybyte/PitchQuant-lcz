# -*- coding: utf-8 -*-
"""概率校准表的统计有效性守卫（2026-10-19·2.5pp 缺口根因修复）。

🔴 根因（systematic-debugging Phase 1-3 实测）
  79 场复盘：模型 59.5% vs 直接押市场热门 62.0%，差 2.5pp。
  逐场比对发现模型只在 5 场改判、5 场全错、置信度全 LOW，且全部是
  「市场主胜 → 模型客胜」。
  追踪 direction_full 的概率路径（以克拉约瓦 vs 赫塔菲为例）：
      ① 去水起点        主35.8 平29.3 客34.8   主客差 +1.0
      ② 校准 [0.30-0.40] bias=-5.97pp → 主29.9 客34.8   主客差 -5.0  ← 方向在此翻掉
      ③ 平局加权+0.05   → 主30.2 客35.2
      ④ 欧战档矩阵      → 主35.1 客35.7
      ⑤ 最终            客胜
  即：**0.30-0.40 这一档的 -5.97pp 直接把主胜压出局**。

🔴 该档本身站不住
  441 场样本回查：n=93，实际主胜 29.0% vs 隐含中点 35.0%，bias -6.0pp，
  但二项检验 **p=0.114（不显著）**；分批看 batch_2_5_8 +15.0pp / batch_74 +1.8pp /
  batch_140 -16.5pp / batch_203 -4.8pp —— **四个批次正负颠倒，是噪声**。

  全 8 档只有 0.60-0.70 一档 p<0.05（+11.9pp），其余全部不显著。

修复纪律
  · 校准档必须通过统计显著性才会被施加；不显著的档置 0（而不是照抄噪声）
  · 校准只作用于「热门方向」且不得把主客接近的场次翻向 —— 该保护由显著性过滤自然达成
"""
import json
import math
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(ROOT, 'scripts', 'tmp')
CALIB = os.path.join(ROOT, 'data', 'tmp', 'prob_calibration.json')


def _load():
    return json.load(open(CALIB, encoding='utf-8'))


def test_calibration_bands_carry_significance_metadata():
    """每个档必须带 n / bias_pp / p_value，否则无法判断它是不是噪声。"""
    d = _load()
    bands = {k: v for k, v in d.items() if k != '_meta'}
    assert bands, '校准表为空'
    for k, v in bands.items():
        assert 'n' in v, '%s 缺 n' % k
        assert 'bias_pp' in v, '%s 缺 bias_pp' % k
        assert 'p_value' in v, (
            '%s 缺 p_value —— 无 p 值就无法区分「真偏差」与「小样本噪声」，'
            '本次 2.5pp 缺口正是把 p=0.114 的噪声当成了证据' % k)


def test_insignificant_bands_are_zeroed():
    """p>=0.05 的档 bias_pp 必须为 0（禁止把噪声当修正量）。"""
    d = _load()
    bad = []
    for k, v in d.items():
        if k == '_meta':
            continue
        p = v.get('p_value')
        if p is None:
            bad.append((k, 'missing p'))
            continue
        if p >= 0.05 and abs(v.get('bias_pp', 0)) > 1e-9:
            bad.append((k, 'p=%.4f 但 bias=%.2f pp' % (p, v['bias_pp'])))
    assert not bad, '不显著却仍施加修正: %s' % bad


def test_the_noise_band_that_caused_the_gap_is_zeroed():
    """0.30-0.40 档（本次根因）必须是 0 —— 它的 p=0.114 且四批次正负颠倒。"""
    d = _load()
    v = d['0.30-0.40']
    assert v.get('p_value', 1.0) >= 0.05
    assert v.get('bias_pp', 0) == 0, (
        '0.30-0.40 档 bias 仍为 %.2f —— 会把主客接近的场次从主胜翻成客胜' % v['bias_pp'])


def test_significant_band_is_preserved():
    """唯一显著档（0.60-0.70，p=0.036，+11.9pp）必须保留，不得一刀切全关。"""
    d = _load()
    v = d['0.60-0.70']
    assert v.get('p_value', 1.0) < 0.05
    assert v.get('bias_pp', 0) > 0, '最强热门低估档被误关，会丢失真信号'


def test_calibration_still_continuous():
    """读端是 if lo<=ph<hi，区间必须仍连续覆盖 0-1。"""
    d = _load()
    sp = sorted((float(k.split('-')[0]), float(k.split('-')[1]))
                for k in d if k != '_meta')
    assert abs(sp[0][0]) < 1e-9
    assert abs(sp[-1][1] - 1.0) < 1e-9
    for a, b in zip(sp, sp[1:]):
        assert abs(a[1] - b[0]) < 1e-9, '区间不连续: %s -> %s' % (a, b)


def test_direction_not_flipped_on_close_matches():
    """端到端：校准不得把「市场主胜、主客隐含接近」的场次翻成客胜。

    用本次 5 场改判里的 3 场真实赔率（澳门基线）直接跑 direction_full。
    """
    if TMP not in sys.path:
        sys.path.insert(0, TMP)
    import calc_v3572 as V

    cases = [
        ('克拉约瓦大学 vs 赫塔菲', 2.48, 3.03, 2.55, -0.0, '欧协联'),
        ('哥本哈根 vs 布拉加', 2.35, 3.21, 2.58, -0.0, '欧协联'),
        ('利兹联 vs 曼联', 2.32, 3.55, 2.51, -0.25, '英超'),
    ]
    flipped = []
    for nm, oh, od, oa, handi, lg in cases:
        inv = [1 / oh, 1 / od, 1 / oa]
        s = sum(inv)
        raw = [x / s for x in inv]
        market = ['主胜', '平局', '客胜'][raw.index(max(raw))]
        r = V.direction_full(oh, od, oa, over25=1.85, league_div=lg, handi=handi)
        if market != r['主方向']:
            flipped.append((nm, market, r['主方向']))
    assert not flipped, '校准把市场方向翻掉了: %s' % flipped
