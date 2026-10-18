# -*- coding: utf-8 -*-
"""check_vig_basis 自洽性检查回归（2026-10-18·吸收 v259_consistency）

v259_consistency.py 已删除，其三项检查并入 check_vig_basis.selfcheck_output：
  SC01 skew ↔ 隐含    SC02 λ ↔ 聚合方向    SC03 聚合概率和=100
并新增 SC04 铁胆↔skew、SC05 铁胆必带否定声明。
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(ROOT, 'scripts', 'tmp')
sys.path.insert(0, TMP)


def _codes(text):
    import check_vig_basis as V
    return [f['code'] for f in V.selfcheck_output(text, 'x.txt')]


def test_sc01_catches_skew_mismatch():
    """skew 报 999% 但隐含算出来 115.9% → 必须抓出"""
    txt = ('隐含: 主35.2%/平24.0%/客40.8%\n'
           'skew精确计算: 99.9/10.0 = 999%\n')
    assert 'SC01' in _codes(txt)


def test_sc01_tolerates_one_decimal_rounding():
    """隐含只保留 1 位小数，反算 skew 有舍入误差 → 不得误报"""
    txt = ('隐含: 主80.5%/平11.2%/客8.3%\n'
           'skew精确计算: 80.5/11.2 = 721%\n')
    assert 'SC01' not in _codes(txt)


def test_sc01_consistent_passes():
    txt = ('隐含: 主40.8%/平24.0%/客35.2%\n'
           'skew精确计算: 40.8/35.2 = 116%\n')
    assert 'SC01' not in _codes(txt)


def test_sc02_catches_lambda_vs_aggregate():
    """λ 主>客 但聚合最高是客 → 抓出"""
    txt = ('λ: 主1.80 客1.10 总2.90\n'
           '聚合: 主25.0% 平25.0% 客50.0%\n')
    assert 'SC02' in _codes(txt)


def test_sc02_skips_when_lambda_close():
    """|λh-λa|<=0.15 属噪声区，不判"""
    txt = ('λ: 主1.50 客1.45 总2.95\n'
           '聚合: 主25.0% 平25.0% 客50.0%\n')
    assert 'SC02' not in _codes(txt)


def test_sc03_catches_probability_sum():
    txt = '聚合: 主50.0% 平30.0% 客30.0%\n'
    assert 'SC03' in _codes(txt)


def test_sc03_passes_at_100():
    txt = '聚合: 主50.0% 平25.0% 客25.0%\n'
    assert 'SC03' not in _codes(txt)


def test_sc04_catches_tiedan_below_threshold():
    """标铁胆但 skew<450 → 抓出"""
    txt = '铁胆档: 🔴铁胆(skew=300≥450·439场实测命中85.7%·n=49)\n铁胆 ≠ 100%\n'
    assert 'SC04' in _codes(txt)


def test_sc05_requires_never_100_notice():
    """标铁胆但缺「铁胆 ≠ 100%」→ 抓出"""
    txt = '铁胆档: 🔴铁胆(skew=805≥450·439场实测命中85.7%·n=49)\n'
    assert 'SC05' in _codes(txt)


def test_sc05_passes_with_notice():
    txt = ('铁胆档: 🔴铁胆(skew=805≥450·439场实测命中85.7%·n=49)\n'
           '🔴 铁胆 ≠ 100%：约每 7 场错 1 场\n')
    assert 'SC05' not in _codes(txt)


def test_empty_text_yields_no_false_positive():
    assert _codes("") == []


@pytest.mark.skipif(not os.path.isdir(os.path.join(ROOT, "data", "tmp", "batch_v259V", "out")),
                    reason="需 data/tmp/batch_v259V/out")
def test_real_batch_is_self_consistent():
    """真实批次必须全部自洽（否则说明模型输出内部矛盾）"""
    import check_vig_basis as V
    out = os.path.join(ROOT, 'data', 'tmp', 'batch_v259V', 'out')
    bad = []
    for fn in sorted(os.listdir(out)):
        if not fn.endswith('.txt'):
            continue
        t = open(os.path.join(out, fn), encoding='utf-8').read()
        bad += [(fn, f) for f in V.selfcheck_output(t, fn) if f["level"] == "FAIL"]
    assert not bad, bad[:5]