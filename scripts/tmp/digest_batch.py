#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""digest_batch.py — 从 calc_all 输出抽取结构化摘要（通用版·替代硬编码 batch_14 的 digest_14.py）

不重算任何数值：只做正则抽取。供报告/SQL 消费。

用法:
    python scripts/tmp/digest_batch.py --dest data/tmp/batch_v259W
产物: <dest>/_digest.json  +  stdout 一行动一行的紧凑表
"""
import argparse
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PATS = {
    'implied': r'隐含: ([^\n(]+)',
    'calib': r'校准后热门方向\(\S+\)概率: ([^\n]+)',
    'gap': r'方向差距\(前两方向\): ([^\n]+)',
    'skew': r'skew精确计算.*?: ([^\n]+)',
    'kelly': r'凯利指数\(单源[^)]*\): ([^\n]+)',
    'vig': r'反抽水比 ([0-9.]+x)',
    'netmargin': r'\[netmargin[^\]]*\] ([^\n]+)',
    'goalbins': r'\[goalbins\] ([^\n]+)',
    'trap': r'\[trap\] ([^\n]+)',
    'direction': r'方向\(欧亚综合\): ([^\n]+)',
    'tiedan': r'铁胆档: ([^\n]+)',
    'bigsmall': r'🔴大小球判向: \*\*([^*]+)\*\*',
    'league': r'🔴联赛基准\(([^)]*)\): ([^\n]+)',
    'leaguedist': r'本场主胜档 [^\n]+',
    'top5': r'联赛比分Top5: ([^\n]+)',
    'haf': r'🔴HAF\(Step4\.6\): ([^\n]+)',
    'elo': r'🔴ELO\(修正41\): ([^\n]+)',
    'elo2': r'    → \|ELO差\|[^\n]+',
    'xg': r'🔴xG\([^)]*\): ([^\n]+)',
    'cross': r'🔴跨机构分歧\(修正35\): ([^\n]+)',
    'injury': r'🔴伤停影响分[^\n]*',
    'live_lam': r'  λ: ([^\n]+)',
    'live_w': r'动态权重: ([^\n]+)',
    'live_top5': r'Top5比分: ([^\n]+)',
    'anchor_main': r'🔴主锚建议: ([^\n]+)',
    'netexp': r'🔴市场净胜期望档: ([^\n]+)',
    'anchor_trust': r'🔴锚可信度[^:]*: ([^\n]+)',
    'agg': r'聚合: ([^\n]+)',
    'prior': r'先验格: ([^\n]+)',
}


def one(txt, pat, idx=1):
    m = re.search(pat, txt)
    if not m:
        return None
    try:
        return m.group(idx).strip()
    except IndexError:
        return m.group(0).strip()


def digest(base, dest):
    p = os.path.join(dest, 'out', base + '.txt')
    t = open(p, encoding='utf-8').read() if os.path.exists(p) else ''
    pp = os.path.join(dest, 'out', base + '.pin.txt')
    tp = open(pp, encoding='utf-8').read() if os.path.exists(pp) else ''
    d = {'name': base}
    for k, pat in PATS.items():
        d[k] = one(t, pat)
    # 锚-市场一致性：抓整段（含 ❌ 行）
    m = re.search(r'🔴锚-市场一致性: ([^\n]+)((?:\n      [^\n]+)*)', t)
    d['anchor_market'] = (m.group(1) + m.group(2)) if m else None
    d['anchor_market_marks'] = re.findall(r'(?:❌|↳|⚠️) [^\n]+', t)
    d['suggestion'] = one(t, r'约束内候选\*\*参考\*\*[^:]*: ([^\n]+)')
    d['trap_anomaly'] = one(t, r'    异常: ([^\n]+)')
    d['induce'] = one(t, r'诱盘:\[([^\]]*)\]')
    d['hints'] = one(t, r'提示:\[([^\]]*)\]')
    d['s53'] = one(t, r'修正53预计算: ([^\n]+)')
    d['d1'] = re.findall(r'D1检测: ([^\n]+)', t)
    d['v5'] = one(t, r'V5跨市场分歧: ([^\n]+)')
    d['consensus_in'] = one(t, r'\[输入\] 🔴多机构合并去水[^\n]*')
    d['fresh'] = one(t, r'🔴时点新鲜度：[^\n]+')
    # pin 基线
    d['dir_pin'] = one(tp, r'方向\(欧亚综合\): ([^\n]+)')
    d['agg_pin'] = one(tp, r'聚合: ([^\n]+)')
    d['anchor_pin'] = one(tp, r'🔴主锚建议: ([^\n]+)')
    d['netexp_pin'] = one(tp, r'🔴市场净胜期望档: ([^\n]+)')
    d['implied_pin'] = one(tp, r'隐含: ([^\n(]+)')
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dest', required=True)
    a = ap.parse_args()
    dest = a.dest if os.path.isabs(a.dest) else os.path.join(ROOT, a.dest)
    man = json.load(open(os.path.join(dest, '_manifest.json'), encoding='utf-8'))
    res = []
    for m in man:
        base = m['name'].replace(' ', '_')
        d = digest(base, dest)
        d['lg'] = m['lg']
        d['home'], d['away'], d['mt'] = m['home'], m['away'], m['mt']
        d['eu'], d['eu_pin'] = m['eu'], m.get('eu_pin')
        d['handi'], d['jch'] = m['handi'], m.get('jch')
        d['o25'], d['u25'], d['lam'] = m['o25'], m['u25'], m['lam']
        d['ou_line'], d['ah_line'], d['water'] = m.get('ou_line'), m.get('ah_line'), m.get('water')
        d['band'], d['minutes'] = m.get('band'), m.get('minutes_before_ko')
        d['n_euro'] = m.get('n_euro')
        res.append(d)
    json.dump(res, open(os.path.join(dest, '_digest.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('dumped', len(res), '→', os.path.join(dest, '_digest.json'))


if __name__ == '__main__':
    main()
