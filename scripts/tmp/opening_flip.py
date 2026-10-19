#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""opening_flip.py — 深挖「初盘热门 ≠ 终盘热门」这个唯一冒头的信号

初测：热门被推翻的 16 场，终盘热门命中仅 31.2%（正常 60.3%）。
n=16 太小，必须做：扩大样本口径 + 显著性 + 时间分割 + 定义稳健性（换热门阈值）。
"""
import json
import math
import os
import sys

import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import opening_features as OF      # noqa: E402

OUT = os.path.join(OF.ROOT, 'data', 'tmp', 'opening_flip.json')


def wilson(k, n, z=1.96):
    if n == 0:
        return (0., 0.)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - r) / d, (c + r) / d)


def fisher_p(k1, n1, k2, n2):
    """两比例 z 检验（大样本近似）"""
    if n1 < 5 or n2 < 5:
        return None
    p1, p2 = k1 / n1, k2 / n2
    p = (k1 + k2) / (n1 + n2)
    se = math.sqrt(max(p * (1 - p) * (1 / n1 + 1 / n2), 1e-12))
    z = (p1 - p2) / se
    return 0.5 * math.erfc(abs(z) / math.sqrt(2))


def main():
    S = OF.collect()
    y = np.array([x['label'] for x in S])
    n = len(S)
    print('样本 %d\n' % n)

    def fav(F, key):
        v = [F.get(key + '_h', 0), F.get(key + '_d', 0), F.get(key + '_a', 0)]
        return int(np.argmax(v))

    fo = np.array([fav(x['F'], 'o') for x in S])
    fl = np.array([fav(x['F'], 'l') for x in S])
    flip = fo != fl
    hit_o = fo == y
    hit_l = fl == y

    print('=== 1. 热门是否被推翻 ===')
    for nm, m in (('热门未变', ~flip), ('热门被推翻', flip)):
        k = int(hit_l[m].sum())
        lo, hi = wilson(k, int(m.sum()))
        print('  %-12s n=%-3d 终盘热门命中 %5.1f%% [CI %.1f–%.1f]   初盘热门命中 %5.1f%%' % (
            nm, int(m.sum()), k / m.sum() * 100, lo * 100, hi * 100,
            hit_o[m].mean() * 100))
    k1 = int(hit_l[flip].sum()); n1 = int(flip.sum())
    k2 = int(hit_l[~flip].sum()); n2 = int((~flip).sum())
    p = fisher_p(k1, n1, k2, n2)
    print('  两比例检验 p = %s' % ('%.4f' % p if p else 'n/a'))

    print('\n=== 2. 定义稳健性：换「热门」判定口径 ===')
    # 口径B：用「领先第二名 ≥3pp」才算热门，否则视为无明确热门
    def fav_strong(F, key, margin=3.0):
        v = np.array([F.get(key + '_h', 0), F.get(key + '_d', 0), F.get(key + '_a', 0)])
        s = np.sort(v)[::-1]
        if s[0] - s[1] < margin:
            return -1
        return int(np.argmax(v))
    fos = np.array([fav_strong(x['F'], 'o') for x in S])
    fls = np.array([fav_strong(x['F'], 'l') for x in S])
    ok = (fos >= 0) & (fls >= 0)
    flip2 = ok & (fos != fls)
    print('  口径B（领先≥3pp 才算热门）：可用 %d 场，其中被推翻 %d 场' % (ok.sum(), flip2.sum()))
    if flip2.sum() >= 8:
        m = flip2
        k = int(hit_l[m].sum())
        print('    被推翻 n=%d 终盘热门命中 %.1f%%' % (m.sum(), k / m.sum() * 100))
        m2 = ok & ~flip2
        print('    未推翻 n=%d 终盘热门命中 %.1f%%' % (m2.sum(), hit_l[m2].mean() * 100))

    print('\n=== 3. 扩大口径：初盘与终盘「主客顺序反转」===')
    # 主客翻转（初盘押主/押客 与 终盘相反；数组版）
    hv = np.vectorize(lambda f: 0 if f == 0 else (2 if f == 2 else 1))
    rev = hv(fo) != hv(fl)
    print('  主客翻转 n=%d' % rev.sum())
    if rev.sum() >= 8:
        for nm, m in (('主客未翻', ~rev), ('主客翻转', rev)):
            print('    %-8s n=%-3d 终盘热门命中 %5.1f%%  实际 主%4.1f/平%4.1f/客%4.1f' % (
                nm, int(m.sum()), hit_l[m].mean() * 100,
                (y[m] == 0).mean() * 100, (y[m] == 1).mean() * 100, (y[m] == 2).mean() * 100))

    print('\n=== 4. 时间分割稳定性 ===')
    ko = np.array([x.get('kickoff') or '' for x in S])
    order = np.argsort(ko)
    half = n // 2
    for nm, idx in (('前半', order[:half]), ('后半', order[half:])):
        m = np.zeros(n, bool); m[idx] = True
        a, b = m & flip, m & ~flip
        if a.sum() < 4:
            continue
        print('  %s  被推翻 n=%-2d 命中 %5.1f%%   未推翻 n=%-3d 命中 %5.1f%%' % (
            nm, int(a.sum()), hit_l[a].mean() * 100, int(b.sum()), hit_l[b].mean() * 100))

    print('\n=== 5. 被推翻的场次，怎么判才对？ ===')
    if flip.sum() >= 8:
        m = flip
        print('  这些场实际：初盘热门命中 %5.1f%% / 终盘热门 %5.1f%% / 平局 %5.1f%%' % (
            hit_o[m].mean() * 100, hit_l[m].mean() * 100, (y[m] == 1).mean() * 100))
        print('  三向均匀分布（各 33%%）→ 说明「推翻了」等价于「市场自己也不知道」')
        # 检查平局率是否被抬高
        base_draw = (y == 1).mean() * 100
        dd = (y[m] == 1).mean() * 100
        print('  平局率 %.1f%% vs 全样本 %.1f%%  → %+.1fpp' % (dd, base_draw, dd - base_draw))

    json.dump(dict(n=n, flip_n=int(flip.sum()),
                   hit_flip=float(hit_l[flip].mean()) if flip.sum() else None,
                   hit_noflip=float(hit_l[~flip].mean()),
                   p=float(p) if p else None),
              open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('\n→', OUT)


if __name__ == '__main__':
    main()
