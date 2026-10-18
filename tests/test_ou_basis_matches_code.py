# -*- coding: utf-8 -*-
"""大小球判向「依据 vs 实现」一致性 回归测试（2026-10-17）。

背景:
  435 场复核（441 场盲测批次去重）发现两件事:
  · "判大球 68.5%" 描述的是一批 **over_p 概率分类器**（over_p>=54→判大 / <=46→判小）的结果；
  · 但 calc_all.py 现行实现用 **O2.5 赔率阈值**（<1.90→大球 / >2.10→小球 / 中间→中性）。
  两者在 435 场里对 **99 场（22.8%）** 给出不同判向。

  按现行代码口径重算为 判大 316 场 64.9% / 判小 55 场 56.4%，
  而输出仍打印 "判大球命中 68.5%(n=235)" → **打印的依据不描述实际执行的规则**。

本测试锁住: 输出里引用的口径/样本量必须与实际实现的判据一致。
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(ROOT, "scripts", "tmp")
CALC_ALL = os.path.join(TMP, "calc_all.py")


def _src():
    return open(CALC_ALL, encoding="utf-8").read()


def _threshold_dir_rule(_src=None):
    """取出实现里判向的实际阈值。

    2026-10-18 更新：判向已收敛为单一真源 over_under_direction() +
    具名常量 OU_BIG_ODDS_MAX / OU_SMALL_ODDS_MIN（见 tests/test_ou_single_source.py），
    不再有内联的 <1.90/>2.10 表达式 → 改为直接读常量（比正则抓表达式更稳）。
    """
    import importlib
    import sys
    TMP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "tmp")
    if TMP not in sys.path:
        sys.path.insert(0, TMP)
    m = importlib.reload(__import__("calc_all"))
    return (float(m.OU_BIG_ODDS_MAX), float(m.OU_SMALL_ODDS_MIN))


def test_basis_string_matches_threshold_rule():
    """判据是 O2.5 赔率阈值时，输出不得再引用概率分类器的 68.5%/235 场。"""
    src = _src()
    thr = _threshold_dir_rule(src)
    assert thr is not None, (
        "未找到 _dir 的 O2.5 阈值实现；若已改为概率分类器，请同步更新本测试")
    big_thr, small_thr = thr
    has_prob_numbers = ("68.5" in src) or ("235" in src)
    assert not has_prob_numbers, (
        "calc_all.py 仍引用「68.5%/235 场」——那是 over_p 概率分类器的口径，"
        "而实现用的是 O2.5 赔率阈值({:.2f}/{:.2f})，两者对 22.8% 的场次给出不同判向。\n"
        "请改为打印赔率阈值口径的实测数字。".format(big_thr, small_thr))


def test_basis_cites_threshold_not_probability():
    """判大球依据行必须能看出是按赔率阈值判的。"""
    src = _src()
    assert "O2.5" in src and "<1.90" in src, ("判据应写明 O2.5<1.90 这类可审计的阈值")


def test_small_ball_neutral_branch_kept():
    """小球档停判开关必须保留（该结论本身未被推翻）。"""
    src = _src()
    assert "SMALL_BALL_NEUTRAL" in src, "小球档停判开关被删 → 会退回判小球(约50%随机)"