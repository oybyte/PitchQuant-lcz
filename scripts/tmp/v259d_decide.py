#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v259d_decide.py — 判定辅助表（不替模型判定·只把脚本事实排成一行一场）"""
import json, os, re, sys
sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEST = os.path.join(ROOT, 'data', 'tmp', 'batch_v259d')
OUT = os.path.join(DEST, 'out')
man = json.load(open(os.path.join(DEST, '_manifest.json'), encoding='utf-8'))
LINES = {1.5:1.5,1.75:1.75,2.0:2.0,2.25:2.25,2.5:2.5,2.75:2.75,3.0:3.0,3.25:3.25,3.5:3.5,3.75:3.75,4.0:4.0,4.25:4.25,4.5:4.5,4.75:4.75,5.0:5.0,5.25:5.25}

def rd(t, base):
    p = os.path.join(OUT, base + ('.pin' if t else '') + '.txt')
    return open(p, encoding='utf-8').read()

print('%-3s %-30s %-6s %-6s %-5s %-5s %-4s %-5s %-6s %-4s %s' % (
    '#','对阵','方向','置信','并列','诱盘','双源','O2.5','判向','主流线','聚合(主/平/客|O25|tag)'))
print('-'*150)
rows=[]
for i, m in enumerate(man, 1):
    base = m['name'].replace(' ','_').replace('(','').replace(')','')
    t, tp = rd(False, base), rd(True, base)
    dm = re.search(r'方向\(欧亚综合\): (\S+?)\(([A-Z\-]+)\) \| 并列:(\S+) \| 诱盘:(\S+)', t)
    dp = re.search(r'方向\(欧亚综合\): (\S+?)\(([A-Z\-]+)\)', tp)
    agg = re.search(r'聚合: 主([\d.]+)% 平([\d.]+)% 客([\d.]+)% \| O2\.5([\d.]+)% \| 置信(\S+)', t)
    ball = re.search(r'大小球判向: \*\*(\S+?)\*\*', t)
    agree = '✅' if (dm and dp and dm.group(1) == dp.group(1)) else '🔴'
    rows.append(dict(i=i, name=m['name'], dir=dm.group(1), conf=dm.group(2), tie=dm.group(3),
                     trap=dm.group(4), agree=agree, o25=m['o25'], u25=m['u25'], line=m['ou_line'],
                     handi=m['handi'], lg=m['lg'], mt=m['mt'],
                     agg=(float(agg.group(1)),float(agg.group(2)),float(agg.group(3)),float(agg.group(4)),agg.group(5)) if agg else None,
                     ball=ball.group(1) if ball else '?'))
    print('%-3d %-30s %-6s %-6s %-5s %-5s %-4s %-6.3f %-6s %-6s %s' % (
        i, m['name'][:30], dm.group(1), dm.group(2), dm.group(3), dm.group(4), agree,
        m['o25'], ball.group(1) if ball else '?', m['ou_line'],
        ('%.0f/%.0f/%.0f|%.0f|%s' % rows[-1]['agg'][:5]) if agg else '?'))
json.dump(rows, open(os.path.join(DEST,'_decide.json'),'w',encoding='utf-8'), ensure_ascii=False, indent=1)
print()
print('方向分布:', {k: sum(1 for r in rows if r['dir']==k) for k in ('主胜','平局','客胜')})
print('置信分布:', {k: sum(1 for r in rows if r['conf']==k) for k in ('HIGH','MID','MID-LOW','LOW')})
print('双源不一致:', [r['name'] for r in rows if r['agree']=='🔴'])
print('大球/中性:', sum(1 for r in rows if r['ball']=='大球'), '/', sum(1 for r in rows if r['ball']!='大球'))
