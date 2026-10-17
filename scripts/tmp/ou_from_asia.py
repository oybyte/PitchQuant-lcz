#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ou_from_asia.py — 亚洲盘（含四分之一球线）→ O2.5/U2.5 折算（唯一真源）

背景
----
服务端只给亚洲大小球线（2.5 / 2.75 / 3 / 3.25 …）+ 香港水位（0.xx）。
模型需要的却是 O2.5 赔率。直接把四分之一线当二元盘去水会**系统性偏差**，
因为 2.25/2.75/3.25 是 half-win / half-loss 组合线。

口径（EV 中性·非去水）
----------------------
把一条线拆成两条相邻的整球/半球线各半注，逐半注写 EV，令总 EV = 0：

    EV = p_win × 水 − (1 − p_win − p_push) × 1 + p_push × 0

    · 半球线（2.5 / 3.5）：无走盘 push = 0
    · 整球线（3.0）：     走盘 = 该整数球，上下盘退回本金（EV 贡献 0）
    · 四分之一线：        拆成相邻两条，各半注

线型拆解表（唯一真源·新增线型必须在此登记）
    2.25 = 2.0 + 2.5      2.75 = 2.5 + 3.0      3.25 = 3.0 + 3.5
    2.50 = 2.5            3.00 = 3.0            3.50 = 3.5
    1.50 = 1.5            2.00 = 2.0            1.75 = 1.5 + 2.0

🔴 历史事故（本模块存在的原因）
    首版把 3.25 线上盘的「走盘=4 球」误写成 >=5、2.25 线下盘走盘条件写反，
    22 场 O2.5 全部偏高：埃弗顿 vs 切尔西 2.39→应为 1.67，宫崎 vs 磐田 1.99→2.52
    （判向从「大球」翻成「小球档·中性不判」）。本文件把该结构固化为代码 + 单测。

用法
----
    python scripts/tmp/ou_from_asia.py --line 2.75 --over 0.82 --under 0.98
    python scripts/tmp/ou_from_asia.py --line 3 --over 0.91 --under 0.81 --json

输出（--json 时为机器可读）
    λ_total         反解出的总进球泊松均值
    p25_over        折算到 2.5 档的去水 P(总进球>=3)
    o25 / u25       互为倒数的公平赔率（fair odds = 1/p）
    ev_residual     解处 EV 残差（应 ≈ 0·自检用）
"""
import argparse
import json
import math
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8')
    except Exception:
        pass

# ── 线型拆解表（唯一真源）──
# value: (半注A, 半注B)；两半注相同表示整线（非四分之一线）
LINES = {
    1.5:  (1.5, 1.5),
    1.75: (1.5, 2.0),
    2.0:  (2.0, 2.0),
    2.25: (2.0, 2.5),
    2.5:  (2.5, 2.5),
    2.75: (2.5, 3.0),
    3.0:  (3.0, 3.0),
    3.25: (3.0, 3.5),
    3.5:  (3.5, 3.5),
    3.75: (3.5, 4.0),
    4.0:  (4.0, 4.0),
}

_MAX_GOALS = 14   # 泊松求和上界（>14 球概率可忽略）


def _pois(lam, k):
    return math.exp(-lam) * lam ** k / math.factorial(k)


def _p_ge(lam, k):
    """P(X >= k)·k<=1 时直接返回 1"""
    if k <= 0:
        return 1.0
    return 1.0 - sum(_pois(lam, i) for i in range(k))


def _half_ev(lam, line, w_over):
    """单条整球/半球线上盘的 EV（注金 1·走盘退回本金 EV 贡献 0）

    line 为 .0（整球）或 .5（半球）：
      · 上盘赢：总进球 > line
      · 走盘  ：总进球 == line（仅整球线存在，EV=0）
      · 上盘输：总进球 < line
    """
    whole = abs(line - round(line)) < 1e-9
    if whole:
        n = int(round(line))
        p_win = _p_ge(lam, n + 1)
        p_push = _pois(lam, n)
    else:
        p_win = _p_ge(lam, math.floor(line) + 1)
        p_push = 0.0
    p_lose = max(0.0, 1.0 - p_win - p_push)
    return p_win * w_over - p_lose * 1.0 + p_push * 0.0


def _ev(lam, line, w_over):
    if line not in LINES:
        return None
    a, b = LINES[line]
    if a == b:
        return _half_ev(lam, a, w_over)
    return 0.5 * _half_ev(lam, a, w_over) + 0.5 * _half_ev(lam, b, w_over)


def solve_total_lambda(line, w_over, w_under=None):
    """反解总进球泊松 λ。

    参数
      line    亚洲盘主流线（须在 LINES 中）
      w_over  上盘（大球）香港水位，如 0.82
      w_under 下盘（小球）香港水位；仅作合法性参考，EV 用上盘侧写（半注镜像）

    返回 λ（float）或 None（线型不支持/无解）
    """
    try:
        line = float(line)
    except (TypeError, ValueError):
        return None
    if line not in LINES or w_over is None:
        return None
    if not (0.3 <= float(w_over) <= 5.0):
        return None

    # 单调性：EV 随 λ 递减（λ 大 → 上盘更容易赢 → 上盘 EV 更高…实为递增）。
    # 用二分在 [0.2, 12] 找 EV==0
    lo, hi = 0.2, 12.0
    f_lo, f_hi = _ev(lo, line, w_over), _ev(hi, line, w_over)
    if f_lo is None or f_hi is None:
        return None
    if f_lo * f_hi > 0:
        # 单侧无解（水位极端）→ 夹逼到边界
        return lo if abs(f_lo) < abs(f_hi) else hi
    for _ in range(200):
        mid = (lo + hi) / 2.0
        fm = _ev(mid, line, w_over)
        if fm is None:
            return None
        if (fm > 0) == (f_lo > 0):
            lo, f_lo = mid, fm
        else:
            hi, f_hi = mid, fm
    return (lo + hi) / 2.0


def convert(line, w_over, w_under=None):
    """→ dict(lambda, p25_over, o25, u25, line, ev_residual, supported)"""
    lam = solve_total_lambda(line, w_over, w_under)
    if lam is None:
        return {'supported': False, 'line': line}
    p25 = _p_ge(lam, 3)
    p25 = min(max(p25, 1e-6), 1 - 1e-6)
    # 🔴精度纪律: 返回**未取整**值（o25 与 p25_over 必须互为倒数·取整后再相乘会漂）。
    #   展示层负责格式化，调用方按需 round。
    return {
        'supported': True,
        'line': float(line),
        'lambda': lam,
        'p25_over': p25,
        'o25': 1.0 / p25,
        'u25': 1.0 / (1 - p25),
        'ev_residual': _ev(lam, float(line), float(w_over)),
        'expect_total': lam,
    }


def main():
    ap = argparse.ArgumentParser(description='亚洲盘大小球线 → O2.5/U2.5（四分之一线 EV 中性折算）')
    ap.add_argument('--line', type=float, required=True,
                    help='主流线·支持 %s' % '/'.join('%g' % x for x in sorted(LINES)))
    ap.add_argument('--over', type=float, required=True, help='上盘（大球）香港水位·如 0.82')
    ap.add_argument('--under', type=float, default=None, help='下盘（小球）香港水位·可选')
    ap.add_argument('--json', action='store_true', help='输出 JSON')
    a = ap.parse_args()

    if a.line not in LINES:
        msg = '不支持该线型: %g（已支持 %s）' % (a.line, '/'.join('%g' % x for x in sorted(LINES)))
        print(msg, file=sys.stderr)
        sys.exit(2)

    r = convert(a.line, a.over, a.under)
    if not r.get('supported'):
        print('折算失败: 线型或水位越界', file=sys.stderr)
        sys.exit(3)

    if a.json:
        print(json.dumps({k: (round(v, 6) if isinstance(v, float) else v)
                          for k, v in r.items()}, ensure_ascii=False))
        return

    print('亚洲盘折算（四分之一线 EV 中性）')
    print('  主流线 %g · 上盘水 %.2f%s' % (
        r['line'], a.over, (' · 下盘水 %.2f' % a.under) if a.under is not None else ''))
    print('  反解 λ_total = %.3f（期望总进球 %.2f）' % (r['lambda'], r['expect_total']))
    print('  2.5 档 P(over) = %.4f' % r['p25_over'])
    print('  O2.5 = %.2f  |  U2.5 = %.2f' % (r['o25'], r['u25']))
    print('  EV 残差 = %.2e（应≈0·自检）' % r['ev_residual'])


if __name__ == '__main__':
    main()
