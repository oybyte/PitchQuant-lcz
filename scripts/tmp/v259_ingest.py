#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v259_ingest.py — data-2.5.9 单场快照 → 标准竞彩 txt（唯一真源·阶段2）

合并并取代
----------
  v259_convert.py    （output/ 目录版·取 live 但基线口径不同）
  v259d_convert.py   （_by_category/单场 版·阶段1前手写）
两者差异只在路径与零散字段，长期并行会导致「换一份转换器就换一套数值」。

🔴 2026-10-18：上述两个旧脚本**已删除**（本文件为唯一实现）。
   ⚠️ 例外：`prep_14.py` 是自包含的专用脚本（产出公众通道 txt + 机构明细 json），
   与本文件职责不同，保留；它无代码级依赖。

相对旧版修复的三个口径问题（均由阶段1检查器在真实批次上实测暴露）
--------------------------------------------------------------
  VB11  联赛基准整批未命中
        calc_match.LEAGUE_VIG 的键是英文 slug（epl/bundesliga/seriea），
        调用方一直传中文「英超」→ 26/26 场走「缺省6.9%」。
        修法不动任何计算：本模块同时输出 lg_slug，跑步器把 slug 传给 calc_all，
        calc_all 内部 norm_league('epl') 仍得「英超」，两边同时命中。

  FRESH 时点新鲜度不透明
        本模块把「【胜平负】末点距开赛分钟数」直接写进 txt 头部，
        下游无需重算即可判定 V6 是否适用；并在 meta 里给出 LIVE/SEMI/STALE。

  VIG   抽水基准名实不符（标签层，不改数值）
        基线来自机构价时，头部显式写「本条基线=机构价，反抽水比(F1) 不适用」，
        避免下游把机构抽水读成竞彩抽水。

新增（信息损失修复）
--------------------
  · 多机构合并去水：复用 market_consensus.merge_devig（抽水倒数加权），
    同时给出等权对照，喂 Step5 作交叉校验（AGENTS「机构数据双用途铁律」）
  · 跨机构方向一致率：多少家与基线同向（不只是最高/最低价）

用法
----
    python scripts/tmp/v259_ingest.py --src <单场目录> --out <输出目录>
    python scripts/tmp/v259_ingest.py --src <单场目录> --out <输出目录> --pinnacle
    python scripts/tmp/v259_ingest.py --src <单场目录> --check     # 只体检不落盘
退出码: 0 成功; 1 存在无法转换的场次; 2 用法错误
"""
import argparse
import datetime
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import ou_from_asia as OA  # noqa: E402
import opening_shift as S4  # noqa: E402  S4 初盘位移（单一真源·只加标签不改方向）

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

DEFAULT_SRC = r'F:\ocr_python_data\football-research\data-2.5.9\_by_category\单场'

# 中文联赛 → calc_match.LEAGUE_VIG 的英文 slug（五大联赛 + 已登记联赛）
# 🔴这是「基准表键」而不是「联赛显示名」，两者用途不同不可混用
LG_SLUG = {
    '英超': 'epl', '英冠': 'championship', '英甲': 'league1', '英乙': 'league2',
    '德甲': 'bundesliga', '德乙': 'bundesliga2',
    '意甲': 'seriea', '意乙': 'seriea',
    '西甲': 'laliga', '西乙': 'laliga',
    '法甲': 'ligue1', '法乙': 'ligue1',
    '荷甲': 'eredivisie', '荷乙': 'eredivisie',
    '葡超': 'portugal', '芬超': 'finland', '芬超冠': 'finland',
    '挪超': 'norway', '日职联': 'japan', '日职乙': 'japan',
    # 🔴 2026-10-18 修正：韩K联 原映射到 china —— 语义错误。
    #   LEAGUE_VIG 无韩国项（只有 japan/china），且两国联赛盘口特征不同。
    #   正确做法：不映射 → 走「未登记」三态，而不是借用中超基准。
    '中超': 'china', '欧冠': 'ec', '欧联': 'ec', '欧协联': 'ec',
}

# 以下市场在本数据结构下只有「抓取时刻」单行，不是真时序
PSEUDO_SERIES_SECTIONS = ('让球胜平负固定奖金', '半全场胜平负固定奖金',
                          '总进球固定奖金', '比分固定奖金')


def _f(x, d=None):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def _find(rows, pred):
    return next((r for r in rows if pred(r)), None)


def _dt(s):
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%m-%d %H:%M'):
        try:
            d = datetime.datetime.strptime(s.strip(), fmt)
            if fmt == '%m-%d %H:%M':
                d = d.replace(year=datetime.datetime.now().year)
            return d
        except (ValueError, AttributeError):
            continue
    return None


def _parse_kickoff(mt, fetched):
    """服务端 match_time 形如 '2026-10-17 19:30'，也兼容 '10-17 19:30'"""
    m = re.match(r'(?:(\d{4})-)?(\d{2})-(\d{2})\s+(\d{2}):(\d{2})', (mt or '').strip())
    if not m:
        return None
    y, mo, d, hh, mi = m.groups()
    if not y:
        y = str(fetched.year) if fetched else '2026'
        if fetched and int(mo) + 6 < fetched.month:
            y = str(int(y) + 1)
    try:
        return datetime.datetime(int(y), int(mo), int(d), int(hh), int(mi))
    except ValueError:
        return None


def freshness(ko, series):
    """→ (minutes, band)  band: LIVE ≤90 / SEMI ≤180 / STALE / UNKNOWN"""
    if not ko or not series:
        return None, 'UNKNOWN'
    mins = (ko - max(series)).total_seconds() / 60.0
    if mins <= 90:
        return mins, 'LIVE'
    if mins <= 180:
        return mins, 'SEMI'
    return mins, 'STALE'


def _consensus(euro):
    """多机构合并去水 + 方向一致率（复用 market_consensus，失败则自算）"""
    books = []
    for r in euro:
        h, d, a = _f(r.get('live_home')), _f(r.get('live_draw')), _f(r.get('live_away'))
        if not (h and d and a) or min(h, d, a) <= 1.01:
            continue
        books.append({'bookmaker': r.get('company') or r.get('company_en') or '?',
                      'h': h, 'd': d, 'a': a})
    if not books:
        return None
    out = {'n_books': len(books)}
    try:
        import market_consensus as MC
        md = MC.merge_devig(books)
        if md:
            out.update({'pH': md['pH'], 'pD': md['pD'], 'pA': md['pA'],
                        'p_equal': md['p_equal'],
                        'margin_mean': md['margin_mean'],
                        'margin_min': md['margin_min'],
                        'favorite': md['favorite'], 'source': 'market_consensus'})
    except Exception:
        pass
    if 'pH' not in out:                     # 自算兜底（口径一致：抽水倒数加权）
        inv = [(1 / b['h'], 1 / b['d'], 1 / b['a'],
                max(1e-4, 1 / b['h'] + 1 / b['d'] + 1 / b['a'] - 1)) for b in books]
        w = [1.0 / x[3] for x in inv]
        tw = sum(w)
        ph = sum(x[0] * wi for x, wi in zip(inv, w)) / tw
        pd = sum(x[1] * wi for x, wi in zip(inv, w)) / tw
        pa = sum(x[2] * wi for x, wi in zip(inv, w)) / tw
        t = ph + pd + pa
        out.update({'pH': round(ph / t, 4), 'pD': round(pd / t, 4), 'pA': round(pa / t, 4),
                    'margin_mean': round(sum(x[3] for x in inv) / len(inv), 4),
                    'margin_min': round(min(x[3] for x in inv), 4),
                    'favorite': ['H', 'D', 'A'][max(range(3), key=lambda i: (ph, pd, pa)[i])],
                    'source': 'inline'})
    # 方向一致率：与合并去水后的最大向同向的家数
    fav = out['favorite']
    agree = 0
    for b in books:
        inv = (1 / b['h'], 1 / b['d'], 1 / b['a'])
        t = sum(inv)
        f = ['H', 'D', 'A'][max(range(3), key=lambda i: inv[i] / t)]
        agree += (f == fav)
    out['dir_agree'] = agree
    return out


def read_snapshot(match_dir):
    """读取并校验一场快照 → dict（缺关键行则抛 ValueError，绝不静默降级）"""
    js = os.path.join(match_dir, '服务端数据.json')
    if not os.path.exists(js):
        raise ValueError('缺少 服务端数据.json')
    data = json.load(open(js, encoding='utf-8'))
    det = data.get('detail') or {}
    euro = det.get('euro') or []
    asian = det.get('asian') or []
    ou = det.get('ou') or []
    if not euro:
        raise ValueError('euro 为空')

    mac_as = _find(asian, lambda r: str(r.get('company_id')) == '1')
    mac_ou = _find(ou, lambda r: str(r.get('company_id')) == '1')
    mac_eu = _find(euro, lambda r: (r.get('company_en') or '') == 'Macauslot')
    pin = _find(euro, lambda r: (r.get('company_en') or '').lower().startswith('pinnacle'))
    if not mac_as:
        raise ValueError('缺少澳门亚盘行(company_id=1)')
    if not mac_ou:
        raise ValueError('缺少澳门大小球行(company_id=1)')
    if not (mac_eu or pin):
        raise ValueError('澳门与 Pinnacle 胜平负行均缺失')

    o_line = _f(mac_ou.get('live_line_value'))
    o_over = _f(mac_ou.get('live_home'))
    if o_line is None or o_over is None:
        raise ValueError('澳门大小球即盘不完整')
    conv = OA.convert(o_line, o_over, _f(mac_ou.get('live_away')))
    if not conv.get('supported'):
        raise ValueError('O2.5 折算失败(线型 %s 未登记)' % o_line)

    return {'data': data, 'det': det, 'euro': euro, 'asian': asian, 'ou': ou,
            'mac_as': mac_as, 'mac_ou': mac_ou, 'mac_eu': mac_eu, 'pin': pin,
            'conv': conv}


def build(match_dir, baseline='macao', emit_series=True):
    """→ dict(main=txt文本, meta=结构化字段)"""
    S = read_snapshot(match_dir)
    data, det = S['data'], S['det']
    euro, asian, ou = S['euro'], S['asian'], S['ou']
    mac_as, mac_ou, mac_eu, pin, conv = (S['mac_as'], S['mac_ou'], S['mac_eu'],
                                         S['pin'], S['conv'])

    lg_cn = det.get('league') or '未知'
    lg_slug = LG_SLUG.get(lg_cn)
    home, away, mt = det.get('home'), det.get('away'), det.get('match_time')
    fetched = _dt(data.get('fetched_at') or '') or _dt(det.get('fetched_at') or '')
    ko = _parse_kickoff(mt, fetched)

    # ── 基线选择：澳门 / Pinnacle ──
    if baseline == 'pinnacle':
        base_row, base_tag = (pin, 'Pinnacle') if pin else (mac_eu, '澳门(Pinnacle缺失)')
    else:
        base_row, base_tag = (mac_eu, '澳门') if mac_eu else (pin, 'Pinnacle(澳门缺失)')
    if base_row is None:
        raise ValueError('所选基线行不存在: %s' % baseline)

    def _o(row, kind):
        if kind == 'init':
            return (_f(row.get('init_home')), _f(row.get('init_draw')), _f(row.get('init_away')))
        return (_f(row.get('live_home')), _f(row.get('live_draw')), _f(row.get('live_away')))

    base_live = _o(base_row, 'live')
    base_init = _o(base_row, 'init')
    if min([x for x in base_live if x] or [0]) <= 1.0:
        raise ValueError('基线即盘赔率非法: %s' % (base_live,))

    a_live = (_f(mac_as.get('live_home')), _f(mac_as.get('live_line_value')),
              _f(mac_as.get('live_away')))
    a_init = (_f(mac_as.get('init_home')), _f(mac_as.get('init_line_value')),
              _f(mac_as.get('init_away')))
    o_live = (_f(mac_ou.get('live_home')), _f(mac_ou.get('live_line_value')),
              _f(mac_ou.get('live_away')))
    o_init = (_f(mac_ou.get('init_home')), _f(mac_ou.get('init_line_value')),
              _f(mac_ou.get('init_away')))
    o_line_txt = mac_ou.get('live_line') or '%g' % o_live[1]
    a_line_txt = mac_as.get('live_line') or '%g' % a_live[1]

    # ── 跨机构 ──
    valid = [r for r in euro if all(_f(r.get(k), 0) > 1.01
                                    for k in ('live_home', 'live_draw', 'live_away'))]
    mx = tuple(max(_f(r[k]) for r in valid)
               for k in ('live_home', 'live_draw', 'live_away'))
    mn = tuple(min(_f(r[k]) for r in valid)
               for k in ('live_home', 'live_draw', 'live_away'))
    cons = _consensus(euro)

    # ── 时序通道（只有澳门胜平负是真时序）──
    etl = det.get('euro_timeline') or []
    series = []
    for r in reversed(etl):
        m = re.match(r'(\d+)-(\d+)\s+(\d+):(\d+)', r.get('time') or '')
        if not m:
            continue
        y = fetched.year if fetched else datetime.datetime.now().year
        try:
            ts = datetime.datetime(y, int(m.group(1)), int(m.group(2)),
                                   int(m.group(3)), int(m.group(4)))
        except ValueError:
            continue
        if fetched and ts > fetched:
            try:
                ts = ts.replace(year=y - 1)
            except ValueError:
                pass
        series.append(('2026-%02d-%02d %s:%s:00' % (int(m.group(1)), int(m.group(2)),
                                                   m.group(3), m.group(4)),
                       r.get('home'), r.get('line'), r.get('away')))
    series_times = [t for t in (_dt(s[0]) for s in series) if t]

    # 基线单点时，把基线这条也补进序列（保持「末行=当前定价」的不变式）
    if not series_times and base_live and all(base_live):
        ts_txt = (fetched.strftime('%Y-%m-%d %H:%M:%S') if fetched else '2026-01-01 12:00:00')
        series = [(ts_txt, '%g' % base_live[0], '%g' % base_live[1], '%g' % base_live[2])]
        series_times = [_dt(ts_txt)]
        series_is_pseudo = True
    else:
        series_is_pseudo = False

    _soft = ('澳门' in base_tag)
    mins, band = freshness(ko, series_times)
    band_cn = {'LIVE': '临场', 'SEMI': '次临场', 'STALE': '非临场', 'UNKNOWN': '无法判定'}[band]
    v6_ok = {'LIVE': '✅ 可判定', 'SEMI': '⚠️ 仅弱参考', 'STALE': '❌ 不适用(原因:非临场)',
             'UNKNOWN': '❌ 不适用(原因:时点缺失)'}[band]

    # 序列是否等于基线（决定「竞彩抽水」标签能否成立）
    series_equals_base = False
    if series and base_live and all(base_live):
        try:
            h, d, a = (float(series[-1][1]), float(series[-1][2]), float(series[-1][3]))
            series_equals_base = all(abs(v - b) < 0.005 for v, b in zip((h, d, a), base_live))
        except (TypeError, ValueError):
            series_equals_base = False

    jcL = _f(data.get('sport_lottery_handicap'), None)
    jc_ml = _find(euro, lambda r: (r.get('company') or '') == '体彩官方')
    jc_rq = _find(euro, lambda r: '让' in (r.get('company') or ''))
    ser = data.get('sport_lottery_serial') or ''

    handi = -(a_live[1] if a_live[1] is not None else 0.0)

    L = []
    L.append('赛事：%s-%s %s %s(主) VS %s(客)' % (ser or 'x', det.get('match_id') or '', lg_cn, home, away))
    L.append('比赛时间：%s 2026/2027赛季' % mt)
    L.append('球探ID：%s  体彩期号：%s  体彩主队让球：%s' % (
        det.get('match_id') or '', ser, ('%+g' % jcL) if jcL is not None else '—'))
    L.append('')
    L.append('数据来源：football-research data-2.5.9 服务端快照(titan007)·抓取 %s' % (
        data.get('fetched_at') or '—'))
    L.append('🔴联赛基准键：%s → LEAGUE_VIG slug=%s %s' % (
        lg_cn, lg_slug or '—',
        '(calc_match 抽水基准可查表)' if lg_slug else '(该联赛未登记 → 基准须标 无数据)'))
    L.append('')
    L.append('亚盘(澳门 主水/盘口/客水)：初 %s / %s / %s → 即 %s / %s / %s' % (
        a_init[0], mac_as.get('init_line'), a_init[2], a_live[0], a_line_txt, a_live[2]))
    L.append('大小球(澳门 大球水/盘口/小球水)：初 %s / %s / %s → 即 %s / %s / %s' % (
        o_init[0], mac_ou.get('init_line'), o_init[2], o_live[0], o_line_txt, o_live[2]))
    L.append('🔴机构通道统一基线 = %s胜平负即盘：%g / %g / %g (初盘 %g / %g / %g)' % (
        base_tag, base_live[0], base_live[1], base_live[2],
        base_init[0], base_init[1], base_init[2]))
    # 🔴 S4 初盘位移（2026-10-19）：base_init/base_live 已是本函数的真初盘与即盘，
    # 直接复用，禁止重读快照。只产出标签行，判定权仍在模型。
    L.append(S4.signal_line(S4.compute_shift(base_init, base_live)))
    if pin:
        pv = _o(pin, 'live')
        L.append('欧赔(Pinnacle 即盘·交叉校验源)：%g / %g / %g' % pv)
    L.append('跨机构即盘：%d 家 · 最高价 %g/%g/%g · 最低价 %g/%g/%g' % ((len(valid),) + mx + mn))
    if cons:
        L.append('🔴多机构合并去水(%d 家·抽水倒数加权·源:%s)：主 %.1f%% / 平 %.1f%% / 客 %.1f%% '
                 '｜ 等权对照 主 %.1f%% / 平 %.1f%% / 客 %.1f%% ｜ 平均抽水 %.2f%%(最低 %.2f%%) '
                 '｜ 与合并方向同向 %d/%d 家' % (
                     cons['n_books'], cons.get('source', '?'), cons['pH'] * 100, cons['pD'] * 100,
                     cons['pA'] * 100,
                     (cons.get('p_equal') or [0, 0, 0])[0] * 100,
                     (cons.get('p_equal') or [0, 0, 0])[1] * 100,
                     (cons.get('p_equal') or [0, 0, 0])[2] * 100,
                     cons['margin_mean'] * 100, cons['margin_min'] * 100,
                     cons.get('dir_agree', 0), cons['n_books']))
    L.append('市场期望总进球：澳门即盘 %s 线(大%s/小%s) 四分之一线EV中性反解 → λ_total=%.3f '
             '→ 2.5档 P(over)=%.4f → O2.5=%.2f / U2.5=%.2f' % (
                 o_line_txt, o_live[0], o_live[2], conv['lambda'], conv['p25_over'],
                 conv['o25'], conv['u25']))
    L.append('')
    L.append('🔴时点新鲜度：【胜平负】%d 个时点 · 末点 %s · 距开赛 %s 分钟 → %s ｜ 盘口联动(V6): %s' % (
        len(series), (series[-1][0] if series else '—'),
        ('%.0f' % mins) if mins is not None else '未知', band_cn, v6_ok))
    L.append('🔴基线性质：%s (%s) — 软盘=含较高抽水·锐盘=低抽水高频覆盖' % (
        'soft' if _soft else 'sharp', base_tag))
    L.append('🔴抽水基准说明：基线取自 %s 机构价%s → %s' % (
        base_tag,
        ('（本文件无独立竞彩采价，序列即基线）' if series_equals_base else ''),
        '反抽水比(F1) **不适用(无独立竞彩源)**·禁读作「竞彩抽水」·标签=基准价抽水'
        if series_equals_base else
        ('本文件时序通道独立于基线；但基线为锐盘，LEAGUE_VIG 是软盘基准 → 反抽水比不适用(不同源)'
         if not _soft else '本文件时序通道独立于基线，可作反抽水比较')))
    if jc_ml:
        L.append('竞彩官方胜平负即盘：%s / %s / %s' % (
            jc_ml.get('live_home'), jc_ml.get('live_draw'), jc_ml.get('live_away')))
    else:
        L.append('🔴竞彩官方胜平负：missing(本场快照未含「体彩官方」行·让球盘仍可用)')
    L.append('🔴服务端未提供：半全场盘、竞彩总进球盘、比分盘(CS)、凯利逐家时序')
    L.append('')
    L.append('【特征分析】')
    L.append('本文件时序通道=澳门胜平负 %d 点(机构通道)' % len(series))
    for label, key in (('亚盘', 'asian_timeline'), ('大小', 'ou_timeline')):
        tl = det.get(key) or []
        L.append('澳门%s时序(%d 点)：' % (label, len(tl)))
        for r in reversed(tl):
            m = re.match(r'(\d+)-(\d+)\s+(\d+):(\d+)', r.get('time') or '')
            if m:
                L.append('2026-%02d-%02d %s:%s:00 %s %s / %s / %s' % (
                    int(m.group(1)), int(m.group(2)), m.group(3), m.group(4), label,
                    r.get('home'), r.get('line_ocr') or r.get('line'), r.get('away')))
    L.append('')
    L.append('【胜平负固定奖金】')
    L.append('发布时间,胜,平,负')
    for ts, h, d, a in series:
        L.append('%s,%s,%s,%s' % (ts, h, d, a))
    if jcL is not None and jc_rq:
        L.append('')
        L.append('【让球胜平负固定奖金｜让球%+g】' % jcL)
        L.append('发布时间,胜,平,负')
        L.append('%s,%s,%s,%s' % (data.get('fetched_at') or '2026-01-01 12:00:00',
                                  jc_rq.get('live_home'), jc_rq.get('live_draw'),
                                  jc_rq.get('live_away')))
    elif jcL is not None:
        L.append('')
        L.append('🔴让球盘：missing(快照未含「体彩官方让球」行·体彩L=%+g 仍可用于亚盘对照)' % jcL)
    L.append('')
    L.append('【半全场胜平负固定奖金】')
    L.append('发布时间,胜胜,胜平,胜负,平胜,平平,平负,负胜,负平,负负')
    L.append('')
    L.append('【总进球固定奖金】')
    L.append('发布时间,0球,1球,2球,3球,4球,5球,6球,7+球')
    L.append('')
    L.append('【比分固定奖金】')
    L.append('发布时间,1:0,2:0,2:1,3:0,3:1,3:2,4:0,4:1,4:2,胜其它,0:0,1:1,2:2,3:3,平其它,'
             '0:1,0:2,1:2,0:3,1:3,2:3,0:4,1:4,负其它')

    meta = {
        'name': os.path.basename(match_dir.rstrip('\\/')),
        'lg': lg_cn, 'lg_slug': lg_slug, 'home': home, 'away': away, 'mt': mt,
        'baseline': baseline, 'base_tag': base_tag,
        'eu': '%.2f,%.2f,%.2f' % base_live,
        'eu_pin': ('%.2f,%.2f,%.2f' % _o(pin, 'live')) if pin else None,
        'handi': handi, 'jch': jcL,
        'o25': conv['o25'], 'u25': conv['u25'], 'lam': conv['lambda'],
        'water': (a_live[0] + 1.0) if a_live[0] is not None else None,
        'ou_line': o_line_txt, 'ah_line': a_line_txt,
        'n_euro': len(valid), 'n_asian': len(asian), 'n_ou': len(ou),
        'jc_ml': bool(jc_ml), 'jc_rq': bool(jc_rq),
        'series_points': len(series), 'series_is_pseudo': series_is_pseudo,
        'series_equals_base': series_equals_base,
        'baseline_kind': 'soft' if _soft else 'sharp',
        'minutes_before_ko': round(mins, 1) if mins is not None else None,
        'band': band, 'v6': v6_ok,
        'consensus': cons,
    }
    return {'main': '\n'.join(L) + '\n', 'meta': meta, 'match_dir': match_dir}


def _safe_base(name):
    return name.replace(' ', '_').replace('(', '').replace(')', '')


def main():
    ap = argparse.ArgumentParser(description='data-2.5.9 单场快照 → 标准竞彩 txt（唯一真源）')
    ap.add_argument('--src', default=DEFAULT_SRC, help='快照根目录（含若干场次子目录）')
    ap.add_argument('--out', required=False, help='输出目录（批）或 txt 路径（单场）')
    ap.add_argument('--pinnacle', action='store_true', help='基线改用 Pinnacle（交叉校验）')
    ap.add_argument('--suffix', default='', help='输出文件名后缀（如 .pin）')
    ap.add_argument('--check', action='store_true', help='只体检，不落盘')
    a = ap.parse_args()

    if not os.path.isdir(a.src):
        print('源目录不存在: %s' % a.src, file=sys.stderr)
        return 2

    names = sorted(n for n in os.listdir(a.src)
                   if os.path.isdir(os.path.join(a.src, n)) and not n.startswith('_'))
    if not names:
        print('源目录内无场次子目录: %s' % a.src, file=sys.stderr)
        return 2

    single = a.out and a.out.lower().endswith('.txt')
    if a.out and not a.check and not single:
        os.makedirs(a.out, exist_ok=True)

    ok, failed, meta_all = [], [], []
    print('%-42s %-7s %-6s %-8s %-7s %s' % ('场次', '联赛', 'slug', '距开赛', '新鲜度', 'O2.5'))
    print('-' * 96)
    for n in names:
        d = os.path.join(a.src, n)
        try:
            r = build(d, baseline='pinnacle' if a.pinnacle else 'macao')
        except Exception as e:
            failed.append((n, str(e)))
            print('%-42s ❌ %s' % (n[:42], e))
            continue
        m = r['meta']
        ok.append(n)
        meta_all.append(m)
        print('%-42s %-7s %-6s %-8s %-7s %.3f' % (
            n[:42], m['lg'], m['lg_slug'] or '—',
            ('%.0f' % m['minutes_before_ko']) if m['minutes_before_ko'] is not None else '—',
            m['band'], m['o25']))
        if a.check:
            continue
        path = a.out if single else os.path.join(a.out, _safe_base(n) + a.suffix + '.txt')
        open(path, 'w', encoding='utf-8').write(r['main'])

    if not a.check and a.out and not single:
        # 按 suffix 分别落 manifest，避免 Pinnacle 轮覆盖澳门轮的清单
        mname = '_manifest%s.json' % (a.suffix or '')
        json.dump(meta_all, open(os.path.join(a.out, mname), 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=1)

    bands = {}
    for m in meta_all:
        bands[m['band']] = bands.get(m['band'], 0) + 1
    print()
    print('成功 %d ｜ 失败 %d ｜ 新鲜度 %s' % (
        len(ok), len(failed),
        ' / '.join('%s %d' % (k, v) for k, v in sorted(bands.items()))))
    if failed:
        print('🔴 无法转换（必须修数据源，禁止静默跳过）:')
        for n, e in failed:
            print('  · %s — %s' % (n[:50], e))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
