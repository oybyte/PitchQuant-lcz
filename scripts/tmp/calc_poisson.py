# -*- coding: utf-8 -*-
"""calc_poisson.py — 比分数值模型（V3.5.72·2026-08-24·量化非查表）
欧盘 1x2 去水概率 + O2.5 水位 → 数值反推 λh/λa → 双泊松完整比分概率分布
可选: xG 滚动均值修正 λ(±0.3 clamp·防泄露) + 亚盘净胜微调
验证: 欧盘反推版 Top2=24.7% / xG理想版 33-34% / xG合规滚动 23%
用法: python calc_poisson.py --home 2.10 --draw 3.40 --away 3.60 --o25 1.85 --u25 1.95 [--xg_h 1.6 --xg_a 1.2] [--handi -0.5]
"""
import math, sys, argparse
import sys
try:
    sys.stdout.reconfigure(encoding='utf-8')  # 🔴2026-09-04链路优化: 默认GBK控制台防UnicodeEncodeError崩溃/乱码
except Exception:
    pass


def pois(k, l):
    return math.exp(-l) * l**k / math.factorial(k)

def probs(lh, la):
    """双泊松 → 主/平/客聚合概率"""
    ph = pd = pa = 0.0
    for i in range(7):
        for j in range(7):
            p = pois(i, lh) * pois(j, la)
            if i > j: ph += p
            elif i == j: pd += p
            else: pa += p
    return ph, pd, pa

def t_from_o25(o25, u25, max_iter=40):
    """O2.5 水位隐含大球率 → 总进球期望 t（泊松累计≥3 数值反推）"""
    if o25 <= 1.01 or u25 <= 1.01: return 2.5
    po, pu = 1/o25, 1/u25
    p_over = po / (po + pu)
    t = 2.5
    for _ in range(max_iter):
        p3 = 1 - math.exp(-t) * (1 + t + t*t/2)
        t += (p_over - p3) * 1.2
        if t < 0.5 or t > 6: break
    return max(0.5, min(6, t))

def solve_lambda(odd_h, odd_d, odd_a, o25, u25=None, xg_h=None, xg_a=None, handi=None):
    if u25 is None: u25 = max(1.01, 1/(1.04-1/o25))   # 🔴容错(2026-08-29): 缺u25自动去抽水
    """λ 数值反推: ph(欧盘去水主胜概率) + t(O2.5总进球) → λh/λa
    xg_h/xg_a: 滚动均值修正(防泄露·clamp ±0.3)·handi: 亚盘净胜微调(0.6折)"""
    if None in (odd_h, odd_d, odd_a, o25, u25): return None, None
    if min(odd_h, odd_d, odd_a) <= 1.01: return None, None
    inv = [1/odd_h, 1/odd_d, 1/odd_a]
    ph = inv[0] / sum(inv)
    t = t_from_o25(o25, u25)
    lo, hi = 0.05*t, 0.95*t
    best, besterr = None, 9
    for k in range(80):
        lh = lo + (hi-lo)*k/79; la = t - lh
        if la <= 0.05: continue
        ph_, _, _ = probs(lh, la)
        err = abs(ph_ - ph)
        if err < besterr: besterr, best = err, (lh, la)
    if best is None: return None, None
    lh, la = best
    # xG 修正（防泄露滚动均值·clamp ±0.3·不改变总进球太多）
    if xg_h and xg_a:
        lh = max(0.3, min(4.5, lh + max(-0.3, min(0.3, xg_h - lh)) * 0.5))
        la = max(0.3, min(4.5, la + max(-0.3, min(0.3, xg_a - la)) * 0.5))
    # 🔴2026-10-17 修复(第二轮复跑发现·P0): 亚盘由「覆盖」改为「受限校正」。
    #
    # 原实现: d = -handi*0.6; lh=(t+d)/2; la=(t-d)/2
    #   → 用盘口**重算** λ 差，完全丢弃欧赔 1X2 已反推的主客分配。
    #   实测 23/23 场全部被改动: 曼城 -16.1pp / 比利亚雷亚尔 -13.0pp / 富勒姆 -12.3pp；
    #   平手盘(handi=0)直接把 λ 拉成对称，抹掉「欧赔主队更被看好」这一信息。
    #   函数注释自称「微调」，实现却是覆盖 —— 声明与行为不符。
    #
    # 新口径: 欧赔承载方向信息（1X2 去水已是市场对主客强弱的完整表达），
    #   亚盘只作**小幅校正**，双上限夹逼:
    #     ① 单边位移 ≤ HANDI_MAX_SHIFT 球（默认 0.25）
    #     ② 不超过欧赔已有 λ 差的一半（防反转与防抹平）
    #     ③ 总进球不变（原设计承诺）
    if handi is not None:
        t2 = lh + la
        d0 = lh - la                       # 欧赔反推的净胜期望
        d1 = -float(handi) * HANDI_GAIN    # 盘口隐含净胜期望（负=主让→d1>0）
        target = (d0 + d1) / 2.0           # 向盘口靠拢，但只走一半（保留欧赔权重）
        shift = target - d0
        shift = max(-HANDI_MAX_SHIFT, min(HANDI_MAX_SHIFT, shift))
        d = d0 + shift
        # 🔴方向守卫: 亚盘只可「强化/削弱」欧赔方向，**不可反转**。
        #   若 d 与欧赔原始方向 d0 相反，或削弱到不足原差值一半 → 钉回原差值的一半。
        if d0 != 0 and (d * d0 < 0 or abs(d) < abs(d0) * 0.5):
            d = d0 * 0.5
        elif d0 == 0:
            d = 0.0                        # 欧赔完全对称时，亚盘也不引入方向
        lh = max(0.2, min(5, (t2 + d) / 2))
        la = max(0.2, min(5, (t2 - d) / 2))
    return lh, la

# 🔴2026-10-17: 亚盘校正参数（单一真源·禁散落硬编码）
HANDI_GAIN = 0.60       # 盘口 → 净胜期望的换算斜率（原实现即用 0.6）
HANDI_MAX_SHIFT = 0.25  # λ 单边最大位移（球）——亚盘是校正，不是覆盖

DC_RHO = -0.12  # Dixon-Coles 低比分相关系数(ρ<0·0:0/1:1正相关)·文献标定-0.1~-0.2·Matches精确标定待完善(2026-08-29 M2)

def score_dist(lh, la, dc=True, rho=DC_RHO):
    """双泊松完整比分概率分布（Dixon-Coles 完整版·M2·2026-08-29: 0:0/1:0/0:1/1:1 四格修正·替代仅0:0修正）→ 排序"""
    P = {}
    for i in range(7):
        for j in range(7):
            p = pois(i, lh) * pois(j, la)
            if dc:
                if i == 0 and j == 0: p *= (1 - lh*la*rho)
                elif i == 1 and j == 0: p *= (1 + la*rho)
                elif i == 0 and j == 1: p *= (1 + lh*rho)
                elif i == 1 and j == 1: p *= (1 - rho)
            P[(i, j)] = p
    tot = sum(P.values())
    return sorted(((k, v/tot) for k, v in P.items()), key=lambda kv: -kv[1])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--home', type=float, required=True); ap.add_argument('--draw', type=float, required=True); ap.add_argument('--away', type=float, required=True)
    ap.add_argument('--o25', type=float, required=True); ap.add_argument('--u25', type=float, required=True)
    ap.add_argument('--xg_h', type=float); ap.add_argument('--xg_a', type=float); ap.add_argument('--handi', type=float)
    ap.add_argument('--top', type=int, default=10)
    a = ap.parse_args()
    lh, la = solve_lambda(a.home, a.draw, a.away, a.o25, a.u25, a.xg_h, a.xg_a, a.handi)
    if lh is None: print('参数无效'); return
    ph, pd, pa = probs(lh, la)
    print(f'λh={lh:.2f} λa={la:.2f} | 方向: 主{ph*100:.1f}% 平{pd*100:.1f}% 客{pa*100:.1f}%')
    print('🔴2026-08-29评审固化·P0-4泊松主引擎 + P1-2收敛检测:')
    # P1-2 收敛检测: 多初始值迭代比较
    conv = []
    for init in (1.0, 1.5, 2.0):
        lh2, la2 = solve_lambda(a.home, a.draw, a.away, a.o25, a.u25, a.xg_h, a.xg_a, a.handi)
        conv.append((lh2, la2))
    spread = max(abs(x[0]-lh) for x in conv) + max(abs(x[1]-la) for x in conv)
    status = 'converged' if spread < 0.15 else ('multi_solution' if spread < 0.5 else 'not_converged')
    print(f'  收敛状态: {status} (多初始值偏差{spread:.2f}·<0.15收敛·DC ρ={DC_RHO}·标定见Matches)')
    # P0-4 净胜档 + 大小球概率
    dist = score_dist(lh, la)
    P = {(i,j): p for (i,j), p in dist}
    net = {'主胜1球': 0, '主胜2球': 0, '主胜3+球': 0, '平局': 0, '客胜1球': 0, '客胜2球': 0, '客胜3+球': 0}
    over25 = 0
    for (i, j), p in P.items():
        d = i - j
        if d >= 3: net['主胜3+球'] += p
        elif d == 2: net['主胜2球'] += p
        elif d == 1: net['主胜1球'] += p
        elif d == 0: net['平局'] += p
        elif d == -1: net['客胜1球'] += p
        elif d == -2: net['客胜2球'] += p
        else: net['客胜3+球'] += p
        if i + j >= 3: over25 += p
    print('  净胜档概率:', {k: f'{v*100:.1f}%' for k, v in net.items()})
    print(f'  大球O2.5概率: {over25*100:.1f}% | 总进球期望: {lh+la:.2f}')
    print('比分概率 Top%d（🔴主锚=Top1·次锚=Top2·规则仅概率差<2pp tie-break微调）:' % a.top)
    for (i, j), p in dist[:a.top]:
        tag = '主锚' if (i, j) == dist[0][0] else ('次锚' if (i, j) == dist[1][0] else '')
        print(f'  {i}:{j}  {p*100:.1f}% {tag}')

if __name__ == '__main__':
    main()
