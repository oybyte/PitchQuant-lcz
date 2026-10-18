# -*- coding: utf-8 -*-
"""facts_14.py — 每场消费查表值（odds_table / team_profiles / league_table）·禁手算"""
import json, os, sys
sys.stdout.reconfigure(encoding='utf-8')
R = r'E:\footbal-github\PitchQuant\data\tmp'
D = os.path.join(R, 'batch_14')
man = json.load(open(os.path.join(D, '_manifest.json'), encoding='utf-8'))
dg = {m['name']: m for m in json.load(open(os.path.join(D, '_digest.json'), encoding='utf-8'))}
ot = json.load(open(os.path.join(R, 'odds_table.json'), encoding='utf-8'))
tp = json.load(open(os.path.join(R, 'team_profiles.json'), encoding='utf-8'))
EN = {}
for t in json.load(open(r'E:\footbal-github\PitchQuant\data\team_name_mapping_2025-26.json', encoding='utf-8'))['teams']:
    if t.get('cn') and t.get('en'):
        EN[t['cn']] = t['en']
ALIAS = {'RB莱比锡': ['RB Leipzig', 'Leipzig'], '曼彻斯特城': ['Man City'], '拜仁慕尼黑': ['Bayern Munich'],
         '纽卡斯尔联': ['Newcastle'], '皇家贝蒂斯': ['Betis'], '毕尔巴鄂竞技': ['Ath Bilbao'],
         '国际米兰': ['Inter'], '沙尔克04': ['Schalke 04'], '汉堡': ['Hamburg', 'Hamburger SV'],
         '巴伦西亚': ['Valencia'], '阿斯顿维拉': ['Aston Villa']}


def band_for(oh):
    b = [('<1.30', 1.30), ('1.30-1.50', 1.50), ('1.50-1.80', 1.80), ('1.80-2.10', 2.10),
         ('2.10-2.50', 2.50), ('2.50-3.00', 3.00), ('3.00+', 99)]
    for name, hi in b:
        if oh < hi:
            return name
    return '3.00+'


def prof(cn):
    for nm in ([EN.get(cn)] if EN.get(cn) else []) + ALIAS.get(cn, []):
        if nm and nm in tp:
            return nm, tp[nm]
    return None, None


print('%-34s %-6s %-12s %-28s %s' % ('match', 'lg', 'band', 'odds_table(H/D/A/O25/net1-2-3)', 'implied-diff'))
for m in man:
    name = m['name']
    oh = float(m['eu'].split(',')[0])
    bd = band_for(oh)
    key = '%s|%s' % (m['lg'], {'<1.30': '<1.30超深盘'}.get(bd, ''))
    # match actual key
    hit = [k for k in ot if k.startswith(m['lg'] + '|') and bd in k]
    row = ot[hit[0]] if hit else {}
    d = dg[name]
    imp = d['implied'].replace('%', '').replace('主', '').replace('平', '').replace('客', '').split('/')
    try:
        diff = abs(float(imp[0]) - float(imp[2]))
    except Exception:
        diff = None
    print('%-34s %-6s %-12s H%s/D%s/A%s O25:%s n1%s n2%s n3%s n=%s | %.1fpp'
          % (name[:34], m['lg'], bd, row.get('H'), row.get('D'), row.get('A'), row.get('O25'),
             row.get('net1'), row.get('net2'), row.get('net3'), row.get('n'), diff if diff is not None else -1))
    for cn in (m['home'], m['away']):
        nm, p = prof(cn)
        if p:
            print('        %-10s(%s) n=%s 主胜%s 客胜%s 平局%s 大球%s 赢1球%s 大胜3+%s'
                  % (cn, nm, p.get('n'), p.get('主胜'), p.get('客胜'), p.get('平局'),
                     p.get('大球率'), p.get('赢1球'), p.get('大胜3+')))
        else:
            print('        %-10s 无 team_profiles 档案' % cn)
