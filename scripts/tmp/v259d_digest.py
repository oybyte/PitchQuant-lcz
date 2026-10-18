#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v259d_digest.py — 把 calc_all 双基线输出压缩成决策摘要（每场 ≤16 行）"""
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEST = os.path.join(ROOT, 'data', 'tmp', 'batch_v259d')
OUT = os.path.join(DEST, 'out')
man = json.load(open(os.path.join(DEST, '_manifest.json'), encoding='utf-8'))


def g1(pat, s, d=None, cast=str):
    m = re.search(pat, s)
    if not m:
        return d
    try:
        return cast(m.group(1))
    except Exception:
        return d


def parse(t):
    r = {}
    r['devig'] = re.search(r'隐含: 主([\d.]+)%/平([\d.]+)%/客([\d.]+)%', t)
    r['devig'] = tuple(map(float, r['devig'].groups())) if r['devig'] else None
    r['calib'] = g1(r'校准后主胜概率\(P0-1\): ([\d.]+)%', t, None, float)
    r['gap'] = g1(r'方向差距\(前两方向\): ([\d.]+)pt', t, None, float)
    m = re.search(r'skew精确计算: [\d.]+/[\d.]+ = ([\d.]+)% → (\S+?)\(', t)
    r['skew'] = (float(m.group(1)), m.group(2)) if m else None
    r['vig'] = g1(r'去抽水率: ([\d.]+)%', t, None, float)
    r['ratio'] = g1(r'反抽水比 ([\d.]+)x', t, None, float)
    m = re.search(r'变动: 初\([^)]*\) \{[^}]*\} → 末 \{[^}]*\}\n((?:\s{4}.+\n)+)', t)
    r['moves'] = ' | '.join(x.strip() for x in m.group(1).strip().split('\n')) if m else None
    r['d1'] = '; '.join(x.strip() for x in re.findall(r'🔴D1背离候选: [^\n]+', t))
    r['s53'] = g1(r'修正53预计算: ([^\n]+)', t)
    r['grp'] = g1(r"分组去相关\(P0-2\): \{[^}]*\} → 总分([\d.]+)", t, None, float)
    r['v5'] = g1(r'V5跨市场分歧: ([^\n·]+)', t)
    r['netm'] = g1(r'\[netmargin-handi\] ([^\n]+)', t)
    r['marg'] = g1(r'\[netmargin\] ([^\n]+)', t)
    r['gbins'] = g1(r'\[goalbins\] ([^\n]+)', t)
    r['trap'] = g1(r'\[trap\] ([^\n]+)', t)
    r['dir'] = g1(r'方向\(欧亚综合\): (\S+)\(([A-Z\-]+)\)', t)
    m = re.search(r'方向\(欧亚综合\): (\S+)\(([A-Z\-]+)\) \| 并列:(\S+) \| 诱盘:(\S+)', t)
    r['dirv'] = (m.group(1), m.group(2), m.group(3), m.group(4)) if m else None
    r['bin'] = g1(r'量级\(O25校准分布[^)]*\): O2\.5=[\d.]+档(\S+?) → ([^\n]+)', t)
    m = re.search(r'量级\(O25校准分布[^)]*\): O2\.5=[\d.]+档(\S+?) → ([^\n]+?)\n', t)
    r['bin'] = (m.group(1), m.group(2)) if m else None
    r['ball'] = g1(r'大小球判向: \*\*(\S+?)\*\*', t)
    r['lgbase'] = g1(r'联赛基准\(([^)]*)\): 大球率 ([\d.]+)% · 平局率 ([\d.]+)%', t)
    r['lgrow'] = g1(r'本场主胜档 \S+ → ([^\n]+)', t)
    r['haf'] = g1(r'HAF\(Step4\.6\): ([^\n]+)', t)
    r['elo'] = g1(r'ELO\(修正41\): ([^\n]+)', t)
    r['xg'] = g1(r'xG\(SK-xg-depth\): ([^\n]+)', t)
    r['xdiv'] = g1(r'跨机构分歧\(修正35\): ([^\n]+)', t)
    r['xdiv2'] = g1(r'→ Max分歧 ([^\n]+)', t)
    r['inj'] = 'missing(分析禁止联网)'
    r['lam'] = re.search(r'λ: 主([\d.]+) 客([\d.]+) 总([\d.]+)', t)
    r['lam'] = tuple(map(float, r['lam'].groups())) if r['lam'] else None
    r['top5'] = g1(r'Top5比分: ([^\n]+)', t)
    r['anch'] = g1(r'🔴主锚建议: (\S+) \| 次锚建议: (\S+?)\(', t)
    m = re.search(r'🔴主锚建议: (\S+) \| 次锚建议: (\S+?)\(', t)
    r['anch'] = (m.group(1), m.group(2)) if m else None
    r['netband'] = g1(r'市场净胜期望档: (\S+ \([^)]*\))', t)
    r['amc'] = g1(r'锚-市场一致性: ([^\n]+)', t)
    m = re.search(r'约束: ([^\n]+)', t)
    r['cons'] = m.group(1) if m else None
    r['viol'] = [x.strip() for x in re.findall(r'❌ ([^\n]+)', t)]
    r['sug'] = g1(r'约束内候选\*\*参考\*\*[^:]*: ([^\n]+)', t)
    r['trust'] = g1(r'锚可信度\([^)]*\): (\S+) — ([^\n]+)', t)
    m = re.search(r'锚可信度\([^)]*\): (\S+) — ([^\n]+)', t)
    r['trust'] = (m.group(1), m.group(2)) if m else None
    r['agg'] = re.search(r'聚合: 主([\d.]+)% 平([\d.]+)% 客([\d.]+)% \| O2\.5([\d.]+)% \| 置信(\S+)', t)
    r['agg'] = tuple(map(float, r['agg'].groups()[:4])) + (r['agg'].group(5),) if r['agg'] else None
    r['prior'] = g1(r'先验格: (\S+)', t)
    return r


rows = []
for m in man:
    base = m['name'].replace(' ', '_').replace('(', '').replace(')', '')
    t = open(os.path.join(OUT, base + '.txt'), encoding='utf-8').read()
    tp = open(os.path.join(OUT, base + '.pin.txt'), encoding='utf-8').read()
    a, b = parse(t), parse(tp)
    rows.append(dict(man=m, mac=a, pin=b))

json.dump(rows, open(os.path.join(DEST, '_digest.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

lines = []
for i, r in enumerate(rows, 1):
    m, a, b = r['man'], r['mac'], r['pin']
    lines.append('#%02d %s | %s | %s vs %s' % (i, m['mt'], m['lg'], m['home'], m['away']))
    lines.append('   基线 eu=%s (handi %+g · 亚盘 %s · 大小线 %s) → O2.5=%.3f U2.5=%.3f λ_total=%.3f' % (
        m['eu'], m['handi'], m.get('ah_line'), m.get('ou_line'), m['o25'], m['u25'], m['lam']))
    lines.append('   澳门隐含 %s | 校准后主 %.1f%% | gap %.1f | skew %s | 抽水 %.2f%% 反抽水 %.2fx' % (
        a['devig'], a['calib'] or -1, a['gap'] or -1, a['skew'], a['vig'] or -1, a['ratio'] or -1))
    lines.append('   变动 %s' % a['moves'])
    lines.append('   D1 %s | 修正53 %s | 分组分 %s | V5 %s' % (a['d1'] or '无', a['s53'], a['grp'], a['v5']))
    lines.append('   净胜档 %s' % a['netm'])
    lines.append('   候选池 %s' % a['marg'])
    lines.append('   量级 %s | 判向 %s' % (a['bin'], a['ball']))
    lines.append('   诱阻 %s | 方向 %s | 并列 %s | 诱盘 %s' % (a['trap'], a['dirv'][0] if a['dirv'] else '?',
             a['dirv'][2] if a['dirv'] else '?', a['dirv'][3] if a['dirv'] else '?'))
    lines.append('   泊松 λ=%s | Top5 %s | 脚本锚 %s' % (a['lam'], a['top5'], a['anch']))
    lines.append('   市场净胜档 %s | 约束 %s' % (a['netband'], a['cons']))
    lines.append('   锚违规 %s | 建议 %s | 锚可信度 %s' % (a['viol'], a['sug'], a['trust']))
    lines.append('   聚合 %s | 先验 %s' % (a['agg'], a['prior']))
    lines.append('   联赛基准 %s %s' % (a['lgbase'], a['lgrow']))
    lines.append('   HAF %s' % a['haf'])
    lines.append('   ELO %s' % a['elo'])
    lines.append('   xG %s' % a['xg'])
    lines.append('   跨机构 %s / %s' % (a['xdiv'], a['xdiv2']))
    if b:
        lines.append('   [PIN] 隐含 %s | gap %s | skew %s | 方向 %s | 聚合 %s' % (
            b['devig'], b['gap'], b['skew'], b['dirv'][0] if b['dirv'] else '?', b['agg']))
    lines.append('')

open(os.path.join(DEST, '_digest.txt'), 'w', encoding='utf-8').write('\n'.join(lines))
print('\n'.join(lines[:40]))
print('...TOTAL LINES', len(lines))
