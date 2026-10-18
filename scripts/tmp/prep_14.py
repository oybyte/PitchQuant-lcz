#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prep_14.py — _by_category/14场 → 标准输入 txt + manifest

（历史：模板最初取自 v259_convert；该脚本已于 2026-10-18 并入 v259_ingest 并删除。
  本脚本仍自包含，无代码级依赖，仅保留其专用产物：公众通道 txt + 机构明细 json。）

与其他转换脚本的差异:
  · 源目录改为 _by_category/14场（json 与 output 内同源，逐字节校验一致）
  · 保留服务端未提供的节（半全场/总进球/比分）为空表头 → 下游三态 missing
  · 额外产出: 公众通道(体彩官方) txt + 跨机构最高/最低价 + 全量机构明细 json
"""
import json, os, re, sys
sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, 'scripts', 'tmp'))
import ou_from_asia as OA  # noqa: E402

SRC = r'F:\ocr_python_data\football-research\data-2.5.9\_by_category\14场'
DEST = os.path.join(ROOT, 'data', 'tmp', 'batch_14')


def f(x, d=None):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def build(name):
    d = os.path.join(SRC, name)
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
    mac_as = next((r for r in asian if str(r.get('company_id')) == '1'), None)
    mac_ou = next((r for r in ou if str(r.get('company_id')) == '1'), None)
    pin = next((r for r in euro if (r.get('company_en') or '').lower().startswith('pinnacle')), None)
    mac_eu = next((r for r in euro if (r.get('company_en') or '') == 'Macauslot'), None) or pin
    if not (mac_as and mac_ou and mac_eu):
        return {'name': name, 'err': 'missing macao/pinnacle rows'}

    a_init = (f(mac_as['init_home']), f(mac_as['init_line_value']), f(mac_as['init_away']))
    a_live = (f(mac_as['live_home']), f(mac_as['live_line_value']), f(mac_as['live_away']))
    o_init = (f(mac_ou['init_home']), f(mac_ou['init_line_value']), f(mac_ou['init_away']))
    o_live = (f(mac_ou['live_home']), f(mac_ou['live_line_value']), f(mac_ou['live_away']))
    o_line_txt = mac_ou.get('live_line') or ''
    me_init = (f(mac_eu.get('init_home')), f(mac_eu.get('init_draw')), f(mac_eu.get('init_away')))
    me_live = (f(mac_eu.get('live_home')), f(mac_eu.get('live_draw')), f(mac_eu.get('live_away')))
    pi = (f(pin.get('init_home')), f(pin.get('init_draw')), f(pin.get('init_away'))) if pin else None
    mx = (max(f(r['live_home'], 0) for r in euro), max(f(r['live_draw'], 0) for r in euro),
          max(f(r['live_away'], 0) for r in euro))
    mn = (min(f(r['live_home'], 99) for r in euro), min(f(r['live_draw'], 99) for r in euro),
          min(f(r['live_away'], 99) for r in euro))

    conv = OA.convert(o_live[1], o_live[0], o_live[2])
    if not conv.get('supported'):
        return {'name': name, 'err': 'O2.5 折算失败(line=%s)' % (o_live[1],)}

    handi = -(a_live[1] if a_live[1] is not None else 0.0)
    jcL = f(data.get('sport_lottery_handicap'), None)
    rq = next((r for r in euro if '让' in (r.get('company') or '')), None)
    fts = (data.get('fetched_at') or '2026-10-17 12:00')[:10]
    jc_rq = None
    if rq and jcL is not None:
        jc_rq = '%s 12:00:00,%s,%s,%s' % (fts, rq.get('live_home'), rq.get('live_draw'), rq.get('live_away'))
    off = next((r for r in euro if (r.get('company') or '') == '体彩官方'), None)
    ser = data.get('sport_lottery_serial') or ''
    jch_s = ('%+g' % jcL) if jcL is not None else '—'

    head = '赛事：%s-%s %s %s(主) VS %s(客)\n' % (ser or 'x', det.get('match_id'), lg, home, away)
    head += '比赛时间：2026-%s 2026/2027赛季\n' % mt
    head += '球探ID：%s  体彩期号：%s  体彩主队让球：%s\n' % (det.get('match_id'), ser, jch_s)

    body = '数据来源：football-research data-2.5.9 _by_category/14场 服务端快照(titan007)·抓取 %s\n\n' % data.get('fetched_at', '')
    body += '亚盘(澳门 主水/盘口/客水)：初 %s / %s / %s → 即 %s / %s / %s\n' % (a_init + a_live)
    body += '大小球(澳门 大球水/盘口/小球水)：初 %s / %s / %s → 即 %s / %s / %s\n' % (o_init + o_live)
    body += '🔴机构通道统一基线 = 澳门胜平负即盘：%g / %g / %g (初盘 %g / %g / %g)\n' % (me_live + me_init)
    if pi:
        body += '欧赔(Pinnacle 即盘·交叉校验源·无逐点时序)：%g / %g / %g (初盘 %g / %g / %g)\n' % (pi[0:3] + pi[0:3])
    body += '跨机构即盘：%d 家 · 最高价 %g/%g/%g · 最低价 %g/%g/%g\n' % ((len(euro),) + mx + mn)
    body += '市场期望总进球：澳门即盘 %s 线(大%s/小%s) 四分之一线EV中性反解 → λ_total=%.3f → 2.5档 P(over)=%.4f → O2.5=%.2f / U2.5=%.2f\n' % (
        o_line_txt or o_live[1], o_live[0], o_live[2], conv['lambda'], conv['p25_over'], conv['o25'], conv['u25'])
    body += '🔴服务端未提供：半全场盘、竞彩总进球盘、比分盘(CS)、凯利逐家时序\n\n'

    mac_eu_tl = []
    for r in reversed(etl):
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
    body += '\n【比分固定奖金】\n发布时间,胜其它,0:0,1:1,2:2,3:3,平其它,0:1,0:2,1:2,0:3,1:3,2:3,0:4,1:4,负其它\n'

    # ── 公众通道（体彩官方）──
    jc = head + '\n数据来源：football-research data-2.5.9 _by_category/14场·体彩官方(公众通道·单点)\n\n'
    jc += '亚盘(澳门 主水/盘口/客水)：初 %s / %s / %s → 即 %s / %s / %s\n' % (a_init + a_live)
    jc += '大小球(澳门 大球水/盘口/小球水)：初 %s / %s / %s → 即 %s / %s / %s\n' % (o_init + o_live)
    jc += '欧赔(机构通道基线=澳门即盘)：%g / %g / %g ｜ Pinnacle 即盘(交叉校验)：%s\n' % (
        me_live + ((('%g / %g / %g' % pi) if pi else '无数据'),))
    jc += '\n【特征分析】\n本文件时序通道=体彩官方(公众通道·单点)\n\n'
    jc += '【胜平负固定奖金】\n发布时间,胜,平,负\n'
    if off:
        jc += '%s 12:00:00,%s,%s,%s\n' % (fts, off.get('live_home'), off.get('live_draw'), off.get('live_away'))
    if jcL is not None:
        jc += '\n【让球胜平负固定奖金｜让球%+g】\n发布时间,胜,平,负\n' % jcL
        if jc_rq:
            jc += jc_rq + '\n'
    jc += '\n【半全场胜平负固定奖金】\n发布时间,胜胜,胜平,胜负,平胜,平平,平负,负胜,负平,负负\n'
    jc += '\n【总进球固定奖金】\n发布时间,0球,1球,2球,3球,4球,5球,6球,7+球\n'
    jc += '\n【比分固定奖金】\n发布时间,胜其它,0:0,1:1,2:2,3:3,平其它,0:1,0:2,1:2,0:3,1:3,2:3,0:4,1:4,负其它\n'

    return {'name': name, 'lg': lg, 'home': home, 'away': away, 'mt': mt, 'main': head + '\n' + body, 'jc': jc,
            'eu': '%.2f,%.2f,%.2f' % me_live, 'eu_pin': ('%.2f,%.2f,%.2f' % pi) if pi else None,
            'eu_jc': ('%.2f,%.2f,%.2f' % (f(off['live_home']), f(off['live_draw']), f(off['live_away']))) if off else None,
            'handi': handi, 'handi_txt': mac_as.get('live_line') or '', 'jch': jcL,
            'o25': round(conv['o25'], 3), 'u25': round(conv['u25'], 3), 'lam': round(conv['lambda'], 3),
            'p25': round(conv['p25_over'], 4),
            'water': round(a_live[0] + 1.0, 3) if a_live[0] is not None else None,
            'ou_line': o_line_txt or o_live[1], 'n_euro': len(euro), 'n_asian': len(asian), 'n_ou': len(ou),
            'max': mx, 'min': mn, 'fetched_at': data.get('fetched_at')}


def main():
    os.makedirs(DEST, exist_ok=True)
    names = [n for n in sorted(os.listdir(SRC)) if os.path.isdir(os.path.join(SRC, n))]
    man = []
    for n in names:
        r = build(n)
        if not r or r.get('err'):
            print('SKIP', n, (r or {}).get('err')); continue
        bs = n.replace(' ', '_')
        open(os.path.join(DEST, bs + '.txt'), 'w', encoding='utf-8').write(r['main'])
        open(os.path.join(DEST, bs + '_jc.txt'), 'w', encoding='utf-8').write(r['jc'])
        man.append({k: v for k, v in r.items() if k not in ('main', 'jc')})
        print('OK  %-46s %-4s handi=%-6s(%s) O2.5=%.3f λ=%.3f' % (n[:46], r['lg'], '%+.2f' % r['handi'], r['handi_txt'], r['o25'], r['lam']))
    json.dump(man, open(os.path.join(DEST, '_manifest.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('TOTAL', len(man))


if __name__ == '__main__':
    main()
