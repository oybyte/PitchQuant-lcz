# -*- coding: utf-8 -*-
"""亚盘×大小球四象限表构建（2026-09-27·V6 修正54 量化·用户要求立即固化）

数据源: Matches.csv（约 14.8 万场可用: HandiSize + Over25/Under25 + 进球/FTResult）
分箱:
  · 亚盘档 |HandiSize| : 浅 <=0.5 / 中 <1.5 / 深 >=1.5
  · 大小球档 (O2.5 去水隐含): 大球强 >=0.55 / 小球强 <=0.45 / 中性
输出: quadrant_table.json（含 全量 + 时间分割 train/test 的 O2.5 校验）
用法: python data/tmp/build_quadrant_table.py
"""
import csv
import io
import os
import json
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from table_paths import find_root, find_table  # noqa: E402  <- 统一路径解析(唯一真源)

ROOT = find_root()
SRC = os.path.join(ROOT, 'data', 'Matches.csv')
# 2026-09-15 修复(P5): 原输出到 HERE(=scripts/tmp/) 而消费方(audit_alignment TABLES)与
# table_paths 规范位置都是 data/tmp/ -> 生成后仍「读取失败」; 本文件 L9 自述用法亦为 data/tmp/。
# 已有同名表时尊重其现有位置(避免双份), 否则写规范位置 data/tmp/。
_OUT_EXIST = find_table('quadrant_table.json')
OUT = _OUT_EXIST or os.path.join(ROOT, 'data', 'tmp', 'quadrant_table.json')


def hband(hs):
    a = abs(hs)
    return '浅' if a <= 0.5 else ('中' if a < 1.5 else '深')


def tband(o, u):
    po = (1.0 / o) / (1.0 / o + 1.0 / u)
    return ('大球强' if po >= 0.55 else ('小球强' if po <= 0.45 else '中性')), po


def main():
    rows = []
    with io.open(SRC, encoding='utf-8', errors='replace') as f:
        for r in csv.DictReader(f):
            try:
                hs = float(r['HandiSize'])
                o = float(r['Over25'])
                u = float(r['Under25'])
                gh = int(float(r['FTHome']))
                ga = int(float(r['FTAway']))
            except Exception:
                continue
            if o <= 1.01 or u <= 1.01 or r.get('FTResult') not in ('H', 'D', 'A'):
                continue
            rows.append((r['MatchDate'], hs, o, u, gh, ga, r['FTResult']))
    rows.sort(key=lambda x: x[0])
    cut = int(len(rows) * 0.8)

    def agg(part):
        G = {}
        for dt, hs, o, u, gh, ga, res in part:
            tb, po = tband(o, u)
            k = '%s+%s' % (hband(hs), tb)
            v = G.setdefault(k, [0, 0, 0, 0, 0])
            v[0] += 1
            v[1] += 1 if (gh + ga) >= 3 else 0
            v[2] += 1 if res == 'H' else 0
            v[3] += 1 if res == 'D' else 0
            v[4] += 1 if res == 'A' else 0
        return G

    allG = agg(rows)
    trG = agg(rows[:cut])
    teG = agg(rows[cut:])
    b = [0, 0, 0, 0, 0]
    for v in allG.values():
        for i in range(5):
            b[i] += v[i]
    table = {}
    for k, v in allG.items():
        n = v[0]
        if n < 30:
            table[k] = {'n': n, 'note': '样本不足(<30)·不采用·仅标注'}
            continue
        e = {'n': n,
             'o25': round(v[1] / n, 4), 'h': round(v[2] / n, 4),
             'd': round(v[3] / n, 4), 'a': round(v[4] / n, 4)}
        if k in trG and trG[k][0]:
            e['train_o25'] = round(trG[k][1] / trG[k][0], 4)
        if k in teG and teG[k][0]:
            e['test_o25'] = round(teG[k][1] / teG[k][0], 4)
        table[k] = e
    out = {'meta': {
        'built': '2026-09-27', 'src': 'Matches.csv', 'n_total': len(rows),
        'baseline': {'o25': round(b[1] / b[0], 4), 'h': round(b[2] / b[0], 4),
                     'd': round(b[3] / b[0], 4), 'a': round(b[4] / b[0], 4)},
        'bands': {'handi': '浅<=0.5 / 中<1.5 / 深>=1.5',
                  'o25': '大球强>=0.55 / 小球强<=0.45 / 中性'},
        'rule': 'V6修正54四象限(2026-09-27首次22.7万场验证·只调置信度·永不反转L2方向)'},
        'table': table}
    io.open(OUT, 'w', encoding='utf-8').write(json.dumps(out, ensure_ascii=False, indent=1))
    print('已生成', OUT)
    for k in sorted(table):
        e = table[k]
        if e.get('n', 0) >= 30:
            print('  %-10s n=%-6d O2.5=%.1f%% 主/平/客=%.1f/%.1f/%.1f  (train %.1f%% / test %.1f%%)' % (
                k, e['n'], e['o25'] * 100, e['h'] * 100, e['d'] * 100, e['a'] * 100,
                (e.get('train_o25') or 0) * 100, (e.get('test_o25') or 0) * 100))
    print('  基线 O2.5=%.1f%%' % (out['meta']['baseline']['o25'] * 100))


if __name__ == '__main__':
    main()
