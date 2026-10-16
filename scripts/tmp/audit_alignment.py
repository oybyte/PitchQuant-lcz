# -*- coding: utf-8 -*-
"""A1⑬ 查表模块口径一致性探查（2026-09-28·对照 SK-audit A/B 更新方案·优先级 #2）

背景：2026-09-28 NL 子模型评审 P0-1 —— 同一模块三处口径不一致
（建表用 csv 的 `elo_diff`=raw−65 / 运行时 `band_of(raw)` / 消费 `fair_probs(raw+adv)`）
→ 档位表整体平移 65 Elo（均势档主胜高估 11pp）。静态读码查不出，**三处并排即露**。

本脚本对每个查表类模块并排输出三件事的输入口径：
  ① 建表（build/load）时用的字段
  ② 运行时查表函数收到的变量
  ③ 下游消费点的变量
并对**已固化断言**的模块做硬校验（不一致 → exit 1）。

用法:  python data/tmp/audit_alignment.py      # 全过 → exit 0；断言失败 → exit 1
"""
import io
import os
import sys

D = os.path.dirname(os.path.abspath(__file__))
# 🔴2026-09-15 修复: 原 D 指向 scripts/tmp/, 但 score_depth/league/water/goal_bins/
# deep_anchor/draw 六表实际在 data/tmp/ → report_tables() 六表全部"读取失败"。
import sys as _sys
if D not in _sys.path:
    _sys.path.insert(0, D)
from table_paths import find_table as _find_table  # noqa: E402
D_TABLES = os.path.join(os.path.dirname(os.path.dirname(D)), 'data', 'tmp')
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
FAIL = []


def _chk(name, ok, detail=''):
    print('  %s %-52s %s' % ('✅' if ok else '❌', name, detail))
    if not ok:
        FAIL.append(name)


def _src(p):
    try:
        return io.open(os.path.join(D, p), encoding='utf-8').read()
    except Exception:
        return ''


# ══════════ ① nl_model（唯一已固化硬断言的模块·P0-1 复发守卫）══════════
def check_nl_model():
    print('【nl_model】建表 raw(eh−ea) / 查表 band_of(raw) / 消费 fair_probs(raw+adv)')
    s = _src('nl_model.py')
    _chk('建表用 raw = eh − ea', "float(r['eh']) - float(r['ea'])" in s,
         '← 防回退到 elo_diff(=raw−65)')
    _chk('查表输入 d = elo_h − elo_a（raw）', 'd = elo_h - elo_a' in s and 'band_of(d)' in s)
    _chk('消费 fair_probs 用 (elo_h+adv)−elo_a（adv=主场先验·非分档口径）',
         "d = (elo_h + p['adv']) - elo_a" in s)
    _chk('draw_leak 边界为 raw 空间', '-135 <= elo_diff < 15' in s)
    _chk('无遗留 elo_diff 建表（raw−65 空间）',
         "rows.append((float(r['elo_diff'])" not in s)


# ══════════ ② 其余查表模块（并排打印·供审计判断·无硬断言）══════════
TABLES = [
    ('score_depth_table.json', '净胜档 × Over25 5 档', '净胜档来自 Step5 方向；Over25 来自市场赔率'),
    ('league_table.json', '联赛 × 赔率档', '联赛 key + 档位（主胜赔率区间）'),
    ('water_table.json', '盘口 × 水位档', '亚盘盘口 + 水位值'),
    ('goal_bins_table.json', 'Over25 赔率 → 总进球档', 'O25 去水隐含/赔率'),
    ('deep_anchor_table.json', '让球盘深度档', '亚盘盘口（-2/-1.75…）'),
    ('draw_table.json', '赔率档/盘口/ELO → 平局率', '主胜赔率档 + Over25 + ELO 差'),
    ('quadrant_table.json', '亚盘档 × 大小球档', '亚盘档(深/中/浅) + O25 档(大/中/小)'),
]


def report_tables():
    print()
    print('【其余查表模块·口径并排（供审计判断·非硬断言）】')
    print('  %-26s %-22s %s' % ('表', '查表键', '运行时输入来源'))
    for fn, key, src in TABLES:
        rows = ''
        if fn.endswith('.json'):
            try:
                import json
                _p = _find_table(fn)
                if not _p:
                    raise FileNotFoundError(fn)
                d = json.load(io.open(_p, encoding='utf-8'))
                rows = 'n=%d' % (len(d) if hasattr(d, '__len__') else 0)
            except Exception:
                rows = '读取失败'
        else:
            rows = '缺失'
        print('  %-26s %-22s %-38s %s' % (fn, key, src, rows))


def main():
    print('════ A1⑬ 查表模块口径一致性探查 ════')
    check_nl_model()
    report_tables()
    print()
    if FAIL:
        print('🔴 口径一致性断言失败 %d 项: %s' % (len(FAIL), FAIL))
        return 1
    print('🟢 口径一致性断言全过（nl_model 硬断言 + 7 表并排）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
