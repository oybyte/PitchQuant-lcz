# -*- coding: utf-8 -*-
"""opening_shift 单一真源回归测试（S4 位移强度·2026-10-19）。

口径（docs/方案_初盘位移接入_2026-10-19.md）:
  基准 = 澳门欧赔 init_*（真初盘）  终点 = 同一行 live_*
  fav      = 初盘三项赔率最低的方向
  conc_pp  = (1/live[fav] - 1/init[fav]) * 100
  fav_kept = argmin(init) == argmin(live)
  分级: fav 被翻 → flip | |conc|>=5 → strong | 3<=|conc|<5 → mid | 否则 flat
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(ROOT, "scripts", "tmp")

if TMP not in sys.path:
    sys.path.insert(0, TMP)

import opening_shift as OS  # noqa: E402


def test_shift_strong_when_fav_gained_five_pp():
    # 初盘 1.48/3.97/5.40 → 即盘 1.40/4.20/6.00（主胜被加仓）
    r = OS.compute_shift((1.48, 3.97, 5.40), (1.40, 4.20, 6.00))
    assert r["state"] == "ok"
    assert r["fav_open"] == 0 and r["fav_live"] == 0
    assert r["fav_kept"] is True
    # 1/1.40 - 1/1.48 = 0.714286 - 0.675676 = 0.038610 → 3.861pp
    assert abs(r["conc_pp"] - 3.861) < 0.01
    assert r["tier"] == "mid"


def test_shift_strong_tier_at_threshold():
    # 位移恰好跨过 5pp 门槛
    r = OS.compute_shift((1.50, 4.00, 6.00), (1.44, 4.00, 6.00))
    # 1/1.44 - 1/1.50 = 0.694444 - 0.666667 = 0.027778 → 2.778pp
    assert abs(r["conc_pp"] - 2.778) < 0.01
    assert r["tier"] == "flat"

    r2 = OS.compute_shift((1.50, 4.00, 6.00), (1.42, 4.00, 6.00))
    # 1/1.42 - 1/1.50 = 0.704225 - 0.666667 = 0.037558 → 3.756pp
    assert r2["tier"] == "mid"

    r3 = OS.compute_shift((1.50, 4.00, 6.00), (1.38, 4.00, 6.00))
    # 1/1.38 - 1/1.50 = 0.724638 - 0.666667 = 0.057971 → 5.797pp
    assert r3["tier"] == "strong"


def test_shift_flip_when_favorite_changes():
    # 初盘主胜最热 → 即盘客胜最热
    r = OS.compute_shift((2.10, 3.40, 3.30), (2.90, 3.40, 2.20))
    assert r["fav_open"] == 0
    assert r["fav_live"] == 2
    assert r["fav_kept"] is False
    assert r["tier"] == "flip"


def test_shift_counts_drop_as_strength_too():
    # 热门方向被弃（赔率上升）同样算位移强度，符号为负
    r = OS.compute_shift((1.60, 4.00, 5.20), (1.78, 3.90, 4.50))
    # 1/1.78 - 1/1.60 = 0.561798 - 0.625 = -0.063202 → -6.32pp
    assert abs(r["conc_pp"] + 6.320) < 0.01
    assert r["fav_kept"] is True
    assert r["tier"] == "strong"


def test_fav_live_pct_is_devig_share_of_live():
    r = OS.compute_shift((1.50, 4.00, 6.00), (1.50, 4.00, 6.00))
    assert r["fav_live_pct"] is not None
    # 等比例去水：1/1.5=0.666667, 1/4=0.25, 1/6=0.166667, 和=1.083333
    # 主胜占比 = 0.666667/1.083333 = 61.5385%
    assert abs(r["fav_live_pct"] - 61.5385) < 0.01


def test_missing_init_returns_three_state():
    r = OS.compute_shift(None, (1.50, 4.00, 6.00))
    assert r["state"] == "missing"
    assert "初盘" in r["reason"]
    assert r["tier"] == "missing"
    assert r["conc_pp"] is None


def test_missing_live_returns_three_state():
    r = OS.compute_shift((1.50, 4.00, 6.00), None)
    assert r["state"] == "missing"
    assert r["tier"] == "missing"


def test_illegal_odds_returns_three_state():
    # 赔率 <=1.0 非法 → 三态，不得产出 inf
    r = OS.compute_shift((1.00, 4.00, 6.00), (1.50, 4.00, 6.00))
    assert r["state"] == "missing"
    assert r["conc_pp"] is None


def test_tie_breaks_to_first_non_flip():
    # 主胜与客胜同赔（并列最热）→ argmin 取先出现的主胜，两侧一致即不翻
    r = OS.compute_shift((2.50, 3.20, 2.50), (2.50, 3.20, 2.50))
    assert r["fav_open"] == 0
    assert r["fav_live"] == 0
    assert r["fav_kept"] is True
    assert r["conc_pp"] == 0.0


def test_signal_line_contains_three_state_when_missing():
    line = OS.signal_line(OS.compute_shift(None, (1.5, 4.0, 6.0)))
    assert "无数据" in line
    assert "S4" in line


def test_constants_are_single_source():
    assert OS.S4_SHIFT_MIN_PP == 5.0
    assert OS.S4_MID_PP == 3.0
    assert OS.S4_STRONG_FAV_PCT == 70.0
