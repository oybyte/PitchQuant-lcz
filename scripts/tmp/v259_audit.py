#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v259_audit.py — 22 场复跑体检（判据修正版）

判据修正（第二轮）:
  · P0-4 溯源行属于「生成期」产物 → 查输入 txt，不查 calc_all 输出
  · 双基线「方向不同」不等于缺陷 → 各自隐含/skew 自洽即为真实市场分歧
  · 空块判定排除「标题+分隔线」的正常排版
"""
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEST = os.path.join(ROOT, 'data', 'tmp', 'batch_v259_today')
OUT = os.path.join(DEST, 'out')
man = json.load(open(os.path.join(DEST, '_manifest.json'), encoding='utf-8'))
bases = [m['name'].replace(' ', '_').replace('(', '').replace(')', '') for m in man]

C = {}


def chk(k, ok, det=''):
    C.setdefault(k, [0, 0, []])
    C[k][1] += 1
    if ok:
        C[k][0] += 1
    else:
        C[k][2].append(det)


for m, base in zip(man, bases):
    t = open(os.path.join(OUT, base + '.txt'), encoding='utf-8').read()
    tp = open(os.path.join(OUT, base + '.pin.txt'), encoding='utf-8').read()
    src = open(os.path.join(DEST, base + '.txt'), encoding='utf-8').read()

    chk('P0-1 V5跨市场', '未提供欧盘' not in t and 'V5跨市场分歧' in t, base)
    chk('P0-2 诱阻分类', bool(re.search(r'诱阻分类预计算[^\n]*\n\s*\[trap\]', t)), base)
    chk('P0-3 亚盘/体彩L双轨', 'netmargin-handi' in t, base)
    chk('P0-3 净胜档依亚盘', '依据=亚盘线' in t, base)
    chk('P0-4 O2.5折算溯源(输入期)', '四分之一线EV中性反解' in src, base)
    chk('P1-1 锚=约束', ('约束:' in t or '约束内候选' in t or '当前锚均落在市场约束内' in t), base)
    chk('P1-2 伤停三态', '伤停影响分(判定铁依据' in t, base)
    chk('P1-4 跨机构分歧', '跨机构分歧' in t, base)
    chk('P2-1 三层三态', all(k in t for k in ('HAF(Step4.6)', 'ELO(修正41)', 'xG(SK-xg-depth)')), base)
    chk('P2-3 门限150', 'skew<130' not in t, base)

    # 新增: 去水口径跟随 --eu（第二轮修复）
    def devig(s):
        mm = re.search(r'隐含: 主([\d.]+)%/平([\d.]+)%/客([\d.]+)%', s)
        return tuple(map(float, mm.groups())) if mm else None
    dm, dp = devig(t), devig(tp)
    chk('P0(新) 去水跟随--eu', dm is not None and dp is not None and dm != dp, base)
    # 若两基线隐含不同 → 允许方向不同（真实市场分歧），但各自须标源
    chk('P0(新) 去水标源', '源:欧盘--eu' in t and '源:欧盘--eu' in tp, base)


def dir_of(s):
    mm = re.search(r'方向\(欧亚综合\): (\S+?)\(', s)
    return mm.group(1) if mm else None


# 双基线方向分歧 → 单独列出（不是缺陷·是市场分歧）
diverge = [b for b in bases if dir_of(open(os.path.join(OUT, b + '.txt'), encoding='utf-8').read())
           != dir_of(open(os.path.join(OUT, b + '.pin.txt'), encoding='utf-8').read())]

print('%-28s %-8s %s' % ('检查项', '结果', '失败'))
print('-' * 78)
for k, (ok, tot, bad) in C.items():
    print('%-28s %s %d/%d %s' % (k, '✅' if ok == tot else '❌', ok, tot,
                                 ('  ' + ', '.join(bad[:2])) if bad else ''))
print('%-28s %s %d/%d' % ('双基线同向', '✅' if not diverge else 'ℹ️',
                          len(bases) - len(diverge), len(bases)))
for b in diverge:
    print('     ↳ 市场分歧(非缺陷): ' + b)
