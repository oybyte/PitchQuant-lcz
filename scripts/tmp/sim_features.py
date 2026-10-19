#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sim_features.py — 相似性分析统一特征抽取（历史盲测语料 ↔ 今日待赛快照）

🔴 核心约束（为什么只用澳门通道）
   历史语料 data/tmp/batch_{2_5_8,74,140,203}/blind_parsed.json 每场只有 5-6 家欧赔；
   今日快照 data-2.5.9/_by_category/竞足 每场 319-371 家。直接拼跨机构维度会得到
   「机构数量」而非「盘口形态」。二者唯一同构的通道是 **澳门(Macauslot) 胜平负/亚盘/大小球时序**。

🔴 防泄漏（本模块的核心纪律）
   所有特征都由「T-minus 截断后」的数据计算：只使用距开赛 >= H 小时的点。
   预测今日比赛时，历史样本与今日样本在**同一 T-minus 视界**上截断，
   因此历史侧同样看不到收盘价 —— 这是可比性的前提，不是可选项。

特征族
   L*  level    去水隐含概率（截断点上的市场定价水平）
   D*  drift    阶段隐含概率变动（资金流向）
   S*  shape    路径形态（波动/单边性/反转/节奏重心）
   A*  asian    亚盘盘口与水位
   O*  totals   大小球盘口与水位
   X*  cross    欧亚背离

用法
  python scripts/tmp/sim_features.py            # 自检：语料规模 + 特征名
"""

import json
import math
import os
import re
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HIST_BATCHES = ('batch_2_5_8', 'batch_74', 'batch_140', 'batch_203')
SNAP_ROOT = r'F:\ocr_python_data\football-research\data-2.5.9\_by_category\竞足'
RESULT_ROOTS = ('竞足', '单场', '14场')


# ────────────────────────── 基础 ──────────────────────────
def _f(x):
    try:
        v = float(x)
        return v if v == v else None          # NaN 过滤
    except (TypeError, ValueError):
        return None


def devig(o):
    """等比例去水 → [p_h, p_d, p_a]"""
    try:
        o = [float(x) for x in o]
        if len(o) != 3 or min(o) <= 1.0:
            return None
        inv = [1.0 / x for x in o]
        s = sum(inv)
        return [x / s for x in inv]
    except (TypeError, ValueError):
        return None


def parse_dt(s):
    """'08-14 17:37' / '2026-10-18 14:09:00' → datetime(2026, …)"""
    m = re.search(r'(\d{1,2})-(\d{1,2})[ _](\d{1,2}):(\d{2})', s or '')
    if not m:
        return None
    try:
        return datetime(2026, int(m.group(1)), int(m.group(2)),
                        int(m.group(3)), int(m.group(4)))
    except ValueError:
        return None


def asian_p(water_home, water_away):
    """亚盘双水 → 上盘(主)EV中性概率。水位口径自适应（0.85 型 / 1.85 型）。"""
    lh, la = _f(water_home), _f(water_away)
    if lh is None or la is None:
        return None
    if lh < 1.30:
        lh += 1.0
    if la < 1.30:
        la += 1.0
    if lh <= 1.0 or la <= 1.0:
        return None
    return max(0.0, min(1.0, (la - 1.0) / ((lh - 1.0) + (la - 1.0))))


# ────────────────────────── 序列构建（统一成 t_minus 小时）──────────────────────────
def series_hist(tl_eu, tl_ah, tl_ou, ko):
    """历史 blind_parsed：tl_* = [[time, [..]], ...] → dict(升序 [(tminus_h, vals)])"""
    def conv(tl, width):
        rows = []
        for t, v in (tl or []):
            dt = parse_dt(t)
            if not dt or not v or len(v) < width:
                continue
            vals = [_f(x) for x in v[:width]]
            if any(x is None for x in vals):
                continue
            rows.append(((ko - dt).total_seconds() / 3600.0, vals))
        rows.sort(key=lambda r: -r[0])          # tminus 降序 = 时间升序
        return rows
    return {'eu': conv(tl_eu, 3), 'ah': conv(tl_ah, 3), 'ou': conv(tl_ou, 3)}


def series_snap(det):
    """今日快照：euro_timeline / asian_timeline / ou_timeline"""
    ko = parse_dt(det.get('match_time'))

    def conv(tl, kind):
        rows = []
        for r in (tl or []):
            dt = parse_dt(r.get('time') or '')
            if not dt or not ko:
                continue
            if kind == 'eu':
                vals = [_f(r.get('home')), _f(r.get('line')), _f(r.get('away'))]
            else:
                ln = r.get('line_value')
                if ln is None:
                    ln = r.get('line_ocr')
                if ln is None:
                    ln = r.get('line')
                vals = [_f(r.get('home')), _f(ln), _f(r.get('away'))]
            if any(x is None for x in vals):
                continue
            rows.append(((ko - dt).total_seconds() / 3600.0, vals))
        rows.sort(key=lambda r: -r[0])
        return rows
    return {'eu': conv(det.get('euro_timeline'), 'eu'),
            'ah': conv(det.get('asian_timeline'), 'ah'),
            'ou': conv(det.get('ou_timeline'), 'ou')}


def truncate(series, horizon_h):
    """只保留距开赛 >= horizon_h 的点（horizon_h=0 → 全部保留）"""
    if horizon_h <= 0:
        return series
    return {k: [p for p in v if p[0] >= horizon_h - 1e-9] for k, v in series.items()}


# ────────────────────────── 特征 ──────────────────────────
BUCKETS = (48.0, 24.0, 12.0, 6.0, 3.0, 1.0)


def _at(rows, tmin):
    """取距开赛 tmin 小时之前(含)的最后一个点；样本更早则取最早点"""
    cand = [r for r in rows if r[0] >= tmin - 1e-9]
    if cand:
        return cand[-1]
    return rows[0] if rows else None


def features(series):
    """series 必须已截断 → dict[str,float]"""
    F = {}
    eu, ah, ou = series['eu'], series['ah'], series['ou']

    # ── 近端水平（截断点）──
    cur = _at(eu, 0.0)
    if cur:
        p = devig(cur[1])
        if p:
            F['lvl_h'], F['lvl_d'], F['lvl_a'] = [x * 100 for x in p]
            F['lvl_gap'] = (p[0] - p[2]) * 100
            srt = sorted(p, reverse=True)
            F['lvl_skew'] = (srt[0] / srt[1] * 100) if srt[1] > 1e-9 else 999.0
            F['lvl_fav'] = float(p.index(max(p)))
            F['lvl_h_draw'] = p[0] * p[1] * 100          # 主×平 交互（平局敏感）

    # ── 阶段水平（时间对齐）──
    for b in BUCKETS:
        pt = _at(eu, b)
        if not pt:
            continue
        p = devig(pt[1])
        if not p:
            continue
        F['lv%d_h' % int(b)] = p[0] * 100
        F['lv%d_d' % int(b)] = p[1] * 100
        F['lv%d_a' % int(b)] = p[2] * 100
        F['lv%d_gap' % int(b)] = (p[0] - p[2]) * 100

    # ── 漂移 ──
    seq = []
    for t, v in eu:
        p = devig(v)
        if p:
            seq.append((t, p))
    if len(seq) >= 2:
        first, last = seq[0][1], seq[-1][1]
        F['dr_h'] = (last[0] - first[0]) * 100
        F['dr_d'] = (last[1] - first[1]) * 100
        F['dr_a'] = (last[2] - first[2]) * 100
        for b in (24.0, 6.0, 1.0):
            a = _at([(t, devig(v)) for t, v in eu if devig(v)], b)
            if a:
                F['dr%d_h' % int(b)] = (last[0] - a[1][0]) * 100
                F['dr%d_a' % int(b)] = (last[2] - a[1][2]) * 100
        F['dr_span_h'] = seq[0][0] - seq[-1][0]
        F['dr_npts'] = float(len(seq))

        # ── 形态 ──
        diffs = [seq[i + 1][1][0] - seq[i][1][0] for i in range(len(seq) - 1)]
        absd = [abs(d) for d in diffs]
        tot = sum(absd)
        if tot > 1e-9:
            F['sh_h_eff'] = (last[0] - first[0]) / tot * 100 if tot else 0
            F['sh_h_rev'] = float(sum(1 for i in range(1, len(diffs))
                                     if diffs[i] * diffs[i - 1] < -1e-12))
            span = seq[0][0] - seq[-1][0]
            if span > 1e-9:
                w = 0.0
                for i, d in enumerate(absd):
                    w += d * ((seq[0][0] - seq[i + 1][0]) / span)
                F['sh_h_tc'] = w / tot * 100
        for k, nm in ((0, 'h'), (2, 'a')):
            vals = [s[1][k] for s in seq]
            mean = sum(vals) / len(vals)
            F['sh_%s_vol' % nm] = math.sqrt(sum((x - mean) ** 2 for x in vals) / len(vals)) * 100
            F['sh_%s_rng' % nm] = (max(vals) - min(vals)) * 100

    # ── 亚盘 ──
    if ah:
        ln = [(_f(v[1]), _f(v[0]), _f(v[2])) for _, v in ah]
        ln = [x for x in ln if x[0] is not None]
        if ln:
            F['ah_line_open'] = ln[0][0]
            F['ah_line_last'] = ln[-1][0]
            F['ah_line_d'] = ln[-1][0] - ln[0][0]
            F['ah_moves'] = float(sum(1 for i in range(1, len(ln)) if ln[i][0] != ln[i - 1][0]))
            F['ah_depth'] = max(abs(x[0]) for x in ln)
        probs = [(asian_p(v[0], v[2]))
                 for _, v in [(t, [v[0], v[1], v[2]]) for t, v in ah]]
        probs = [x for x in probs if x is not None]
        if probs:
            F['ah_p_open'] = probs[0] * 100
            F['ah_p_last'] = probs[-1] * 100
            F['ah_p_d'] = (probs[-1] - probs[0]) * 100

    # ── 大小球 ──
    if ou:
        oln = [(_f(v[1]), _f(v[0]), _f(v[2])) for _, v in ou]
        oln = [x for x in oln if x[0] is not None]
        if oln:
            F['ou_line_open'] = oln[0][0]
            F['ou_line_last'] = oln[-1][0]
            F['ou_line_d'] = oln[-1][0] - oln[0][0]
        pr = [asian_p(v[0], v[2]) for _, v in ou]
        pr = [x for x in pr if x is not None]
        if pr:
            F['ou_over_open'] = pr[0] * 100
            F['ou_over_last'] = pr[-1] * 100

    # ── 交叉 ──
    if 'lvl_h' in F and 'ah_p_last' in F:
        F['x_eu_ah'] = F['lvl_h'] - F['ah_p_last']
    if 'ah_line_last' in F and 'lvl_h' in F:
        F['x_line_imp'] = F['ah_line_last'] * 100 - F['lvl_h']
    return {k: (0.0 if (v is None or v != v) else float(v)) for k, v in F.items()}


# ────────────────────────── 语料 ──────────────────────────
LAB = {'主胜': 0, '平局': 1, '客胜': 2}


def _results_from_snapshots():
    """data-2.5.9 三个类目里已回填赛果的场次（未回填的跳过，绝不猜）"""
    out = {}
    for cat in RESULT_ROOTS:
        base = os.path.join(SNAP_ROOT.replace('竞足', cat))
        if not os.path.isdir(base):
            continue
        for n in os.listdir(base):
            md = os.path.join(base, n, '服务端数据.md')
            js = os.path.join(base, n, '服务端数据.json')
            if not (os.path.exists(md) and os.path.exists(js)):
                continue
            t = open(md, encoding='utf-8', errors='ignore').read()
            m = re.search(r'全场比分[：:]\s*(\d+)\s*[-:]\s*(\d+)', t)
            if not m:
                continue
            h, a = int(m.group(1)), int(m.group(2))
            det = json.load(open(js, encoding='utf-8'))['detail']
            key = (det.get('league'), det.get('home'), det.get('away'))
            out[key] = {'h': h, 'a': a, 'dir': os.path.join(base, n),
                        'score': '%d:%d' % (h, a),
                        'lab': 0 if h > a else (1 if h == a else 2)}
    return out


def dedupe(samples):
    """🔴去重：同一场比赛会被多个批次重复收录（实测 455 → 404，多出 51 条）。

    重复样本会让 KNN 的同一个邻居被计 k 次，等价于给热门形态加权 —— 是隐性泄漏。
    判据用「联赛+主客队+最早时点」的指纹，不依赖文件名。
    """
    seen = {}
    out = []
    for s in samples:
        eu = s['series']['eu']
        if not eu:
            continue
        fp = (s['league'], eu[0][0], eu[-1][0], len(eu),
              round(eu[-1][1][0], 2), round(eu[-1][1][2], 2))
        if fp in seen:
            continue
        seen[fp] = 1
        out.append(s)
    return out


def collect_corpus():
    """→ (list[样本], dict 统计)。样本含 series（供不同 T-minus 视界复用）"""
    samples = []
    for b in HIST_BATCHES:
        P = os.path.join(ROOT, 'data', 'tmp', b)
        bp = json.load(open(os.path.join(P, 'blind_parsed.json'), encoding='utf-8'))
        rc = json.load(open(os.path.join(P, 'result_compare.json'), encoding='utf-8'))
        idx = {(r.get('league'), r.get('home'), r.get('away')): r for r in rc}
        for x in bp:
            r = idx.get((x.get('league'), x.get('home'), x.get('away')))
            if not r or r.get('act') not in LAB:
                continue
            ko = parse_dt(x.get('time'))
            if not ko:
                continue
            ser = series_hist(x.get('tl_eu'), x.get('tl_ah'), x.get('tl_ou'), ko)
            if len(ser['eu']) < 2:
                continue
            samples.append({'src': b, 'name': x.get('dir'), 'league': x.get('league'),
                            'label': LAB[r['act']], 'act': r['act'],
                            'score': r.get('score'), 'tot': r.get('tot'),
                            'series': ser, 'ko': ko})

    # 今日类目里已回填赛果的场次（同一 2.5.9 快照结构，可复用澳门通道）
    res = _results_from_snapshots()
    n_snap = 0
    for cat in RESULT_ROOTS:
        base = os.path.join(SNAP_ROOT.replace('竞足', cat))
        if not os.path.isdir(base):
            continue
        for n in os.listdir(base):
            js = os.path.join(base, n, '服务端数据.json')
            if not os.path.exists(js):
                continue
            det = json.load(open(js, encoding='utf-8'))['detail']
            key = (det.get('league'), det.get('home'), det.get('away'))
            r = res.get(key)
            if not r:
                continue
            ser = series_snap(det)
            if len(ser['eu']) < 2:
                continue
            n_snap += 1
            samples.append({'src': 'v2.5.9', 'name': n, 'league': det.get('league'),
                            'label': r['lab'], 'act': ('主胜', '平局', '客胜')[r['lab']],
                            'score': r['score'], 'tot': r['h'] + r['a'],
                            'series': ser, 'ko': parse_dt(det.get('match_time'))})
    return dedupe(samples), n_snap


def collect_targets(batch_dir=None, cutoff='10-18 15:30'):
    """今日未开赛 → 与历史同一特征空间"""
    batch_dir = batch_dir or os.path.join(ROOT, 'data', 'tmp', 'batch_v259W')
    man = json.load(open(os.path.join(batch_dir, '_manifest.json'), encoding='utf-8'))
    out = []
    for m in man:
        if m['mt'] <= cutoff:
            continue
        js = os.path.join(SNAP_ROOT, m['name'], '服务端数据.json')
        if not os.path.exists(js):
            continue
        det = json.load(open(js, encoding='utf-8'))['detail']
        ser = series_snap(det)
        if len(ser['eu']) < 2:
            continue
        out.append({'name': m['name'], 'league': m['lg'], 'mt': m['mt'],
                    'series': ser, 'ko': parse_dt(det.get('match_time')), 'meta': m})
    return out


if __name__ == '__main__':
    S, n_snap = collect_corpus()
    from collections import Counter
    print('历史语料样本:', len(S), '（其中 2.5.9 已回填场次 %d）' % n_snap)
    print('来源分布:', dict(Counter(x['src'] for x in S)))
    print('方向分布:', dict(Counter(x['act'] for x in S)))
    print('联赛数:', len(set(x['league'] for x in S)))
    # 取语料中「有足够历史点」的一场做演示（截断到 T-6h 后仍有 >=2 点）
    demo = next(s for s in S if len(truncate(s['series'], 6.0)['eu']) >= 2)
    f0 = features(truncate(demo['series'], 6.0))
    print('特征维度:', len(f0))
    print('样例(截断 T-6h)·%s:' % demo['name'][:24],
          {k: round(v, 2) for k, v in list(f0.items())[:8]})
    T = collect_targets()
    print()
    print('今日待赛目标:', len(T))
    tf = [features(truncate(t['series'], 6.0)) for t in T]
    print('目标特征维度:', len(tf[0]))
    allk = sorted(set(f0) | set(tf[0]))
    mh = [k for k in allk if k not in f0]
    mt = [k for k in allk if k not in tf[0]]
    print('历史/目标 特征缺失率: %.1f%% / %.1f%%  共有维度 %d' % (
        100 * len(mh) / len(allk), 100 * len(mt) / len(allk), len(allk) - len(set(mh) | set(mt))))
