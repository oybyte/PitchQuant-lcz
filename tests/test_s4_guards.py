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
    # 键名必须是 s4_d1_negative_evidence：d1_heuristic_only 会与 self_iterate 的
    # 失误类型命名空间冲突（评审 C1），故本文件名已固定，旧名不得回归。
    assert "s4_d1_negative_evidence" in d, "必须登记 D1 的反证，防后人误以为它有 441 场背书"
    e = d["s4_d1_negative_evidence"]
    assert "启发式" in e["rule"]
    assert "441" in e["evidence"][0]




# ══════════ Final review 修复（2026-10-19）══════════

def test_rejects_non_finite_odds():
    """C2: inf 必须三态，不得抛 ZeroDivisionError 也不得产出假信号。

    回归：原守卫只挡 <=1.0，inf 一路走到 _devig 的 1.0/inf 求和为 0 → 除零，
    而 v259_ingest.main 逐场 try/except 会把它计成「无法转换（必须修数据源）」，
    把上游脏值误报成数据源损坏。
    """
    inf = float('inf')
    cases = [
        ((inf, inf, inf), (1.40, 4.20, 6.00)),
        ((inf, 4.0, 6.0), (1.50, 4.00, 6.00)),
        ((1.50, 4.00, 6.00), (inf, 4.00, 6.00)),
        ((1.50, 4.00, 6.00), (1.40, float('-inf'), 6.00)),
        ((1.50, float('nan'), 6.00), (1.40, 4.20, 6.00)),
    ]
    for init, live in cases:
        r = OS.compute_shift(init, live)   # 不得抛异常
        assert r["state"] == "missing", (init, live, r)
        assert r["conc_pp"] is None
        assert r["tier"] == "missing"


def test_shift_threshold_exactly_five_is_strong():
    """I3: 位移恰好 5.0pp 必须判 strong（>= 口径），不得因改成 > 而漏判。"""
    # 构造 conc 恰为 +5.0pp：init fav 赔率 2.0 → live fav = 1/(0.5+0.05) = 1.8181818...
    init = (2.0, 3.5, 4.0)
    live = (1.0 / 0.55, 3.5, 4.0)
    r = OS.compute_shift(init, live)
    assert abs(r["conc_pp"] - 5.0) < 1e-9, r["conc_pp"]
    assert r["tier"] == "strong", r["tier"]


def test_shift_threshold_exactly_three_is_mid():
    """I3: 位移恰好 3.0pp 必须判 mid（>= 口径）。"""
    init = (2.0, 3.5, 4.0)
    live = (1.0 / 0.53, 3.5, 4.0)     # 0.50 + 0.03
    r = OS.compute_shift(init, live)
    assert abs(r["conc_pp"] - 3.0) < 1e-9, r["conc_pp"]
    assert r["tier"] == "mid", r["tier"]


def test_shift_just_below_threshold_is_not_strong():
    """边界另一侧：略低于 5.0 不得判 strong（否则 >= 改成 > 也不会有测试发现）。"""
    init = (2.0, 3.5, 4.0)
    live = (1.0 / (0.55 - 1e-9), 3.5, 4.0)
    r = OS.compute_shift(init, live)
    assert r["conc_pp"] < 5.0
    assert r["tier"] == "mid", r["tier"]


def test_tie_breaks_to_first_occurrence_not_last():
    """I5: 并列最热时 argmin 必须取「先出现者」（主胜），不得取最后（客胜）。

    反例：初盘主 2.50 / 客 2.50 并列最热 → 取主胜(0)；
          即盘客胜微降到 2.49 → 客胜(2) 独热 → 热门被推翻。
          若 argmin 取最后，初盘会得客胜(2)，两边都是客胜 → fav_kept=True（漏报 flip）。
    """
    r = OS.compute_shift((2.50, 3.20, 2.50), (2.50, 3.20, 2.49))
    assert r["fav_open"] == 0, "并列最热必须取先出现者(主胜)，实得 %s" % r["fav_open"]
    assert r["fav_live"] == 2
    assert r["fav_kept"] is False
    assert r["tier"] == "flip"


def test_s4_block_uses_module_constants():
    """I2: 展示块里的阈值数字必须来自 opening_shift 常量，不得另写一份。"""
    if TMP not in sys.path:
        sys.path.insert(0, TMP)
    import calc_all as CA
    import opening_shift as OS2
    import shutil
    import tempfile

    base = os.path.join(ROOT, 'data', 'tmp', '_test_s4c')
    os.makedirs(base, exist_ok=True)
    d = tempfile.mkdtemp(dir=base)
    try:
        p = os.path.join(d, 'm.txt')
        open(p, 'w', encoding='utf-8').write(
            '🔴S4初盘位移: 客胜 -7.9pp（初盘 48.5% → 即盘 56.4%）· 热门未变 · 强度档=strong\n')
        joined = '\n'.join(CA._s4_block(p))
        assert ('≥%gpp' % OS2.S4_SHIFT_MIN_PP) in joined, joined
        assert ('%g' % OS2.S4_STRONG_FAV_PCT) in joined, joined
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_d1_negative_evidence_survives_self_iterate_bump():
    """C1: D1 反证不得被 self_iterate._bump 的「复发≥2 自动升级」覆写。

    _bump 对未知失误类型默认建 {'status':'观察'}，n>=2 时改成 '提示' 并覆盖 rule；
    而 calc_all 的提示白名单正是 ('提示','待回测验证','已固化')
    → 反证会被翻成对外发布的正向提示。键名必须与失误类型命名空间隔离。
    """
    p = os.path.join(ROOT, 'data', 'tmp', 'learned_rules.json')
    if not os.path.exists(p):
        pytest.skip("learned_rules.json 未随公开版分发")
    d = json.load(open(p, encoding='utf-8'))
    assert 'd1_heuristic_only' not in d, (
        "d1_heuristic_only 会与 self_iterate 的失误类型命名空间冲突，必须改名")
    key = 's4_d1_negative_evidence'
    assert key in d
    assert d[key]['status'] == '已证伪(大样本)'
    # 与 calc_all 白名单不相交，才是「不会被当成正向提示」的充要条件
    assert d[key]['status'] not in ('提示', '待回测验证', '已固化')
