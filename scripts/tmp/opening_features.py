#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""opening_features.py — 「真·初盘」特征抽取（数据源修复 + 特征工程）

🔴 关键发现（为什么之前的分析用不了初盘）
   历史盲测语料 data/tmp/batch_*/blind_parsed.json 里的 tl_* 是**抓取时刻的时序快照**，
   它的「最早点」只有 45-55% 等于真实初盘（实测 batch_203 106/166、batch_140 88/139），
   剩下的是抓取时已经变动过的盘 —— 用它当「初盘」等于用了一个带噪声的伪初盘。

   真·初盘藏在原始 OCR 结果里：
     matches-*/output/<场次>/识别结果.json
       → slots[asian_handicap].result.overview_rows[*]
           = {provider_name, provider_id, opening:[主水,盘口,客水], late:[…]}
   覆盖率 **203/203 · 74/74 · 140/140 = 100%**，且 opening 与 late 明确分离。

本模块抽取三个时刻：
   opening  = 真初盘（真·开盘定价）
   late     = 抓取时刻即盘
   两者之差 = 完整的价格路径（这才是「初盘信息」的全部载体）
"""
import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RAW_ROOTS = {
    'matches-203': r'F:\ocr_python_data\football-research\matches-203\output',
    'matches-74': r'F:\ocr_python_data\football-research\matches-74\output',
    'matches-140': r'F:\ocr_python_data\football-research\matches-140\output',
    'matches-24-2.5.8': r'F:\ocr_python_data\football-research\matches-24-2.5.8\output',
}
SLOT_MAP = {
    'ah': 'asian_handicap',
    'eu': 'european_odds',
    'ou': 'total_goals',
}


def _f(x):
    try:
        v = float(x)
        return v if v == v else None
    except (TypeError, ValueError):
        return None


def line_val(s):
    """'0.5/1'→0.75  '-0.5'→-0.5  '0'→0  '2/2.5'→2.25

    🔴 符号约定（与项目 handi 相反，务必注意）：
       本函数返回的是**澳门原始盘口**：正数 = 主队**让**球（主强），负数 = 主队**受**让。
       项目内部 handi（calc_all/v259_ingest）= **负号取反**：handi = -line。
       实测一致率：matches-203 78% / matches-74 84% / matches-140 78%（其余为冷门或
       欧亚轻微错配，不是符号反了）。转换时一律显式写 handi = -line，禁止混用。
    """
    if s is None:
        return None
    s = str(s).strip().replace('+', '').replace('﹣', '-')
    if s in ('', '-', '—'):
        return None
    if '/' in s:
        parts = s.split('/')
        if len(parts) == 2:
            a, b = _f(parts[0]), _f(parts[1])
            if a is None or b is None:
                return None
            return (a + b) / 2.0
    return _f(s)


def devig(o):
    try:
        o = [_f(x) for x in o]
        if len(o) != 3 or any(v is None for v in o) or min(o) <= 1.0:
            return None
        inv = [1.0 / x for x in o]
        s = sum(inv)
        return [x / s for x in inv]
    except Exception:
        return None


def asian_p(w_home, w_away):
    """亚盘双水 → 上盘 EV 中性概率（水位自适应 0.85 型 / 1.85 型）"""
    lh, la = _f(w_home), _f(w_away)
    if lh is None or la is None:
        return None
    if lh < 1.30:
        lh += 1.0
    if la < 1.30:
        la += 1.0
    if lh <= 1.0 or la <= 1.0:
        return None
    return max(0.0, min(1.0, (la - 1.0) / ((lh - 1.0) + (la - 1.0))))


def read_raw(match_dir):
    """→ dict(opening={ah,eu,ou}, late={...}, extra) 或 None"""
    p = os.path.join(match_dir, '识别结果.json')
    if not os.path.exists(p):
        return None
    j = json.load(open(p, encoding='utf-8'))
    slots = j.get('slots') or {}
    out = {'opening': {}, 'late': {}, 'macau_only': {}}
    for kind, slot in SLOT_MAP.items():
        r = (slots.get(slot) or {}).get('result') or {}
        rows = r.get('overview_rows') or []
        mac = next((x for x in rows if x.get('provider_id') == 'macau'), None)
        if mac:
            out['opening'][kind] = list(mac.get('opening') or [])
            out['late'][kind] = list(mac.get('late') or [])
        # 全机构快照（用于跨机构分歧）
        out[kind + '_books'] = [
            {'name': x.get('provider_name'), 'open': x.get('opening'), 'late': x.get('late')}
            for x in rows]
    fix = j.get('fixture') or {}
    out['fixture'] = {'league': fix.get('competition'), 'home': fix.get('home_team'),
                      'away': fix.get('away_team'), 'kickoff': fix.get('kickoff_display'),
                      'L': fix.get('sport_lottery_handicap')}
    oc = j.get('outcome') or {}
    ft = oc.get('full_time') or {}
    # 🔴 字段是 home_goals / away_goals（不是 home / away）
    out['outcome'] = {'h': ft.get('home_goals'), 'a': ft.get('away_goals'),
                      'status': oc.get('status'),
                      'ht': oc.get('half_time'), 'tot': oc.get('total_goals')}
    return out


def features(raw):
    """→ dict 初盘特征族"""
    F = {}
    if not raw:
        return F
    op, lt = raw.get('opening') or {}, raw.get('late') or {}
    ah_o, ah_l = op.get('ah') or [], lt.get('ah') or []
    eu_o, eu_l = op.get('eu') or [], lt.get('eu') or []
    ou_o, ou_l = op.get('ou') or [], lt.get('ou') or []

    # ── 欧赔初盘 ──
    p_o = devig(eu_o) if len(eu_o) == 3 else None
    p_l = devig(eu_l) if len(eu_l) == 3 else None
    if len(eu_o) == 3:
        F['e_oh'], F['e_od'], F['e_oa'] = [_f(x) for x in eu_o]      # 原始赔率（分档要用）
    if len(eu_l) == 3:
        F['e_lh'], F['e_ld'], F['e_la'] = [_f(x) for x in eu_l]
    if p_o:
        F['o_h'], F['o_d'], F['o_a'] = [x * 100 for x in p_o]
        F['o_gap'] = (p_o[0] - p_o[2]) * 100
        srt = sorted(p_o, reverse=True)
        F['o_skew'] = (srt[0] / srt[1] * 100) if srt[1] > 1e-9 else 999.
        F['o_fav'] = float(p_o.index(max(p_o)))
        F['o_sum'] = sum(float(x) for x in eu_o)
    if p_l:
        F['l_h'], F['l_d'], F['l_a'] = [x * 100 for x in p_l]
        F['l_gap'] = (p_l[0] - p_l[2]) * 100
    if p_o and p_l:
        F['d_h'] = (p_l[0] - p_o[0]) * 100
        F['d_d'] = (p_l[1] - p_o[1]) * 100
        F['d_a'] = (p_l[2] - p_o[2]) * 100
        F['d_fav_change'] = float(p_l.index(max(p_l)) != p_o.index(max(p_o)))

    # ── 亚盘初盘 ──
    la_o = line_val(ah_o[1]) if len(ah_o) == 3 else None
    la_l = line_val(ah_l[1]) if len(ah_l) == 3 else None
    if la_o is not None:
        F['a_line_o'] = la_o
        F['a_line_abs'] = abs(la_o)
    if la_l is not None:
        F['a_line_l'] = la_l
    if la_o is not None and la_l is not None:
        F['a_move'] = la_l - la_o
        F['a_moved'] = float(abs(la_l - la_o) > 1e-9)
    po = asian_p(ah_o[0], ah_o[2]) if len(ah_o) == 3 else None
    pl = asian_p(ah_l[0], ah_l[2]) if len(ah_l) == 3 else None
    if po is not None:
        F['a_p_o'] = po * 100
    if pl is not None:
        F['a_p_l'] = pl * 100
    if po is not None and pl is not None:
        F['a_p_d'] = (pl - po) * 100
    if len(ah_o) == 3:
        F['a_w_o'] = _f(ah_o[0])
        F['a_w_gap_o'] = (_f(ah_o[0]) or 0) - (_f(ah_o[2]) or 0)
    if len(ah_l) == 3:
        F['a_w_l'] = _f(ah_l[0])

    # ── 大小球初盘 ──
    lo = line_val(ou_o[1]) if len(ou_o) == 3 else None
    ll = line_val(ou_l[1]) if len(ou_l) == 3 else None
    if lo is not None:
        F['t_line_o'] = lo
    if ll is not None:
        F['t_line_l'] = ll
    if lo is not None and ll is not None:
        F['t_move'] = ll - lo
    oo = asian_p(ou_o[0], ou_o[2]) if len(ou_o) == 3 else None
    if oo is not None:
        F['t_over_o'] = oo * 100

    # ── 交叉：初盘欧亚背离 ──
    if p_o and po is not None:
        F['x_o_eu_ah'] = p_o[0] * 100 - po * 100
    if p_o and la_o is not None:
        F['x_o_line_imp'] = la_o * 100 - p_o[0] * 100     # 盘口深度 vs 欧赔隐含
    # ── 跨机构初盘分歧（初盘就有分歧 = 机构没共识）──
    ahb = [b for b in (raw.get('ah_books') or []) if b.get('open')]
    if len(ahb) >= 3:
        lv = [line_val(b['open'][1]) for b in ahb]
        lv = [x for x in lv if x is not None]
        if lv:
            F['disp_line'] = max(lv) - min(lv)
            F['n_books_ah'] = float(len(lv))
    eub = [b for b in (raw.get('eu_books') or []) if b.get('open')]
    if len(eub) >= 3:
        ph = [devig(b['open']) for b in eub]
        ph = [x[0] for x in ph if x]
        if ph:
            F['disp_h'] = (max(ph) - min(ph)) * 100
            F['n_books_eu'] = float(len(ph))
    return {k: float(v) for k, v in F.items() if v is not None}


def collect():
    """→ list[dict(name, league, home, away, label, score, F, src)]"""
    out = []
    for tag, base in RAW_ROOTS.items():
        if not os.path.isdir(base):
            continue
        for d in sorted(os.listdir(base)):
            md = os.path.join(base, d)
            if not os.path.isdir(md):
                continue
            raw = read_raw(md)
            if not raw:
                continue
            oc = raw.get('outcome') or {}
            h, a = _f(oc.get('h')), _f(oc.get('a'))
            if h is None or a is None:
                continue
            F = features(raw)
            if 'o_h' not in F:
                continue
            lab = 0 if h > a else (1 if h == a else 2)
            fx = raw['fixture']
            out.append({'src': tag, 'name': d, 'league': fx.get('league'),
                        'home': fx.get('home'), 'away': fx.get('away'),
                        'kickoff': fx.get('kickoff'), 'L': fx.get('L'),
                        'label': lab, 'score': '%d:%d' % (h, a), 'tot': h + a, 'F': F})
    return out


if __name__ == '__main__':
    S = collect()
    from collections import Counter
    print('样本', len(S))
    print('来源', dict(Counter(x['src'] for x in S)))
    print('方向', dict(Counter(x['label'] for x in S)))
    print('联赛数', len(set(x['league'] for x in S)))
    print('特征维度', len(S[0]['F']))
    print('样例:', json.dumps(S[0]['F'], ensure_ascii=False)[:500])
