# -*- coding: utf-8 -*-
"""大小球判向「单一真源」回归测试（2026-10-18·ou_dir 口径统一）。

背景（435 场 A/B·docs/整改复核_2026-10-17_435场证据.md）:
  calc_all 曾同时存在两套判向切点：
    · over_p 概率分类器 (over_p>=54 判大 / <=46 判小)  ← 441 场盲测实际所用
    · O2.5 赔率阈值   (<1.90 判大 / >2.10 判小)      ← 代码实际执行
  在两者都做出判向的场次上，结果 **100% 相同**（McNemar 分歧=0）——
  差异只在「覆盖范围」，不是准确率之争。

  按净收益口径（判对+1 / 判错-1 / 不判0），全样本 435 场:
    A 赔率 1.90/2.10 : 可判 371  净 +101  准确率 63.6%
    B 概率 54/46     : 可判 275  净  +85  准确率 65.5%
  → 取舍 = A 多 +16 净收益（判 100 场 58% 的"中段"），B 更保守。
  用户决策：保持现行阈值（A），但**收敛为单一真源函数**，禁止散落阈值。
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(ROOT, "scripts", "tmp")
CALC_ALL = os.path.join(TMP, "calc_all.py")


def _mod():
    if TMP not in sys.path:
        sys.path.insert(0, TMP)
    import importlib
    import calc_all
    return importlib.reload(calc_all)


def test_single_source_function_exists():
    """必须有唯一的判向函数，供所有消费点调用。"""
    m = _mod()
    assert hasattr(m, "over_under_direction"), (
        "calc_all 缺少 over_under_direction() —— 判向阈值仍在散落")


def test_thresholds_are_named_constants():
    """阈值必须是具名常量，不得内联魔法数字。"""
    m = _mod()
    assert hasattr(m, "OU_BIG_ODDS_MAX") and hasattr(m, "OU_SMALL_ODDS_MIN"), (
        "缺少 OU_BIG_ODDS_MAX / OU_SMALL_ODDS_MIN 常量")
    assert m.OU_BIG_ODDS_MAX == 1.90, m.OU_BIG_ODDS_MAX
    assert m.OU_SMALL_ODDS_MIN == 2.10, m.OU_SMALL_ODDS_MIN


def test_direction_boundaries():
    """边界语义：<1.90 大球 / >2.10 小球 / 中间中性。"""
    f = _mod().over_under_direction
    assert f(1.89) == "大球"
    assert f(1.90) == "中性", "1.90 是开区间右端，应落中性"
    assert f(2.00) == "中性"
    assert f(2.10) == "中性", "2.10 是开区间左端，应落中性"
    assert f(2.11) == "小球"
    assert f(1.00) == "大球"
    assert f(3.50) == "小球"


def test_direction_returns_neutral_on_missing():
    """缺失赔率必须三态返回「中性」，不得默认判大或判小。"""
    f = _mod().over_under_direction
    assert f(None) == "中性"
    assert f("") == "中性"


def test_no_inline_thresholds_left_in_calc_all():
    """calc_all 内不得再有内联的 1.90/2.10 判向分支（必须走单一真源）。"""
    src = open(CALC_ALL, encoding="utf-8").read()
    # 允许出现在常量定义与注释里，不允许出现在 if/else 判向表达式中
    bad = re.findall(r"_dir\s*=\s*[^\n]*<\s*1\.90", src)
    assert not bad, (
        "仍存在内联判向: %r\n应改为 over_under_direction(o25)" % bad)


def test_consumers_use_the_single_source():
    """主流程必须调用该函数（防"定义了但没人用"）。"""
    src = open(CALC_ALL, encoding="utf-8").read()
    assert "def over_under_direction" in src, "over_under_direction 尚未定义"
    body = src.split("def over_under_direction", 1)[1]
    assert "over_under_direction(" in body, (
        "over_under_direction 定义后未被任何消费点调用")