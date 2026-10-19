#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""opening_test.py — 澳门「真·初盘」单点信息量检验（符号已修正）

🔴 符号约定
   本模块 a_line_* = 澳门原始盘口（正=主让/主强，负=主受让）
   与项目 handi 相反（handi = -line）。下方所有「让球深浅」判断都按原始盘口写。

对照
   A 初盘单点（欧赔热门 / 亚盘 / 大小球 / 水位 / 跨机构分歧）
   B 终盘单点（同一批场的抓取即盘）
   C 初盘 → 终盘 的变动（信息是否在变动里）
"""
import json
import math
import os
import sys

import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import opening_features as OF      # noqa: E402

OUT = os.path.join(OF.ROOT, 'data', 'tmp', 'opening_test.json')


def wilson(k, n, z=1.96):
    if n == 0:
        return (0., 0.)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - r) / d, (c + r) / d)


def rates(y, m):
    return ((y[m] == 0).mean() * 100, (y[m] == 1).mean() * 100, (y[m] == 2).mean() * 100)


def show(nm, y, m, extra=''):
    h, d, a = rates(y, m)
    print('  %-30s n=%-4d 主 %5.1f%% / 平 %5.1f%% / 客 %5.1f%% %s' % (nm, int(m.sum()), h, d, a, extra))


def main():
    S = OF.collect()
    n = len(S)
    y = np.array([x['label'] for x in S])
    F = [x['F'] for x in S]
    def a(k):
        return np.array([f.get(k, np.nan) for f in F])

    print('样本 %d（100%% 真·初盘）\n' % n)
    base = {c: float((y == c).mean()) * 100 for c in (0, 1, 2)}
    print('基线：主 %.1f%% / 平 %.1f%% / 客 %.1f%%\n' % (base[0], base[1], base[2]))

    oh, od, oa = a('o_h'), a('o_d'), a('o_a')
    lh, ld, la = a('l_h'), a('l_d'), a('l_a')
    eod = a('e_od')

    # ── 1. 热门命中：初盘 vs 终盘 ──
    print('=== 1. 押热门：初盘 vs 终盘 ===')
    for nm, h, d, aa in (('初盘', oh, od, oa), ('终盘', lh, ld, la)):
        fav = np.argmax(np.column_stack([h, d, aa]), axis=1)
        k = int((fav == y).sum())
        lo, hi = wilson(k, n)
        print('  %s热门  命中 %5.1f%% [CI %.1f–%.1f]  隐含均值 %.1f%%  边际 %+.1fpp' % (
            nm, k / n * 100, lo * 100, hi * 100,
            np.nanmean(np.column_stack([h, d, aa]).max(axis=1)),
            k / n * 100 - np.nanmean(np.column_stack([h, d, aa]).max(axis=1))))

    # ── 2. 初盘概率校准（分档）──
    print('\n=== 2. 初盘热门概率分档（校准）===')
    maxp = np.max(np.column_stack([oh, od, oa]), axis=1) / 100
    fav_o = np.argmax(np.column_stack([oh, od, oa]), axis=1)
    for lo_, hi_ in ((0, .38), (.38, .45), (.45, .55), (.55, .70), (.70, 1.01)):
        m = (maxp >= lo_) & (maxp < hi_)
        if m.sum() < 12:
            continue
        print('  P∈[%.2f,%.2f) n=%-3d 实际 %5.1f%%  初盘隐含 %5.1f%%  残差 %+.1fpp' % (
            lo_, hi_, int(m.sum()), (fav_o[m] == y[m]).mean() * 100,
            maxp[m].mean() * 100,
            (fav_o[m] == y[m]).mean() * 100 - maxp[m].mean() * 100))

    # ── 3. 平赔分档 → 实际平局率（用原始赔率）──
    print('\n=== 3. 初盘平赔原始赔率分档 → 实际平局率 ===')
    for lo_, hi_ in ((0, 3.0), (3.0, 3.3), (3.3, 3.6), (3.6, 4.2), (4.2, 99)):
        m = (eod >= lo_) & (eod < hi_)
        if m.sum() < 10:
            continue
        print('  平赔∈[%.1f,%.1f) n=%-3d 实际平局 %5.1f%%  隐含 %5.1f%%  残差 %+.1fpp' % (
            lo_, hi_, int(m.sum()), (y[m] == 1).mean() * 100,
            np.nanmean(100 / eod[m]), (y[m] == 1).mean() * 100 - np.nanmean(100 / eod[m])))

    # ── 4. 亚盘初盘 = 主队让球或受让（原始符号：正=主让）──
    print('\n=== 4. 初盘亚盘盘口（正=主让/主强）→ 主胜率 ===')
    al = a('a_line_o')
    for lo_, hi_, nm in ((-9, -0.7, '主受让 ≥0.75（客队大热）'),
                         (-0.7, -0.01, '主受让 0.25-0.5'),
                         (-0.01, 0.01, '平手'),
                         (0.01, 0.6, '主让 0.25-0.5'),
                         (0.6, 1.1, '主让 0.75-1'),
                         (1.1, 9, '主让 ≥1.25')):
        m = (al >= lo_) & (al < hi_)
        if m.sum() < 10:
            continue
        show(nm, y, m, ' 初盘主隐 %5.1f%%' % np.nanmean(oh[m]))

    # ── 5. 初盘「亚盘 vs 欧赔」错配 ──
    print('\n=== 5. 初盘 亚盘深度 vs 欧赔隐含 错配（正=盘口比欧赔更看好主）===')
    mis = al * 100 - oh
    for lo_, hi_, nm in ((-999, -10, '盘口远比欧赔浅（诱主？）'),
                         (-10, 10, '基本一致'),
                         (10, 999, '盘口远比欧赔深（诱客？）')):
        m = (mis >= lo_) & (mis < hi_)
        if m.sum() < 10:
            continue
        show(nm, y, m)

    # ── 6. 初盘欧亚背离（亚盘主隐 vs 欧赔主隐）──
    print('\n=== 6. 初盘 亚盘主隐 − 欧赔主隐 ===')
    apo = a('a_p_o')
    xo = apo - oh
    for lo_, hi_, nm in ((-999, -8, '亚盘更悲观于主'), (-8, 8, '一致'),
                         (8, 999, '亚盘更看好主')):
        m = (xo >= lo_) & (xo < hi_)
        if m.sum() < 10:
            continue
        show(nm, y, m)

    # ── 7. 初盘水位 ──
    print('\n=== 7. 初盘上盘水位 ===')
    wo = a('a_w_o')
    for lo_, hi_, nm in ((0, .85, '低水 <0.85'), (.85, .95, '中低 0.85-0.95'),
                         (.95, 1.05, '中高 0.95-1.05'), (1.05, 9, '高水 >1.05')):
        m = (wo >= lo_) & (wo < hi_)
        if m.sum() < 10:
            continue
        show(nm, y, m)

    # ── 8. 初盘跨机构盘口分歧 ──
    print('\n=== 8. 初盘跨机构盘口分歧 ===')
    dl = a('disp_line')
    for lo_, hi_, nm in ((0, .001, '完全一致'), (.001, .26, '分歧 <0.25'),
                         (.26, 99, '分歧 ≥0.25')):
        m = (dl >= lo_) & (dl < hi_)
        if m.sum() < 10:
            continue
        show(nm, y, m)

    # ── 9. 初盘→终盘 变动 ──
    print('\n=== 9. 初盘→终盘 变动（信息在变动里？）===')
    dh = a('d_h')
    for lo_, hi_, nm in ((-99, -1.5, '主隐下降 >1.5pp'), (-1.5, 1.5, '基本不变'),
                         (1.5, 99, '主隐上升 >1.5pp')):
        m = (dh >= lo_) & (dh < hi_)
        if m.sum() < 10:
            continue
        favc = np.argmax(np.column_stack([lh, ld, la]), axis=1)
        k = int((favc[m] == y[m]).sum())
        show(nm, y, m, ' 终盘热门命中 %5.1f%%' % (k / m.sum() * 100))

    json.dump({'n': n, 'base': base}, open(OUT, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('\n→', OUT)


if __name__ == '__main__':
    main()
