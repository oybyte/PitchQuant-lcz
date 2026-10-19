#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""opening_shift.py — S4「初盘位移强度」单一真源（2026-10-19）

🔴 这个模块回答的问题不是「庄家看好谁」，而是「这场的盘口被动过没有、动得多不多」。

背景（441 场真初盘·docs/初盘判定_2026-10-19.md）
  · 初盘单点判方向 = 终盘单点，都是 58.5% → 初盘不提供独立方向信息
  · 但「初盘→即盘」的**位移幅度**本身有信息：
      |位移|≥5pp 且热门未变 → 73.6%（n=87） vs 稳定 ±3pp → 55.3%（n=246）
      Bootstrap 95%CI [+0.068, +0.291]
  · 🔴 不是方向信号：加仓 75.0%(n=64) vs 弃仓 69.6%(n=23)，p=0.237 无显著差异
    → 机制是「有大量新信息进场把定价重洗了一遍」，不是「庄家确认了某个方向」

口径（三维组合，缺一不可）
  基准 = 澳门欧赔 init_*（真初盘）
  终点 = 同一行 live_*
  fav      = 初盘三项赔率最低的方向（并列取先出现者）
  conc_pp  = (1/live[fav] - 1/init[fav]) * 100
  fav_kept = argmin(init) == argmin(live)
  分级     = flip(被推翻) | strong(|conc|≥5) | mid(3≤|conc|<5) | flat

🔴 纪律
  · 本模块**只产出标签**，不得用于覆盖 direction_full 或 L2 硬核（AGENTS §5.5）
  · 阈值只在本文件定义一次，他处一律 import，禁止硬编码
  · 缺真初盘一律三态「无数据(原因)」，禁止静默降为「平稳」
  · 本模块只处理欧赔三元组；亚盘盘口符号与项目 handi 相反（handi = -line），
    误传亚盘值（含负数）必须被拒绝而不是算出个数字

用法
  from opening_shift import compute_shift, signal_line
  r = compute_shift((1.48, 3.97, 5.40), (1.40, 4.20, 6.00))
  print(signal_line(r))
"""
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

# ── 阈值单一真源（禁他处硬编码）──
S4_SHIFT_MIN_PP = 5.0        # |conc_pp| ≥ 此值 → strong
S4_MID_PP = 3.0              # 3 ≤ |conc_pp| < 5 → mid
S4_STRONG_FAV_PCT = 70.0     # 即盘热门 ≥ 此值 → 强热门档，不追加

TIERS = ('flip', 'strong', 'mid', 'flat', 'missing')

_MISSING_KEYS = ('state', 'reason', 'fav_open', 'fav_live', 'fav_kept',
                 'conc_pp', 'fav_live_pct', 'tier')


def _missing(reason):
    """三态构造器——缺数据时唯一出口，禁止用空 dict 或 None 冒充"""
    return {'state': 'missing', 'reason': reason, 'fav_open': None,
            'fav_live': None, 'fav_kept': None, 'conc_pp': None,
            'fav_live_pct': None, 'fav_open_pct': None,
            'fav_open_dir_pct': None, 'tier': 'missing'}


def _f(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if v != v:          # NaN
        return None
    return v


def _check_triple(o, tag):
    """→ (三元组, None) 或 (None, 原因)

    🔴 守卫：必须是长度 3 的欧赔三元组，且每项 >1.0。
       负数即亚盘盘口误传（亚盘原始盘口 0.5/1 带符号），必须拒绝。
    """
    if o is None:
        return None, '%s缺失' % tag
    try:
        o = list(o)
    except TypeError:
        return None, '%s格式非法' % tag
    if len(o) != 3:
        return None, '%s非3元(长度%d)·需欧赔 主/平/客' % (tag, len(o))
    vals = [_f(x) for x in o]
    if any(v is None for v in vals):
        return None, '%s含非数值' % tag
    if any(v <= 1.0 for v in vals):
        return None, '%s赔率非法(≤1.0·疑似误传亚盘盘口)' % tag
    return vals, None


def _argmin_dir(o):
    """赔率最低的方向索引：0=主 1=平 2=客。并列取先出现者（list.index 语义）。"""
    return int(min(range(3), key=lambda i: o[i]))


def _devig(o):
    """等比例去水 → [p主, p平, p客]"""
    inv = [1.0 / x for x in o]
    s = sum(inv)
    return [x / s for x in inv]


def compute_shift(init, live):
    """→ dict（键固定 8 个·见 _MISSING_KEYS）

    init/live 为澳门欧赔三元组 (主, 平, 客)。
    conc_pp 恒为「初盘热门方向」的隐含概率变化，正=被加仓，负=被弃。
    """
    vi, why_i = _check_triple(init, '初盘')
    if why_i:
        return _missing(why_i)
    vl, why_l = _check_triple(live, '即盘')
    if why_l:
        return _missing(why_l)

    fav_open = _argmin_dir(vi)
    fav_live = _argmin_dir(vl)
    kept = (fav_open == fav_live)

    # 位移强度：只看初盘热门方向（不是主客绝对值取最大）
    conc = (1.0 / vl[fav_open] - 1.0 / vi[fav_open]) * 100.0
    conc = 0.0 if abs(conc) < 1e-12 else conc

    # 展示用的三个占比（全部为「去水后」·同量纲）：
    #   fav_live_pct     = 即盘热门方占比           （is_strong 判强热门档用）
    #   fav_open_pct     = 初盘热门方占比           （初盘侧的起点）
    #   fav_open_dir_pct = 「初盘热门那一方向」在即盘的占比（与 open_pct 同向可比）
    pi = _devig(vi)
    pl = _devig(vl)
    pct = pl[fav_live] * 100.0
    open_pct = pi[fav_open] * 100.0
    open_dir_live_pct = pl[fav_open] * 100.0

    # 分级顺序：先 flip，再 strong，再 mid，最后 flat（顺序错会把 flip 判成 strong）
    if not kept:
        tier = 'flip'
    elif abs(conc) >= S4_SHIFT_MIN_PP:
        tier = 'strong'
    elif abs(conc) >= S4_MID_PP:
        tier = 'mid'
    else:
        tier = 'flat'

    return {'state': 'ok', 'reason': None, 'fav_open': fav_open,
            'fav_live': fav_live, 'fav_kept': kept, 'conc_pp': conc,
            'fav_live_pct': pct, 'fav_open_pct': open_pct,
            'fav_open_dir_pct': open_dir_live_pct, 'tier': tier}


_LAB = ('主胜', '平局', '客胜')

_TIER_CN = {'flip': '热门被推翻', 'strong': '强位移',
            'mid': '中等位移', 'flat': '平稳'}


def signal_line(result):
    """→ 写进 txt 头的一行（v259_ingest 用·calc_all 按前缀 🔴S4初盘位移 解析）"""
    if not result or result.get('state') != 'ok':
        why = (result or {}).get('reason') or '未知'
        return '🔴S4初盘位移: 无数据(原因: %s)' % why

    fav = _LAB[result['fav_open']]
    conc = result['conc_pp']
    # 🔴 展示必须用两个「同方向」的去水占比，不能用 pct−conc 反推：
    #   conc 是未去水的赔率倒数差，与去水占比不同量纲；
    #   且热门被推翻时 fav_live ≠ fav_open，pct 属于另一个方向，减出来会差 10pp+。
    open_pct = result.get('fav_open_pct')
    live_pct = result.get('fav_open_dir_pct')
    if open_pct is None or live_pct is None:
        kept = '热门未变' if result['fav_kept'] else '热门被推翻'
        return ('🔴S4初盘位移: %s %+.1fpp · %s · 强度档=%s'
                % (fav, conc, kept, result['tier']))
    kept = '热门未变' if result['fav_kept'] else '热门被推翻'
    return ('🔴S4初盘位移: %s %+.1fpp（初盘 %.1f%% → 即盘 %.1f%%·同向去水）· %s · 强度档=%s'
            % (fav, conc, open_pct, live_pct, kept, result['tier']))


def is_strong(result):
    """是否达到「可 +1 档」——需 strong 且非强热门档（回测 60-70% 档打平）"""
    if not result or result.get('state') != 'ok':
        return False
    if result['tier'] != 'strong':
        return False
    return result['fav_live_pct'] is not None and result['fav_live_pct'] < S4_STRONG_FAV_PCT


if __name__ == '__main__':
    demo = compute_shift((1.48, 3.97, 5.40), (1.40, 4.20, 6.00))
    print(signal_line(demo))
    print('可+1档:', is_strong(demo))
