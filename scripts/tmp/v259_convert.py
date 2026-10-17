#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v259_convert.py — data-2.5.9 服务端快照 → 标准竞彩 txt（可复现转换器）

与 2026-10-17 首版一次性脚本的区别：
  · O2.5 折算**调用正式模块** scripts/tmp/ou_from_asia.py（不再内联公式）
  · 体彩让球 L 缺失时**不伪造 +0**（整段不写，下游走三态）
  · 机构基线 = 澳门即盘（唯一带逐点时序的源）；Pinnacle 作交叉校验源

口径:
  · --eu  = 澳门胜平负即盘（与 txt 内时序通道同源）
  · handi = -(亚盘 line_value)   负=主让 / 正=主受让
  · o25/u25 = ou_from_asia.convert(主流线, 上水, 下水)
"""
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import ou_from_asia as OA  # noqa: E402

OUT_BASE = r'F:\ocr_python_data\football-research\data-2.5.9\output'
DEST = os.path.join(ROOT, 'data', 'tmp', 'batch_v259_today')


def _f(x, d=None):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def _find(rows, pred):
    return next((r for r in rows if pred(r)), None)


def build(name):
    d = os.path.join(OUT_BASE, name)
    js = os.path.join(d, '服务端数据.json')
    if not os.path.exists(js):
        return None
    data = json.load(open(js, encoding='utf-8'))
    det = data['detail']
    lg, home, away, mt = det['league'], det['home'], det['away'], det['match_time']
    euro = det.get('euro') or []
    asian = det.get('asian') or []
    ou = det.get('ou') or []
    etl = det.get('euro_timeline') or []

    mac_as = _find(asian, lambda r: str(r.get('company_id')) == '1')
    mac_ou = _find(ou, lambda r: str(r.get('company_id')) == '1')
    pin = _find(euro, lambda r: (r.get('company_en') or '').lower().startswith('pinnacle'))
    mac_eu = _find(euro, lambda r: (r.get('company_en') or '') == 'Macauslot') or pin
    if not (mac_as and mac_ou and mac_eu):
        return {'name': name, 'err': 'missing macao/pinnacle rows'}

    a_init = (_f(mac_as['init_home']), _f(mac_as['init_line_value']), _f(mac_as['init_away']))
    a_live = (_f(mac_as['live_home']), _f(mac_as['live_line_value']), _f(mac_as['live_away']))
    o_init = (_f(mac_ou['init_home']), _f(mac_ou['init_line_value']), _f(mac_ou['init_away']))
    o_live = (_f(mac_ou['live_home']), _f(mac_ou['live_line_value']), _f(mac_ou['live_away']))
    o_line_txt = mac_ou.get('live_line') or ''

    me_init = (_f(mac_eu.get('init_home')), _f(mac_eu.get('init_draw')), _f(mac_eu.get('init_away')))
    me_live = (_f(mac_eu.get('live_home')), _f(mac_eu.get('live_draw')), _f(mac_eu.get('live_away')))
    pi = None
    if pin:
        pi = (_f(pin.get('init_home')), _f(pin.get('init_draw')), _f(pin.get('init_away')))
    mx = (max(_f(r['live_home'], 0) for r in euro),
          max(_f(r['live_draw'], 0) for r in euro),
          max(_f(r['live_away'], 0) for r in euro))
    mn = (min(_f(r['live_home'], 99) for r in euro),
          min(_f(r['live_draw'], 99) for r in euro),
          min(_f(r['live_away'], 99) for r in euro))

    # 🔴 O2.5 调用正式模块（唯一真源）
    conv = OA.convert(o_live[1], o_live[0], o_live[2])
    if not conv.get('supported'):
        return {'name': name, 'err': 'O2.5 折算失败(line=%s)' % o_live[1]}

    handi = -(a_live[1] if a_live[1] is not None else 0.0)
    jcL = _f(data.get('sport_lottery_handicap'), None)
    _rq = _find(euro, lambda r: '让' in (r.get('company') or ''))
    _fts = (data.get('fetched_at') or '2026-10-17 12:00')[:10]
    jc_rq = None
    if _rq and jcL is not None:
        jc_rq = '%s 12:00:00,%s,%s,%s' % (_fts, _rq.get('live_home'), _rq.get('live_draw'), _rq.get('live_away'))

    ser = data.get('sport_lottery_serial') or ''
    jch_s = ('%+g' % jcL) if jcL is not None else '—'
    head = '赛事：%s-%s %s %s(主) VS %s(客)\n' % (ser or 'x', det.get('match_id'), lg, home, away)
    head += '比赛时间：2026-%s 2026/2027赛季\n' % mt.replace(' ', ' ')
    head += '球探ID：%s  体彩期号：%s  体彩主队让球：%s\n' % (det.get('match_id'), ser, jch_s)

    body = '数据来源：football-research data-2.5.9 服务端快照(titan007)·抓取 %s\n\n' % data.get('fetched_at', '')
    body += '亚盘(澳门 主水/盘口/客水)：初 %s / %s / %s → 即 %s / %s / %s\n' % (a_init + a_live)
    body += '大小球(澳门 大球水/盘口/小球水)：初 %s / %s / %s → 即 %s / %s / %s\n' % (o_init + o_live)
    body += '🔴机构通道统一基线 = 澳门胜平负即盘：%g / %g / %g (初盘 %g / %g / %g)\n' % (me_live + me_init)
    if pi:
        body += '欧赔(Pinnacle 即盘·交叉校验源·无逐点时序)：%g / %g / %g (初盘 %g / %g / %g)\n' % (pi[0:3] + pi[0:3])
        body = body.replace('(初盘 %g / %g / %g)\n' % pi[0:3], '(初盘 %g / %g / %g)\n' % pi[0:3])
    body += '跨机构即盘：%d 家 · 最高价 %g/%g/%g · 最低价 %g/%g/%g\n' % ((len(euro),) + mx + mn)
    body += '市场期望总进球：澳门即盘 %s 线(大%s/小%s) 四分之一线EV中性反解 → λ_total=%.3f → 2.5档 P(over)=%.4f → O2.5=%.2f / U2.5=%.2f\n' % (
        o_line_txt or o_live[1], o_live[0], o_live[2], conv['lambda'], conv['p25_over'], conv['o25'], conv['u25'])
    body += '🔴服务端未提供：半全场盘、竞彩总进球盘、比分盘(CS)、凯利逐家时序\n\n'

    mac_eu_tl = []
    for r in reversed(etl):  # 源文件倒序 → 转升序
        m = re.match(r'(\d+)-(\d+)\s+(\d+):(\d+)', r.get('time') or '')
        if m:
            mac_eu_tl.append('2026-%02d-%02d %s:%s:00,%s,%s,%s' % (
                int(m.group(1)), int(m.group(2)), m.group(3), m.group(4),
                r.get('home'), r.get('line'), r.get('away')))

    body += '【特征分析】\n本文件时序通道=澳门胜平负 %d 点(机构通道)\n\n' % len(mac_eu_tl)
    body += '【胜平负固定奖金】\n发布时间,胜,平,负\n' + '\n'.join(mac_eu_tl) + '\n'
    if jcL is not None:
        body += '\n【让球胜平负固定奖金｜让球%+g】\n发布时间,胜,平,负\n' % jcL
        if jc_rq:
            body += jc_rq + '\n'
    body += '\n【半全场胜平负固定奖金】\n发布时间,胜胜,胜平,胜负,平胜,平平,平负,负胜,负平,负负\n'
    body += '\n【总进球固定奖金】\n发布时间,0球,1球,2球,3球,4球,5球,6球,7+球\n'
    body += '\n【比分固定奖金】\n发布时间,1:0,2:0,2:1,3:0,3:1,3:2,4:0,4:1,4:2,胜其它,0:0,1:1,2:2,3:3,平其它,0:1,0:2,1:2,0:3,1:3,2:3,0:4,1:4,负其它\n'

    return {'name': name, 'lg': lg, 'home': home, 'away': away, 'mt': mt, 'main': head + '\n' + body,
            'eu': '%.2f,%.2f,%.2f' % me_live,
            'eu_pin': ('%.2f,%.2f,%.2f' % pi) if pi else None,
            'handi': handi, 'jch': jcL,
            'o25': conv['o25'], 'u25': conv['u25'], 'lam': conv['lambda'],
            'water': (a_live[0] + 1.0) if a_live[0] is not None else None,
            'ou_line': o_line_txt or o_live[1], 'n_euro': len(euro)}


def main():
    os.makedirs(DEST, exist_ok=True)
    names = [n for n in sorted(os.listdir(OUT_BASE))
             if os.path.isdir(os.path.join(OUT_BASE, n)) and not n.startswith('_')]
    man = []
    for n in names:
        md = os.path.join(OUT_BASE, n, '服务端数据.md')
        if not os.path.exists(md):
            continue
        if '未填写赛果' not in open(md, encoding='utf-8').read():
            continue
        r = build(n)
        if not r or r.get('err'):
            print('SKIP', n, (r or {}).get('err')); continue
        base = n.replace(' ', '_').replace('(', '').replace(')', '')
        open(os.path.join(DEST, base + '.txt'), 'w', encoding='utf-8').write(r['main'])
        man.append({k: v for k, v in r.items() if k != 'main'})
        print('OK  %-44s %-6s handi=%+.2f O2.5=%.3f λ=%.3f' % (n[:44], r['lg'], r['handi'], r['o25'], r['lam']))
    json.dump(man, open(os.path.join(DEST, '_manifest.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('TOTAL', len(man))


if __name__ == '__main__':
    main()
