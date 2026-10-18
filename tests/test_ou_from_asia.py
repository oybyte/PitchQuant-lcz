# -*- coding: utf-8 -*-
"""亚洲盘（含四分之一球线）→ O2.5 折算 回归测试（2026-10-17 修复批次）。

背景（本次实盘分析暴露）:
  服务端只给亚洲大小球线（2.5/3、3/3.5、3 等）+ 香港水位（0.xx）。
  项目没有把这些折成 --o25 的正式模块，执行者只能现场推导；
  首版把四分之一线的「走盘」结构写错（3.25 线上盘走盘=4 球 误写成 >=5），
  导致 22 场 O2.5 全部偏高：埃弗顿 2.39→1.67、宫崎 1.99→2.52（大球翻成小球档）。

四分之一线 = 相邻两条整球/半球线各半注：
  2.25 = 2.0 + 2.5 | 2.75 = 2.5 + 3.0 | 3.25 = 3.0 + 3.5
走盘(Push)只在整球线发生：上下盘各退回本金（EV 贡献 0）。
"""
import math
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(ROOT, 'scripts', 'tmp')


def pois(lam, k):
    return math.exp(-lam) * lam ** k / math.factorial(k)


def p_ge(lam, k):
    return 1.0 - sum(pois(lam, i) for i in range(k))


def solve(line, w_over, w_under):
    """调用被测模块。"""
    sys.path.insert(0, TMP)
    import ou_from_asia as M
    return M.solve_total_lambda(line, w_over, w_under)


# ══════════ 1. 半球线：无走盘，赌徒恒等式 P = 1/(1+w) ══════════
def test_half_line_equal_water_fair_probability():
    """2.5 线、上下水相等 → 去水 P(over) 必须恰为 1/(1+w)。"""
    sys.path.insert(0, TMP)
    import ou_from_asia as M
    w = 0.95
    lam = M.solve_total_lambda(2.5, w, w)
    assert lam is not None, "2.5 线应可解"
    p = p_ge(lam, 3)
    assert abs(p - 1 / (1 + w)) < 1e-3, (
        "2.5 线等水去水概率应为 1/(1+w)=%.4f，实得 %.4f (λ=%.4f)" % (1 / (1 + w), p, lam))


def test_half_line_35():
    """3.5 线（半球，无走盘）同构。"""
    sys.path.insert(0, TMP)
    import ou_from_asia as M
    w = 0.90
    lam = M.solve_total_lambda(3.5, w, w)
    p = p_ge(lam, 4)
    assert abs(p - 1 / (1 + w)) < 1e-3


# ══════════ 2. 整球线：走盘 EV=0 ══════════
def test_whole_line_30_push_at_three():
    """3.0 线走盘=3 球（上下盘各退本金·EV 贡献 0）。

    🔴 注意：走盘是**整注退回**，不是「半赢半输」，故等水条件为
           P(>=4) = 1/(1+w)      ← 不是 P(>=4)+0.5P(=3)
       走盘概率不进入等式——它只把分子分母同时挖掉，不影响盈亏平衡点。
       首版实现若把 push 当「0.5 权重半损」就会解出偏高的 λ（本次 2.39→应 1.67 的同型错误）。
    """
    sys.path.insert(0, TMP)
    import ou_from_asia as M
    w = 0.88
    lam = M.solve_total_lambda(3.0, w, w)
    assert lam is not None, "3.0 线应可解"
    p_win = p_ge(lam, 4)
    p_push = pois(lam, 3)
    p_lose = 1 - p_win - p_push
    ev = p_win * w - p_lose                      # 走盘贡献 0
    assert abs(ev) < 1e-3, "3.0 线 EV 未归零: %.5f（win=%.4f push=%.4f lose=%.4f）" % (
        ev, p_win, p_push, p_lose)
    # 🔴 非循环校验（闭式解·不含被测代码）:
    #    走盘在去水后必须被**整注剔除** → 条件于非走盘，上盘公平概率 = 1/(1+w)
    #      p_win / (1 - p_push) == 1/(1+w)
    cond = p_win / (1 - p_push)
    assert abs(cond - 1 / (1 + w)) < 1e-3, (
        "整球线去水后应「剔走盘后 50/50」: p(>3)/(1-p(=3))=%.4f，应=1/(1+w)=%.4f "
        "（若把 push 当半损处理，此值会偏低）" % (cond, 1 / (1 + w)))
    assert p_push > 0.05, "3.0 线在 λ=%.3f 处应有可观走盘概率，实得 %.4f" % (lam, p_push)


# ══════════ 3. 四分之一线：本批次真正出错的形状 ══════════
def test_quarter_275_splits_25_and_30():
    """2.75 = 2.5 + 3.0；等水时 EV 两半，走盘只出现在 3.0 半注。"""
    sys.path.insert(0, TMP)
    import ou_from_asia as M
    w = 0.92
    lam = M.solve_total_lambda(2.75, w, w)
    assert lam is not None
    ev25 = p_ge(lam, 3) * w - (1 - p_ge(lam, 3))
    ev30 = (p_ge(lam, 4) * w + pois(lam, 3) * 0.0
            - (1 - p_ge(lam, 4) - pois(lam, 3)))
    assert abs(0.5 * ev25 + 0.5 * ev30) < 1e-3, (
        "2.75 线 EV 未归零: 0.5*%.4f + 0.5*%.4f" % (ev25, ev30))


def test_quarter_325_push_is_four_goals_not_five():
    """3.25 = 3.0 + 3.5；3.0 半注走盘=3 球、3.5 半注无走盘（走盘=4 球是错的）。"""
    sys.path.insert(0, TMP)
    import ou_from_asia as M
    w = 0.90
    lam = M.solve_total_lambda(3.25, w, w)
    assert lam is not None, "3.25 线应可解"
    p3, p4 = pois(lam, 3), pois(lam, 4)
    ev30 = p_ge(lam, 4) * w + p3 * 0.0 - (1 - p_ge(lam, 4) - p3)
    ev35 = p_ge(lam, 4) * w - (1 - p_ge(lam, 4))
    assert abs(0.5 * ev30 + 0.5 * ev35) < 1e-3, (
        "3.25 线 EV 未归零（走盘结构写错会在此暴露）")


def test_quarter_225_splits_20_and_25():
    """2.25 = 2.0 + 2.5；2.0 半注走盘=2 球。"""
    sys.path.insert(0, TMP)
    import ou_from_asia as M
    w = 0.95
    lam = M.solve_total_lambda(2.25, w, w)
    assert lam is not None
    p2 = pois(lam, 2)
    ev20 = p_ge(lam, 3) * w + p2 * 0.0 - (1 - p_ge(lam, 3) - p2)
    ev25 = p_ge(lam, 3) * w - (1 - p_ge(lam, 3))
    assert abs(0.5 * ev20 + 0.5 * ev25) < 1e-3


def test_deep_line_475_qatari_push_at_five():
    """4.75 = 4.5 + 5.0（14场批拜仁 vs 莱比锡的真实主流线）。

    走盘只出现在 5.0 半注（=5 球），4.5 半注无走盘。
    """
    sys.path.insert(0, TMP)
    import ou_from_asia as M
    w = 0.90
    lam = M.solve_total_lambda(4.75, w, w)
    assert lam is not None, "4.75 线应可解（深盘高进球场主流线）"
    p5 = pois(lam, 5)
    ev45 = p_ge(lam, 5) * w - (1 - p_ge(lam, 5))
    ev50 = p_ge(lam, 6) * w + p5 * 0.0 - (1 - p_ge(lam, 6) - p5)
    assert abs(0.5 * ev45 + 0.5 * ev50) < 1e-3, "4.75 线 EV 未归零"


# ══════════ 4. 单调性：水分越高（赔付越大）→ λ 越低 ══════════
@pytest.mark.parametrize("line", [2.25, 2.5, 2.75, 3.0, 3.25, 3.5, 4.25, 4.5, 4.75, 5.0])
def test_monotonic_in_over_water(line):
    sys.path.insert(0, TMP)
    import ou_from_asia as M
    lo = M.solve_total_lambda(line, 0.80, 1.00)
    hi = M.solve_total_lambda(line, 1.00, 0.80)
    assert lo is not None and hi is not None
    assert lo > hi, "上盘水位升高(赔付变大)→ 期望进球应下降: %.3f vs %.3f" % (lo, hi)


# ══════════ 5. 2.5 档折算 + CLI ══════════
def test_convert_returns_o25_and_u25():
    sys.path.insert(0, TMP)
    import ou_from_asia as M
    r = M.convert(2.75, 0.82, 0.98)
    assert r['lambda'] and r['p25_over']
    assert abs(r['o25'] * r['p25_over'] - 1.0) < 1e-6, "O2.5 与 P2.5(over) 必须互为倒数"
    assert abs(r['u25'] * (1 - r['p25_over']) - 1.0) < 1e-6
    assert r['o25'] > 1.0 and r['u25'] > 1.0


def test_cli_json_output():
    r = subprocess.run(
        [sys.executable, os.path.join(TMP, 'ou_from_asia.py'),
         '--line', '2.75', '--over', '0.82', '--under', '0.98', '--json'],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        cwd=ROOT, timeout=120)
    assert r.returncode == 0, r.stderr[-500:]
    import json as _j
    d = _j.loads(r.stdout)
    assert set(['lambda', 'p25_over', 'o25', 'u25', 'line']) <= set(d), d


def test_cli_rejects_unknown_line():
    """未覆盖的线型必须显式拒绝，不得静默给默认值。"""
    # 🔴2026-10-17: 原用例拿 4.75 当「未覆盖线型」，但 14场批（拜仁 vs 莱比锡）
    #   证明 4.75 是真实主流线，已登记进 LINES → 改用确实不存在的 9.25。
    r = subprocess.run(
        [sys.executable, os.path.join(TMP, 'ou_from_asia.py'),
         '--line', '9.25', '--over', '0.90', '--under', '0.90'],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        cwd=ROOT, timeout=120)
    combined = r.stdout + r.stderr
    assert '不支持' in combined, "未覆盖线型应显式报「不支持」: " + combined[-300:]
    assert r.returncode != 0, "拒绝未覆盖线型时退出码须非0"
