#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v259d_convert.py — data-2.5.9/_by_category/单场 → 标准竞彩 txt（可复现转换器·D 批）

与 v259_convert.py（output/ 目录版）的差异:
  · 源目录改为 _by_category/单场（26 场·含赛前最新快照·抓取 17:30）
  · 统一取 **live（即盘）** 作当前定价 → 与 calc_all 的「动态铁律」一致
  · 输出到 data/tmp/batch_v259d/，文件名 = 目录名（空格→下划线）

口径（与项目 SKILL/AGENTS 一致·不改模型）:
  · --eu   = 澳门胜平负即盘（唯一带逐点时序的机构通道基线）；Pinnacle 即盘作交叉校验基线
  · handi  = -(亚盘 live_line_value)   负=主让 / 正=主受让
  · o25/u25= ou_from_asia.convert(主流线, 大球水, 小球水)  ← 唯一真源·禁手工推导
  · 跨机构 = 全 N 家 euro 的 最高价/最低价（供修正35 自动解析·禁单家冒充）
  · 体彩让球 L 仅用于让球盘去水；缺失时整段不写（下游三态），不伪造 +0
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

SRC = r'F:\ocr_python_data\football-research\data-2.5.9\_by_category\单场'
DEST = os.path.join(ROOT, 'data', 'tmp', 'batch_v259d')


def _f(x, d=None):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def _find(rows, pred):
    return next((r for r in rows if pred(r)), None)


def _used_portfolio_log(md_text):
    """已填赛果 → 标出（不排除，由使用者决定；本批 26 场全部未填写）"""
    return '未填写赛果' not in md_text


def build(name):
    d = os.path.join(SRC, name)
    js = os.path.join(d, '服务端数据.json')
    if not os.path.exists(js):
        return {'name': name, 'err': 'missing json'}
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
    mac_eu = _find(euro, lambda r: (r.get('company_en') or '') == 'Macauslot')
    base_eu = mac_eu or pin
    if not (mac_as and mac_ou and base_eu):
        return {'name': name, 'err': 'missing macao/pinnacle rows'}

    # ── live（即盘）= 当前定价 ──
    a_live = (_f(mac_as['live_home']), _f(mac_as['live_line_value']), _f(mac_as['live_away']))
    a_init = (_f(mac_as['init_home']), _f(mac_as['init_line_value']), _f(mac_as['init_away']))
    o_live = (_f(mac_ou['live_home']), _f(mac_ou['live_line_value']), _f(mac_ou['live_away']))
    o_init = (_f(mac_ou['init_home']), _f(mac_ou['init_line_value']), _f(mac_ou['init_away']))
    o_line_txt = mac_ou.get('live_line') or ''
    a_line_txt = mac_as.get('live_line') or ''

    me_init = (_f(base_eu.get('init_home')), _f(base_eu.get('init_draw')), _f(base_eu.get('init_away')))
    me_live = (_f(base_eu.get('live_home')), _f(base_eu.get('live_draw')), _f(base_eu.get('live_away')))
    base_tag = '澳门' if mac_eu else 'Pinnacle(澳门缺失)'
    pi_live = None
    if pin:
        pi_live = (_f(pin.get('live_home')), _f(pin.get('live_draw')), _f(pin.get('live_away')))

    if None in o_live or o_live[0] is None:
        return {'name': name, 'err': 'OU live row incomplete'}
    conv = OA.convert(o_live[1], o_live[0], o_live[2])
    if not conv.get('supported'):
        return {'name': name, 'err': 'O2.5 折算失败(line=%s)' % o_live[1]}

    # ── 跨机构（全样本·禁单家冒充） ──
    valid = [r for r in euro if _f(r.get('live_home'), 0) and _f(r.get('live_draw'), 0) and _f(r.get('live_away'), 0)]
    mx = (max(_f(r['live_home']) for r in valid),
          max(_f(r['live_draw']) for r in valid),
          max(_f(r['live_away']) for r in valid))
    mn = (min(_f(r['live_home']) for r in valid),
          min(_f(r['live_draw']) for r in valid),
          min(_f(r['live_away']) for r in valid))

    handi = -(a_live[1] if a_live[1] is not None else 0.0)
    jcL = _f(data.get('sport_lottery_handicap'), None)
    jc_ml = _find(euro, lambda r: (r.get('company') or '') == '体彩官方')
    jc_rq = _find(euro, lambda r: '让' in (r.get('company') or ''))
    ser = data.get('sport_lottery_serial') or ''
    jch_s = ('%+g' % jcL) if jcL is not None else '—'

    head = '赛事：%s-%s %s %s(主) VS %s(客)\n' % (ser or 'x', det.get('match_id'), lg, home, away)
    head += '比赛时间：%s 2026/2027赛季\n' % mt
    head += '球探ID：%s  体彩期号：%s  体彩主队让球：%s\n' % (det.get('match_id'), ser, jch_s)

    body = '数据来源：football-research data-2.5.9 服务端快照(titan007·_by_category/单场)·抓取 %s\n\n' % data.get('fetched_at', '')
    body += '亚盘(澳门 主水/盘口/客水)：初 %s / %s / %s → 即 %s / %s / %s\n' % (
        a_init[0], mac_as.get('init_line'), a_init[2], a_live[0], a_line_txt, a_live[2])
    body += '大小球(澳门 大球水/盘口/小球水)：初 %s / %s / %s → 即 %s / %s / %s\n' % (
        o_init[0], mac_ou.get('init_line'), o_init[2], o_live[0], o_line_txt, o_live[2])
    body += '🔴机构通道统一基线 = %s胜平负即盘：%g / %g / %g (初盘 %g / %g / %g)\n' % (
        base_tag, me_live[0], me_live[1], me_live[2], me_init[0], me_init[1], me_init[2])
    if pi_live:
        body += '欧赔(Pinnacle 即盘·交叉校验源)：%g / %g / %g\n' % pi_live
    body += '跨机构即盘：%d 家 · 最高价 %g/%g/%g · 最低价 %g/%g/%g\n' % (
        (len(valid),) + mx + mn)
    body += '市场期望总进球：澳门即盘 %s 线(大%s/小%s) 四分之一线EV中性反解 → λ_total=%.3f → 2.5档 P(over)=%.4f → O2.5=%.2f / U2.5=%.2f\n' % (
        o_line_txt or o_live[1], o_live[0], o_live[2], conv['lambda'], conv['p25_over'], conv['o25'], conv['u25'])
    if jc_ml:
        body += '竞彩官方胜平负即盘：%s / %s / %s\n' % (jc_ml.get('live_home'), jc_ml.get('live_draw'), jc_ml.get('live_away'))
    else:
        body += '🔴竞彩官方胜平负：missing(本场快照未含「体彩官方」行·让球盘仍可用)\n'
    body += '🔴服务端未提供：半全场盘、竞彩总进球盘、比分盘(CS)、凯利逐家时序\n\n'

    # 澳门胜平负逐点时序（机构通道·源文件倒序 → 升序）
    mac_eu_tl = []
    for r in reversed(etl):
        m = re.match(r'(\d+)-(\d+)\s+(\d+):(\d+)', r.get('time') or '')
        if m:
            mac_eu_tl.append('2026-%02d-%02d %s:%s:00,%s,%s,%s' % (
                int(m.group(1)), int(m.group(2)), m.group(3), m.group(4),
                r.get('home'), r.get('line'), r.get('away')))

    # 澳门亚盘/大小球逐点时序（水位轨迹·V3/V6 消费）
    def _tl(rows, label):
        out = []
        for r in reversed(rows):
            m = re.match(r'(\d+)-(\d+)\s+(\d+):(\d+)', r.get('time') or '')
            if m:
                out.append('2026-%02d-%02d %s:%s:00 %s %s / %s / %s' % (
                    int(m.group(1)), int(m.group(2)), m.group(3), m.group(4), label,
                    r.get('home'), r.get('line_ocr') or r.get('line'), r.get('away')))
        return out

    body += '【特征分析】\n本文件时序通道=澳门胜平负 %d 点(机构通道)\n' % len(mac_eu_tl)
    body += '澳门亚盘时序(%d 点)：\n' % len(det.get('asian_timeline') or [])
    body += '\n'.join(_tl(det.get('asian_timeline') or [], '亚盘')) + '\n'
    body += '澳门大小球时序(%d 点)：\n' % len(det.get('ou_timeline') or [])
    body += '\n'.join(_tl(det.get('ou_timeline') or [], '大小')) + '\n'

    body += '\n【胜平负固定奖金】\n发布时间,胜,平,负\n' + '\n'.join(mac_eu_tl) + '\n'
    if jcL is not None and jc_rq:
        ts = (data.get('fetched_at') or '2026-10-17 12:00:00')
        body += '\n【让球胜平负固定奖金｜让球%+g】\n发布时间,胜,平,负\n' % jcL
        body += '%s,%s,%s,%s\n' % (ts, jc_rq.get('live_home'), jc_rq.get('live_draw'), jc_rq.get('live_away'))
    elif jcL is not None:
        body += '\n🔴让球盘：missing(快照未含「体彩官方让球」行·体彩L=%+g 仍可用于亚盘对照)\n' % jcL
    body += '\n【半全场胜平负固定奖金】\n发布时间,胜胜,胜平,胜负,平胜,平平,平负,负胜,负平,负负\n'
    body += '\n【总进球固定奖金】\n发布时间,0球,1球,2球,3球,4球,5球,6球,7+球\n'
    body += '\n【比分固定奖金】\n发布时间,1:0,2:0,2:1,3:0,3:1,3:2,4:0,4:1,4:2,胜其它,0:0,1:1,2:2,3:3,平其它,0:1,0:2,1:2,0:3,1:3,2:3,0:4,1:4,负其它\n'

    return {'name': name, 'lg': lg, 'home': home, 'away': away, 'mt': mt, 'main': head + '\n' + body,
            'eu': '%.2f,%.2f,%.2f' % me_live,
            'eu_pin': ('%.2f,%.2f,%.2f' % pi_live) if pi_live else None,
            'handi': handi, 'jch': jcL, 'base': base_tag,
            'o25': conv['o25'], 'u25': conv['u25'], 'lam': conv['lambda'],
            'water': (a_live[0] + 1.0) if a_live[0] is not None else None,
            'ou_line': o_line_txt or o_live[1], 'ah_line': a_line_txt,
            'n_euro': len(valid), 'n_asian': len(asian), 'n_ou': len(ou),
            'jc_ml': bool(jc_ml), 'jc_rq': bool(jc_rq)}


def main():
    os.makedirs(DEST, exist_ok=True)
    names = [n for n in sorted(os.listdir(SRC))
             if os.path.isdir(os.path.join(SRC, n)) and not n.startswith('_')]
    man = []
    for n in names:
        md = os.path.join(SRC, n, '服务端数据.md')
        if not os.path.exists(md):
            print('SKIP(no md)', n); continue
        r = build(n)
        if not r or r.get('err'):
            print('SKIP', n, (r or {}).get('err')); continue
        base = n.replace(' ', '_').replace('(', '').replace(')', '')
        open(os.path.join(DEST, base + '.txt'), 'w', encoding='utf-8').write(r['main'])
        man.append({k: v for k, v in r.items() if k != 'main'})
        print('OK  %-42s %-6s handi=%+.2f O2.5=%.3f λ=%.3f n=%d jcML=%d jcRQ=%d 已填赛果=%d' % (
            n[:42], r['lg'], r['handi'], r['o25'], r['lam'], r['n_euro'],
            r['jc_ml'], r['jc_rq'], _used_portfolio_log(open(md, encoding='utf-8').read())))
    json.dump(man, open(os.path.join(DEST, '_manifest.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('TOTAL', len(man))


if __name__ == '__main__':
    main()
