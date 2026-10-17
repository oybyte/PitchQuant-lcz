# -*- coding: utf-8 -*-
"""calc_poisson 亚盘约束口径 回归测试（2026-10-17 第二轮复跑发现）。

已复现缺陷（真实 22 场复跑暴露）:
  calc_poisson.solve_lambda(..., handi=X) 把亚盘当作 λ 的**全量覆盖**：
      d = -handi * 0.6
      lh = (t + d)/2 ; la = (t - d)/2      ← 直接用盘口重算 λ 差，丢弃欧赔已反推的分配
  后果（实测 23/23 场全部被改动）:
      · 曼城 vs 伊普斯维奇（亚盘 -2.00）：λ 2.94/0.83 → 2.49/1.29，主胜隐含 -16.1pp
      · 比利亚雷亚尔 vs 埃尔切（-1.25）：2.43/1.04 → 2.11/1.36，-13.0pp
      · 富勒姆 vs 赫尔城（-0.75）：2.00/1.01 → 1.73/1.28，-12.3pp
      · 平手盘（布伦特福德、宫崎、埃弗斯堡）→ λ 被强制拉成**完全对称**，抹掉欧赔的主队信息
  而函数注释自称「亚盘净胜微调·clamp 总进球不变」——实现与声明不符。

正确口径:
  λ 的**方向信息来自欧赔**（1X2 去水已是市场主客强弱的完整表达）；
  亚盘只应作为**轻微校正**，且必须有幅度上限——不能覆盖欧赔。
"""
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(ROOT, 'scripts', 'tmp')


def snippet(code, timeout=120):
    env = dict(os.environ, PYTHONPATH=TMP, PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", cwd=ROOT, env=env,
                          timeout=timeout)


def _lam(code):
    r = snippet(code)
    assert "LAM" in r.stdout, r.stdout + r.stderr
    parts = r.stdout.split("LAM")[-1].split()
    return float(parts[0]), float(parts[1])


BASE = "import sys; sys.path.insert(0, %r); import calc_poisson as C" % TMP


def _run(expr):
    return _lam(BASE + chr(10) + "print(chr(76)+chr(65)+chr(77), *%s)" % expr + chr(10))


# ══════════ 1. 平手盘不得抹掉欧赔的主客差异 ══════════
def test_level_handicap_preserves_odds_asymmetry():
    """平手盘不得把 λ 强制对称——欧赔的方向信息必须保留。

    用例 2.74/3.56/2.41：客赔最低 → 市场偏客，欧赔反推 λa > λh。
    平手盘(handi=0)只应「不校正」，不得把 λ 拉平。
    """
    a = _run("C.solve_lambda(2.74, 3.56, 2.41, 1.58, 2.71)")
    b = _run("C.solve_lambda(2.74, 3.56, 2.41, 1.58, 2.71, handi=0)")
    assert abs(b[0] - b[1]) > 1e-6, (
        "平手盘把 λ 强制拉成对称 %.4f/%.4f——欧赔的主客信息被抹掉" % b)
    # 方向须与欧赔一致：客赔 2.41 最低 → λa > λh
    assert b[1] > b[0], (
        "平手盘后 λa(%.3f) 未大于 λh(%.3f)，与欧赔「客赔最低」方向相反" % (b[1], b[0]))
    assert abs(b[0] - a[0]) < 0.05, "平手盘不应改变 λ：%s → %s" % (a, b)


# ══════════ 2. 亚盘只能是「微调」，不得覆盖欧赔 ══════════
@pytest.mark.parametrize("handi", [-2.0, -1.25, -0.75, -0.5, 0.25, 0.75, 1.5, 2.0])
def test_handicap_is_adjustment_not_override(handi):
    """任何盘口下，λ 相对无盘口解的变化都应受限（<=0.35 球/边）。"""
    a = _run("C.solve_lambda(2.74, 3.56, 2.41, 1.58, 2.71)")
    b = _run("C.solve_lambda(2.74, 3.56, 2.41, 1.58, 2.71, handi=%s)" % handi)
    assert abs(b[0] - a[0]) <= 0.35, (
        "亚盘 %+.2f 把 λh 从 %.3f 改到 %.3f（Δ=%.3f），不是微调而是覆盖"
        % (handi, a[0], b[0], abs(b[0] - a[0])))
    assert abs(b[1] - a[1]) <= 0.35


# ══════════ 3. 方向一致性：亚盘不应把 λ 差反转 ══════════
def test_handicap_does_not_flip_lambda_direction():
    """亚盘不得反转欧赔给出的 λ 方向（此处市场偏客，λa 应始终 > λh）。"""
    base = _run("C.solve_lambda(2.74, 3.56, 2.41, 1.58, 2.71)")
    for h in (-2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0):
        b = _run("C.solve_lambda(2.74, 3.56, 2.41, 1.58, 2.71, handi=%s)" % h)
        assert (b[1] > b[0]) == (base[1] > base[0]), (
            "亚盘 %+.2f 把 λ 主客方向反转了: base=%.3f/%.3f -> %.3f/%.3f"
            % (h, base[0], base[1], b[0], b[1]))


# ══════════ 4. 总进球不变（原设计承诺）══════════
def test_total_goals_unchanged_by_handicap():
    a = _run("C.solve_lambda(2.74, 3.56, 2.41, 1.58, 2.71)")
    b = _run("C.solve_lambda(2.74, 3.56, 2.41, 1.58, 2.71, handi=-1.0)")
    assert abs((a[0] + a[1]) - (b[0] + b[1])) < 0.02, (
        "亚盘改动总进球: %.3f → %.3f" % (a[0] + a[1], b[0] + b[1]))

# ══════════ P0(第2轮): 去水/隐含行必须跟随 --eu ══════════
def test_devig_line_follows_eu_source():
    """传 --eu 时，「去抽水率/隐含」必须用欧盘口径，不能仍打印竞彩 txt。

    历史缺陷: 同一段里「隐含」用竞彩、「skew」用 --eu，两个源混排。
    实测布伦特福德 vs 利物浦：澳门基线 41.1/23.5/35.4，Pinnacle 基线也逐字相同，
    但 skew 却是 39.1/34.4（Pinnacle 真实值）。
    """
    txt = os.path.join(ROOT, "tests", "fixtures", "everton-chelsea-EPL.txt")
    r = subprocess.run(
        [sys.executable, os.path.join(TMP, "calc_match.py"), txt, "英超",
         "--eu", "3.17,3.70,2.23", "--handi", "0.25"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=os.path.dirname(ROOT), timeout=180)
    lines = [l.strip() for l in r.stdout.splitlines() if "隐含:" in l]
    assert lines, r.stdout[-600:]
    # 欧盘 3.17/3.70/2.23 去水 = 主30.5/平26.1/客43.4（竞彩 2.80/3.66/2.06 会是别的值）
    assert "30.5%" in lines[0] and "43.4%" in lines[0], (
        "去水/隐含未跟随 --eu（仍在用竞彩 txt）: " + lines[0])
    assert "欧盘" in lines[0], "未标出去水口径来源: " + lines[0]

# ══════════ P0(第2轮): direction_full 依据不得虚假溯源 ══════════
K_MAIN = "\u4e3b\u65b9\u5411"     # 主方向
K_H = "\u4e3b\u80dc"               # 主胜
K_D = "\u5e73\u5c40"               # 平局
K_A = "\u5ba2\u80dc"               # 客胜
K_EV = "\u4f9d\u636e"              # 依据


BASE_V3 = "import sys; sys.path.insert(0, %r); import calc_v3572 as C" % TMP


def _call(oh, od, oa, o25):
    code = (BASE_V3 + chr(10)
            + "d = C.direction_full(%s, %s, %s, %s)" % (oh, od, oa, o25) + chr(10)
            + "print(chr(68)+chr(73)+chr(82), d[%r], d[%r], d[%r], d[%r])" % (K_MAIN, K_H, K_D, K_A) + chr(10)
            + "print(chr(69)+chr(86), d[%r])" % K_EV + chr(10))
    r = snippet(code)
    assert "DIR" in r.stdout and "EV" in r.stdout, r.stdout + r.stderr
    dline = r.stdout.split("DIR")[-1].split(chr(10))[0].split()
    evline = r.stdout.split("EV")[-1].strip()
    return dline[0], float(dline[1]), float(dline[2]), float(dline[3]), evline


def test_direction_full_evidence_has_no_false_odds_table_claim():
    """`依据` 曾恒写「odds_table档位校准」，但该函数内并无查表逻辑。

    odds_table.json 仅覆盖五大联赛 35 档，且不在 direction_full 调用链上；
    日职乙等非五大场次也照样声称「odds_table档位校准」→ 虚假溯源。
    """
    *_, ev = _call(2.48, 3.03, 2.55, 2.521)
    stripped = ev.replace("\u672a\u67e5 odds_table", "")   # 去掉如实声明的「未查」
    assert "odds_table" not in stripped, "依据仍声称做了 odds_table 档位校准: " + ev
    assert "prob_calibration" in ev, "依据未标出实际生效的概率校准: " + ev


@pytest.mark.parametrize("oh,od,oa,o25", [
    (2.48, 3.03, 2.55, 2.521),
    (2.25, 3.97, 2.40, 1.461),
    (2.74, 3.56, 2.41, 1.58),
    (1.42, 4.35, 5.60, 1.73),
    (6.00, 5.40, 1.32, 1.33),
])
def test_direction_matches_max_probability(oh, od, oa, o25):
    """主方向必须是主/平/客三向概率的最大者（strict 口径自洽）。"""
    direction, h, dr, a, _ev = _call(oh, od, oa, o25)
    expect = max([(h, "\u4e3b\u80dc"), (dr, "\u5e73\u5c40"), (a, "\u5ba2\u80dc")])[1]
    assert direction == expect, (
        "方向 %s 与最大概率 %s（主%.1f/平%.1f/客%.1f）不符" % (direction, expect, h, dr, a))

# ══════════ P0(第2轮): 锚必须与方向引擎互证 ══════════
def test_anchor_check_detects_direction_conflict():
    """方向=客胜但主锚/次锚都是主胜/平局 → 必须判冲突（原实现完全看不见方向）。

    实测 宫崎 vs 磐田(方向=客胜): 锚 1:1/1:0 仍报「✅ 均落在市场约束内」。
    """
    code = (BASE_V3.replace("calc_v3572 as C", "live_score_engine as L") + chr(10)
            + "r = L.anchor_market_check([\"1:1\", \"1:0\"], 2.48, 3.03, 2.55,"
            + " o25=2.52, handi=0, direction=\"\\u5ba2\\u80dc\")" + chr(10)
            + "print(chr(79)+chr(75), r[\"ok\"])" + chr(10)
            + "print(chr(86)+chr(73), len(r[\"violations\"]))" + chr(10)
            + "print(chr(72)+chr(65), any(\"\\u786c\\u51b2\\u7a81\" in c for c in r[\"conflicts\"]))" + chr(10))
    r = snippet(code)
    assert "OK False" in r.stdout, "方向冲突未被识别: " + r.stdout + r.stderr
    assert "HA True" in r.stdout, "未标记「方向-锚硬冲突」（两锚均不含判定方向）: " + r.stdout


def test_anchor_check_passes_when_anchor_matches_direction():
    """主锚落在判定方向内时，「方向-锚」这条不应触发（其他约束可能仍在）。

    用 1:1(平局) + direction=平局 的组合，隔离出「方向」这一维。
    """
    code = (BASE_V3.replace("calc_v3572 as C", "live_score_engine as L") + chr(10)
            + "r = L.anchor_market_check([\"1:1\", \"2:2\"], 2.48, 3.03, 2.55,"
            + " o25=2.52, handi=0, direction=\"\\u5e73\\u5c40\")" + chr(10)
            + "rules = [v[\"rule\"] for v in r[\"violations\"]]" + chr(10)
            + "print(chr(68)+chr(73), sum(1 for x in rules if \"\\u65b9\\u5411\\u5f15\\u64ce\" in x))" + chr(10)
            + "print(chr(72)+chr(65), any(\"\\u786c\\u51b2\\u7a81\" in c for c in r[\"conflicts\"]))" + chr(10))
    r = snippet(code)
    assert "DI 0" in r.stdout, "锚已是平局且方向=平局，方向维度不应判违反: " + r.stdout + r.stderr
    assert "HA False" in r.stdout, "不应报方向-锚硬冲突: " + r.stdout

# ══════════ 第三轮: 候选参考不得违反方向 ══════════
def test_suggestion_respects_direction():
    """「约束内候选参考」必须落在方向引擎判定内。

    实测缺陷: 方向=主胜时仍给出 1:1(平局) 作为候选，与同批 violations 自相矛盾。
    """
    code = (BASE_V3.replace("calc_v3572 as C", "live_score_engine as L") + chr(10)
            + "r = L.anchor_market_check([\"1:1\", \"2:1\", \"2:0\", \"1:0\"], 1.42, 4.35, 5.60,"
            + " o25=1.73, handi=-1.0, direction=\"\\u4e3b\\u80dc\")" + chr(10)
            + "print(chr(83), \",\".join(r[\"suggestion\"]))" + chr(10))
    r = snippet(code)
    assert "S " in r.stdout, r.stdout + r.stderr
    sug = r.stdout.split("S ", 1)[1].strip()
    assert sug, "未给出任何候选参考"
    for sc in sug.split(","):
        h, a = map(int, sc.split(":"))
        assert h > a, "方向=主胜，候选参考却给了 %s（非主胜）" % sc


def test_suggestion_respects_direction_away():
    """客胜方向同理。"""
    code = (BASE_V3.replace("calc_v3572 as C", "live_score_engine as L") + chr(10)
            + "r = L.anchor_market_check([\"1:1\", \"0:1\", \"1:2\"], 2.48, 3.03, 2.55,"
            + " o25=2.52, handi=0, direction=\"\\u5ba2\\u80dc\")" + chr(10)
            + "print(chr(83), \",\".join(r[\"suggestion\"]))" + chr(10))
    r = snippet(code)
    assert "S " in r.stdout, r.stdout + r.stderr
    sug = r.stdout.split("S ", 1)[1].strip()
    assert sug, "未给出任何候选参考"
    for sc in sug.split(","):
        h, a = map(int, sc.split(":"))
        assert a > h, "方向=客胜，候选参考却给了 %s（非客胜）" % sc
