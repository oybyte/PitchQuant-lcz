# -*- coding: utf-8 -*-
"""水位标度/让球符号 同根因其余落点回归测试 (2026-09-15 修复批次 2)。

承 Bug2/Bug3 同一根因 —— 全仓只有一个水位标度(欧式 1.8-2.1)与一个让球符号口径(负=主让),
先前只修了 match_classifier, 其余落点未修 = 只治症状。本文件覆盖其余 4 处:
  W1 calc_v3572.direction_full  D6 高水判据 home_water > 1.0 (欧式下恒真)
  W2 calc_v3572.water_level_anomaly  单时点/升降 判据 0.95 / 0.75 (澳门)
  W3 calc_v3572.handicap_movement_analyzer 水位判据 0.9 (澳门) + 升/降盘符号反向
  W4 europe_group_stage.detect_trap 深盘超低水判据 0.8 (澳门)

标度真源: skills/SK-model-v3-analysis/SKILL.md L383-387 水位意图量化表
  主水位1.8-2.1体系: 低水<1.85 / 中水 1.85-2.05 / 高水>2.05
  标度外(如澳门 0.7-1.1) = 非本仓口径 → 不参与并显式标注(三态), 禁当欧式实值误用
  佐证: skills/SL-water-intent 信号E(亚盘水位 hdp=-0.5 上盘 1.9→2.025)
让球符号真源: calc_v3572 L70 --handi 帮助「负=主让」+ margin_candidates(L536-555) 同口径
"""
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(ROOT, "scripts", "tmp")


def snippet(code, timeout=120):
    env = dict(os.environ, PYTHONPATH=TMP, PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", cwd=ROOT, env=env, timeout=timeout)


# W1: direction_full D6 高水判据用欧式标度
@pytest.mark.parametrize("water,expect_d6", [
    (1.84, False),   # 欧式低水 → 非高水 (原: 1.84>1.0 恒触发)
    (1.86, False),   # 欧式中水 → 非高水 (原: 恒触发)
    (2.00, False),   # 中水中段   → 非高水 (原: 恒触发)
    (2.05, False),   # 高水边界(不含)
    (2.10, True),    # 欧式高水 → 触发 (与量化表 >2.05 一致)
    (0.90, False),   # 澳门标度(标度外) → 不参与 → 不触发
])
def test_direction_full_d6_high_water_uses_decimal_scale(water, expect_d6):
    """D6 高水(平手/客浅)判据必须用欧式 1.8-2.1: 高水 = home_water > 2.05。
    原实现 home_water > 1.0 在欧式标度下【恒真】→ 任何真实水位都触发 D6 主胜降权。"""
    code = ("import sys; sys.path.insert(0, %r);"
            "from calc_v3572 import direction_full;"
            "r=direction_full(1.80,3.50,4.20,handi=0.0,home_water=%r);"
            "k=chr(25191)+chr(34892)+chr(25552)+chr(31034);"
            "h=[x for x in r.get(k,[]) if chr(68)+chr(54) in x];"
            "print(1 if h else 0)") % (TMP, water)
    r = snippet(code)
    got = r.stdout.strip()
    assert got == ("1" if expect_d6 else "0"), (
        "water=%s 期望D6触发=%s 实得「%s」| %s" % (water, expect_d6, got, r.stderr[-200:]))


# W2: water_level_anomaly 单时点标度 + 升降标签
@pytest.mark.parametrize("water,expect_word", [
    (1.80, "低"),      # 欧式超低水 → 阻盘/真实看好 (原: 恒判高水诱盘)
    (1.84, "低"),
    (1.86, "正常"),    # 中水区
    (2.05, "正常"),    # 中水区边界
    (2.10, "高"),      # 欧式高水 → 诱盘 (两版一致·保护回归)
])
def test_water_level_anomaly_single_timepoint_decimal(water, expect_word):
    """单时点降级分支: 低水<1.85 / 中水 / 高水>2.05。原判据 0.95/0.75 是澳门标度,
    欧式任何真实水位都 >0.95 → 恒判「高水诱盘信号」(信号恒亮=等于没有信号)。"""
    code = ("import sys; sys.path.insert(0, %r);"
            "from calc_v3572 import water_level_anomaly as f;"
            "print(f(None,%r)[chr(26631)+chr(31614)])") % (TMP, water)
    r = snippet(code)
    got = r.stdout.strip()
    assert expect_word in got, (
        "water=%s 期望标签含「%s」实得「%s」| %s" % (water, expect_word, got, r.stderr[-200:]))


def test_water_level_anomaly_out_of_scale_not_participating():
    """澳门标度(0.7-1.1)输入不是本仓口径 → 显式标注不参与, 不得当欧式实值使用。"""
    code = ("import sys; sys.path.insert(0, %r);"
            "from calc_v3572 import water_level_anomaly as f;"
            "print(f(None,0.90)[chr(26631)+chr(31614)])") % TMP
    r = snippet(code)
    assert ("标度" in r.stdout) or ("不参与" in r.stdout), (
        "澳门标度 0.90 未被标注不参与: %s" % r.stdout.strip())


def test_water_level_anomaly_rise_fall_labels():
    """初盘→临场: 升水(1.90→2.10)=诱盘; 降水(2.10→1.90)=真实看好。
    原实现两条分支都只看 water_live>0.95 → 降水也被标成「升水·诱盘信号」(升降不分)。"""
    code = ("import sys; sys.path.insert(0, %r);"
            "from calc_v3572 import water_level_anomaly as f;"
            "k=chr(26631)+chr(31614);"
            "print(f(1.90,2.10)[k]);print(f(2.10,1.90)[k])") % TMP
    r = snippet(code)
    out = [l.strip() for l in r.stdout.splitlines() if l.strip()]
    assert len(out) >= 2, "water_level_anomaly 未输出两行: %s | %s" % (r.stdout, r.stderr[-200:])
    assert ("升水" in out[0]) and ("诱盘" in out[0]), "升水(1.90→2.10)应标升水·诱盘 实得「%s」" % out[0]
    assert ("降水" in out[1]) and ("真实" in out[1]), "降水(2.10→1.90)应标降水·真实看好 实得「%s」" % out[1]


# W3: handicap_movement_analyzer 升降符号(负=主让) + 欧式水位
def test_handicap_movement_analyzer_rise_sign_uses_negative_home_handi():
    """负=主让(calc_v3572 L70): 让球由 -0.5 变 -1.0 = 主让【加深】= 升盘。
    原实现 chg=h_live-h_init=-0.5<0 落入 else → 误判「降盘」(方向反)。"""
    code = ("import sys; sys.path.insert(0, %r);"
            "from calc_v3572 import handicap_movement_analyzer as f;"
            "r=f(-0.5,-1.0,None,1.84);"
            "print(r[chr(21464)+chr(21160)]);print(r[chr(27169)+chr(24335)])") % TMP
    r = snippet(code)
    out = [l.strip() for l in r.stdout.splitlines() if l.strip()]
    assert len(out) >= 2, "未输出: %s | %s" % (r.stdout, r.stderr[-200:])
    assert ("升" in out[0]) and ("降" not in out[0]), (
        "主让 -0.5→-1.0 是升盘(加深) 实得「%s」" % out[0])


@pytest.mark.parametrize("w_live,expect_word", [
    (1.84, "阻上"),   # 升盘+欧式低水(<1.85) → 阻上·真实看好 (原 0.9 澳门标度下 1.84>0.9 恒判诱下)
    (2.10, "诱下"),   # 升盘+欧式高水(>2.05) → 诱下
])
def test_handicap_movement_analyzer_decimal_water(w_live, expect_word):
    """升盘搭配水位须用欧式标度: 低水<1.85 / 高水>2.05 (原 0.9 是澳门标度)。"""
    code = ("import sys; sys.path.insert(0, %r);"
            "from calc_v3572 import handicap_movement_analyzer as f;"
            "print(f(-0.5,-1.0,None,%r)[chr(27169)+chr(24335)])") % (TMP, w_live)
    r = snippet(code)
    assert expect_word in r.stdout, (
        "升盘+水位%s 期望「%s」实得「%s」" % (w_live, expect_word, r.stdout.strip()))


# W4: europe_group_stage 深盘超低水标度
@pytest.mark.parametrize("water,expect_trap", [
    (1.82, True),    # 欧式超低水(<1.85) → 深盘超低水诱盘
    (1.90, False),   # 欧式常规水 → 不触发
    (0.80, False),   # 澳门标度(标度外) → 不参与(禁当欧式实值误判)
])
def test_europe_group_stage_deep_low_water_scale(water, expect_trap):
    """detect_trap「深盘超低水诱盘」原判据 home_water<0.8 是澳门标度,
    与全仓 1.8-2.1 冲突 → 欧式真实水位永不触发(信号恒灭=等于没有信号)。"""
    code = ("import sys; sys.path.insert(0, %r);"
            "from europe_group_stage import detect_trap as f;"
            "t=f(1.35,8.0,chr(45)+chr(49)+chr(46)+chr(53),chr(72)+chr(73)+chr(71)+chr(72),chr(76)+chr(79)+chr(87),%r);"
            "print(1 if any(chr(35825)+chr(30424) in x.get(chr(116)+chr(121)+chr(112)+chr(101),chr(32)) for x in t) else 0)") % (TMP, water)
    r = snippet(code)
    got = r.stdout.strip()
    assert got == ("1" if expect_trap else "0"), (
        "water=%s 期望诱盘=%s 实得「%s」| %s" % (water, expect_trap, got, r.stderr[-300:]))


# ── W5: 欧式低水可低于 1.8 (回归·德乙本场实测触发) ────────────────
@pytest.mark.parametrize("water", [1.60, 1.72, 1.75, 1.79, 1.80, 1.84])
def test_low_decimal_water_below_1_8_still_participates(water):
    """欧式低水可 <1.8: 澳门/香港 0.60-0.80 加1 = 1.60-1.80。
    量化表「低水<1.85」无下界 → 1.79(澳门0.79) 是合法低水, 必须参与且判「低」。
    原下界把 1.79 误判为「标度外·不参与」→ 低水升档信号丢失(德乙本场实测)。"""
    code = ("import sys; sys.path.insert(0, %r);"
            "from calc_v3572 import water_in_scale as ins, water_level_tag as tag;"
            "print(ins(%r)); print(tag(%r))") % (TMP, water, water)
    r = snippet(code)
    out = [l.strip() for l in r.stdout.splitlines() if l.strip()]
    assert len(out) >= 2, "未输出: %s | %s" % (r.stdout, r.stderr[-200:])
    assert out[0] == "True", ("欧式低水 %.2f 被判标度外(下界过紧) → 水位信号丢失" % water)
    assert out[1] == "低", "欧式低水 %.2f 应判「低」实得「%s」" % (water, out[1])


@pytest.mark.parametrize("water", [0.79, 0.90, 1.10])
def test_macau_scale_still_rejected_after_widening(water):
    """加宽下界不得削弱缺陷拦截能力: 澳门原始值仍须判标度外。
    两标度间存在空档(澳门<=1.15, 欧式>=1.60) → 分界取 1.5 可兼顾两侧。"""
    code = ("import sys; sys.path.insert(0, %r);"
            "from calc_v3572 import water_in_scale as ins; print(ins(%r))") % (TMP, water)
    r = snippet(code)
    assert r.stdout.strip() == "False", (
        "澳门标度 %.2f 应判标度外(参与则标度混淆复发) 实得「%s」" % (water, r.stdout.strip()))
