# -*- coding: utf-8 -*-
import json, os, re, sys
sys.stdout.reconfigure(encoding='utf-8')
D = r'E:\footbal-github\PitchQuant\data\tmp\batch_14'
man = json.load(open(os.path.join(D, '_manifest.json'), encoding='utf-8'))
print('%-30s %-10s %-12s %-10s %-22s %s' % ('match', 'price', 'agg', 'gap', '裁决', '聚合分布'))
for m in man:
    bs = m['name'].replace(' ', '_')
    t = open(os.path.join(D, 'out', bs + '.txt'), encoding='utf-8').read()
    pr = re.search(r'价格引擎\(direction_full\): (\S+)  ↔  多源聚合: (\S+)\(([\d.]+)%\)', t)
    g = re.search(r'首两向 gap ([\d.]+)pt', t)
    dec = re.search(r'→ (.+)', t.split('多源聚合裁决')[1]) if '多源聚合裁决' in t else None
    ag = re.search(r'聚合: 主([\d.]+)% 平([\d.]+)% 客([\d.]+)%', t)
    print('%-30s %-10s %-12s %-10s %-24s %s' % (
        m['name'][:30], pr.group(1) if pr else '-', (pr.group(2) + '(' + pr.group(3) + '%)') if pr else '-',
        g.group(1) + 'pt' if g else '-', (dec.group(1)[:24] if dec else '-'),
        ('%s/%s/%s' % ag.groups()) if ag else '-'))
