# -*- coding: utf-8 -*-
"""S4 口径守卫（2026-10-19·三次踩坑的固化）。

三个坑（docs/方案_初盘位移接入_2026-10-19.md §3.2）:
  1. 不同量纲相减（覆盖率概率 − 胜率）→ 交叉特征必须同定义
  2. 亚盘原始盘口符号与 handi 相反 → 本模块不碰亚盘，碰到即拒绝
  3. 用处理后变量（即盘）做控制变量 → 分层必须用事前变量
"""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(ROOT, "scripts", "tmp")

if TMP not in sys.path:
    sys.path.insert(0, TMP)

import opening_shift as OS  # noqa: E402


def test_compute_shift_rejects_asian_line_input():
    """亚盘盘口带负数与水位，误传为欧赔三元组必须被拒绝，不得算出数字。"""
    r = OS.compute_shift((-0.75, 0.83, 1.01), (1.48, 3.97, 5.40))
    assert r["state"] == "missing"
    assert r["conc_pp"] is None


def test_compute_shift_rejects_wrong_arity():
    r = OS.compute_shift((1.48, 3.97), (1.48, 3.97, 5.40))
    assert r["state"] == "missing"


def test_compute_shift_rejects_non_numeric():
    r = OS.compute_shift(("1.48", "abc", "5.40"), (1.48, 3.97, 5.40))
    assert r["state"] == "missing"


def test_learned_rules_records_d1_negative_evidence():
    p = os.path.join(ROOT, "data", "tmp", "learned_rules.json")
    if not os.path.exists(p):
        pytest.skip("learned_rules.json 未随公开版分发")
    d = json.load(open(p, encoding="utf-8"))
    assert "d1_heuristic_only" in d, "必须登记 D1 的反证，防后人误以为它有 441 场背书"
    e = d["d1_heuristic_only"]
    assert "启发式" in e["rule"]
    assert "441" in e["evidence"][0]
