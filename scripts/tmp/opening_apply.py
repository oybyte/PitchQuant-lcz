#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""opening_apply.py — 把「初盘 → 即盘」结论用到今日 19 场

两个已验证的信号（回测 n=441，严格时间分割 + Bootstrap）：
  K2 初盘热门被推翻 → 终盘热门命中仅 33.3%（对照 59.8%），p=0.0082
     → 用法：降档 / 强制并列，**不是反向押**
  K3 变动幅度 ≥5pp 且热门未变 → 命中 76.8%（对照 57.0%），Bootstrap CI [+0.079,+0.312]
     → 用法：置信度 +1 档（只加标签，不改方向）

今日数据源：data-2.5.9 快照的澳门行 init_* 字段（353 家欧赔里 Macauslot 那条）。
"""
import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import opening_features as OF      # noqa: E402

SNAP = r'F:\ocr_python_data\football-research\data-2.5.9\_by_category\竞足'
BATCH = os.path.join(OF.ROOT, 'data', 'tmp', 'batch_v259W')
OUT = os.path.join(OF.ROOT, 'data', 'tmp', 'opening_today.json')
LAB = {0: '主胜', 1: '平局', 2: '客胜'}


def mac_row(rows, pred):
    return next((r for r in rows if pred(r)), None)


def today_features(det):
    euro = det.get('euro') or []
    asian = det.get('asian') or []
    ou = det.get('ou') or []
    me = mac_row(euro, lambda r: (r.get('company_en') or '') == 'Macauslot')
    ma = mac_row(asian, lambda r: str(r.get('company_id')) == '1')
    mo = mac_row(ou, lambda r: str(r.get('company_id')) == '1')
    F = {}
    if me:
        eo = [OF._f(me.get('init_home')), OF._f(me.get('init_draw')), OF._f(me.get('init_away'))]
        el = [OF._f(me.get('live_home')), OF._f(me.get('live_draw')), OF._f(me.get('live_away'))]
        po, pl = OF.devig(eo), OF.devig(el)
        if po:
            F['o_h'], F['o_d'], F['o_a'] = [x * 100 for x in po]
            srt = sorted(po, reverse=True)
            F['o_skew'] = srt[0] / srt[1] * 100 if srt[1] > 0 else 999
            F['o_fav'] = int(po.index(max(po)))
        if pl:
            F['l_h'], F['l_d'], F['l_a'] = [x * 100 for x in pl]
            F['l_fav'] = int(pl.index(max(pl)))
        if po and pl:
            F['d_h'] = (pl[0] - po[0]) * 100
            F['d_a'] = (pl[2] - po[2]) * 100
            F['dmax'] = max(abs(F['d_h']), abs(F['d_a']))
            F['flip'] = int(F['o_fav'] != F['l_fav'])
    if ma:
        lo = OF.line_val(ma.get('init_line'))
        ll = OF.line_val(ma.get('live_line'))
        if lo is not None:
            F['a_line_o'] = lo
        if ll is not None:
            F['a_line_l'] = ll
        if lo is not None and ll is not None:
            F['a_move'] = ll - lo
        po_ = OF.asian_p(ma.get('init_home'), ma.get('init_away'))
        if po_ is not None:
            F['a_p_o'] = po_ * 100
    if mo:
        t = OF.line_val(mo.get('init_line'))
        if t is not None:
            F['t_line_o'] = t
    # 跨机构初盘盘口分歧
    lv = []
    for r in asian:
        v = r.get('init_line_value')
        if v is None:
            v = OF.line_val(r.get('init_line'))
        if v is not None:
            lv.append(v)
    if len(lv) >= 3:
        F['disp_line'] = max(lv) - min(lv)
        F['n_books'] = len(lv)
    return F


def main():
    man = json.load(open(os.path.join(BATCH, '_manifest.json'), encoding='utf-8'))
    rows = []
    for m in man:
        if m['mt'] <= '10-18 15:30':
            continue
        js = os.path.join(SNAP, m['name'], '服务端数据.json')
        if not os.path.exists(js):
            continue
        det = json.load(open(js, encoding='utf-8'))['detail']
        F = today_features(det)
        if 'o_h' not in F:
            continue
        rows.append({'name': m['name'], 'mt': m['mt'], 'lg': m['lg'], 'F': F})

    print('今日可用 %d 场\n' % len(rows))
    print('%-30s %-6s %-6s %-7s %-7s %-8s %-7s %s' % (
        '场次', '初盘', '即盘', '第1隐', '第2隐', '变动pp', 'skew', '信号'))
    out = []
    for r in rows:
        F = r['F']
        fo = F['o_fav']; fl = F['l_fav']
        flip = fo != fl
        dmax = F.get('dmax', 0)
        if flip:
            sig = '🔴推翻·降档并列'
        elif dmax >= 5:
            sig = '✅大变动·可升档'
        elif dmax >= 3:
            sig = '·中等变动'
        else:
            sig = '—平稳'
        print('%-30s %-6s %-6s %6.1f%% %6.1f%% %+7.1f %6.0f%% %s' % (
            r['name'][:30], LAB[fo], LAB[fl],
            max(F['l_h'], F['l_d'], F['l_a']),
            sorted([F['l_h'], F['l_d'], F['l_a']])[-2],
            dmax, F.get('o_skew', 0), sig))
        out.append(dict(name=r['name'], mt=r['mt'], lg=r['lg'], F=F,
                        open_fav=LAB[fo], late_fav=LAB[fl], flip=bool(flip),
                        dmax=round(dmax, 2), signal=sig))

    n_flip = sum(1 for o in out if o['flip'])
    n_big = sum(1 for o in out if (not o['flip']) and o['dmax'] >= 5)
    print('\n推翻 %d 场 ｜ 大变动未翻 %d 场 ｜ 其余 %d 场' % (n_flip, n_big, len(out) - n_flip - n_big))
    json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('→', OUT)


if __name__ == '__main__':
    main()
