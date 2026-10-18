#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""digest_14.py — 从 calc_all 输出 + 服务端md 抽取结构化摘要（供报告消费·不重算）"""
import json, os, re, sys
sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEST = os.path.join(ROOT, 'data', 'tmp', 'batch_14')
OUT = os.path.join(DEST, 'out')
SRC = r'F:\ocr_python_data\football-research\data-2.5.9\_by_category\14场'
man = json.load(open(os.path.join(DEST, '_manifest.json'), encoding='utf-8'))


def grab(txt, pat, flags=0):
    m = re.search(pat, txt, flags)
    return m.group(0).strip() if m else None


def one(txt, pat, idx=1, flags=0):
    m = re.search(pat, txt, flags)
    return m.group(idx).strip() if m else None


def digest(name):
    bs = name.replace(' ', '_')
    p = os.path.join(OUT, bs + '.txt')
    t = open(p, encoding='utf-8').read()
    tp = os.path.join(OUT, bs + '.pin.txt')
    tp_txt = open(tp, encoding='utf-8').read() if os.path.exists(tp) else ''
    d = {'name': name}
    d['implied'] = one(t, r'隐含: ([^\n(]+)')
    d['calib'] = one(t, r'校准后主胜概率\(P0-1\): ([^\n]+)')
    d['gap'] = one(t, r'方向差距\(前两方向\): ([^\n]+)')
    d['skew'] = one(t, r'skew精确计算: ([^\n]+)')
    d['kelly'] = one(t, r'凯利指数\(单源[^)]*\): ([^\n]+)')
    d['vig'] = one(t, r'反抽水比 ([0-9.]+x)') 
    d['vigflag'] = '触发' if '触发反抽水' in t else '不触发'
    d['d1'] = re.findall(r'D1检测: ([^\n]+)', t)
    d['s53'] = one(t, r'修正53预计算: ([^\n]+)')
    d['v5'] = one(t, r'V5跨市场分歧: ([^\n]+)')
    d['netmargin'] = re.findall(r'\[netmargin[^\]]*\] ([^\n]+)', t)
    d['goalbins'] = one(t, r'\[goalbins\] ([^\n]+)')
    d['trap'] = one(t, r'\[trap\] ([^\n]+)')
    d['direction'] = one(t, r'方向\(欧亚综合\): ([^\n]+)')
    d['trapline'] = one(t, r'诱阻分类: ([^\n]+)')
    d['anomaly'] = one(t, r'    异常: ([^\n]+)')
    d['below'] = one(t, r'量级\(O25校准分布[^)]*\): ([^\n]+)')
    d['bigsmall'] = one(t, r'🔴大小球判向: \*\*([^*]+)\*\*')
    d['league'] = one(t, r'🔴联赛基准\(([^)]*)\): ([^\n]+)', 0)
    d['league_name'] = one(t, r'🔴联赛基准\(([^)]*)\)')
    d['leaguedist'] = one(t, r'本场主胜档 [^\n]+', 0)
    d['top5'] = one(t, r'联赛比分Top5: ([^\n]+)')
    d['haf'] = one(t, r'🔴HAF\(Step4\.6\): ([^\n]+)')
    d['elo'] = one(t, r'🔴ELO\(修正41\): ([^\n]+)')
    d['elo2'] = one(t, r'    → \|ELO差\|[^\n]+', 0)
    d['xg'] = one(t, r'🔴xG\([^)]*\): ([^\n]+)')
    d['cross'] = re.findall(r'🔴跨机构分歧\(修正35\): ([^\n]+)', t)
    d['cross2'] = re.findall(r'    → (?:Max分歧|偏离最大方向)[^\n]+', t)
    d['live'] = one(t, r'λ: ([^\n]+)')
    d['wei'] = one(t, r'动态权重: ([^\n]+)')
    d['topscores'] = one(t, r'Top5比分: ([^\n]+)')
    d['anchorsug'] = one(t, r'🔴主锚建议: ([^\n]+)')
    d['netexp'] = one(t, r'🔴市场净胜期望档: ([^\n]+)')
    d['anchorconflict'] = re.findall(r'  (?:❌|↳|⚠️|🔴 )[^\n]+', t)
    d['anchor_trust'] = one(t, r'🔴锚可信度[^:]*: ([^\n]+)')
    d['agg'] = one(t, r'聚合: ([^\n]+)')
    d['scores_ok'] = one(t, r'约束内候选\*\*参考\*\*[^:]*: ([^\n]+)')
    # pin baseline direction
    d['dir_pin'] = one(tp_txt, r'方向\(欧亚综合\): ([^\n]+)')
    d['implied_pin'] = one(tp_txt, r'隐含: ([^\n(]+)')
    d['skew_pin'] = one(tp_txt, r'skew精确计算: ([^\n]+)')
    d['netexp_pin'] = one(tp_txt, r'🔴市场净胜期望档: ([^\n]+)')
    d['anchorsug_pin'] = one(tp_txt, r'🔴主锚建议: ([^\n]+)')
    d['topscores_pin'] = one(tp_txt, r'Top5比分: ([^\n]+)')
    d['agg_pin'] = one(tp_txt, r'聚合: ([^\n]+)')
    d['trust_pin'] = one(tp_txt, r'🔴锚可信度[^:]*: ([^\n]+)')
    # source md tail facts
    md = os.path.join(SRC, name, '服务端数据.md')
    mt = open(md, encoding='utf-8').read()
    d['md'] = {}
    for k in ['统一基线', '必算六项', '体彩让球去水', '闸门', '把握度封顶', '主流线', '水位', '时间对齐',
              '符号自检', '大小球水位方向', '强制项', '澳门未跟盘', '澳门内部欧亚对照', '异常']:
        d['md'][k] = grab(mt, k + r'[^\n]*')
    return d


res = [digest(m['name']) for m in man]
json.dump(res, open(os.path.join(DEST, '_digest.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('dumped', len(res))
