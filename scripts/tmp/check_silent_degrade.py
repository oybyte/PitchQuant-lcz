#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_silent_degrade.py — 静默降级检测器（阶段1·检查器②）

为什么存在
----------
2026-10-17 这批事故的共同形态不是「报错」，而是**脚本照常打印、数字照常出，
只是悄悄用了一个降级分支**：

  · ou_from_asia 首版把 3.25 线走盘写成 ≥5 球 → 22 场 O2.5 系统性偏高，
    「大球」直接翻成「小球」——没有任何一行输出提示过这件事
  · calc_all 组 cmd 时丢 --eu/--handi/--o25 → V5 恒打印「未提供欧盘」（P0-1）
  · trap_classify_output 只有 def 没有调用点 → 分类段恒空（P0-2）
  · 净胜档拿体彩 L 当亚盘线 → 23/23 场静默取错依据（P0-3）

项目已有铁律「三态标注（触发/不触发(原因)/无数据(原因)）」，但**没有人机械执行它**。
本检测器把铁律变成可执行检查：任何一行宣告了降级/回退/未提供，
要么同行给出原因，要么在最近 N 行内给出原因，否则就是静默降级。

判定口径（宁可放过，不可误报）
------------------------------
  MARKER  降级词汇（未提供/未识别/已忽略/运行失败/不可用/回退到/…）
  REASON  三态词汇（原因/不触发(/无数据(/skipped(/missing(/…）
  · 同一行同时含 MARKER + REASON       → OK（合规三态）
  · 含 MARKER 但同行无 REASON          → 看 CONTEXT 窗口内有无 REASON
  · MARKER 命中白名单（学科用语/提示语） → 跳过

用法
----
    python scripts/tmp/check_silent_degrade.py <输出txt 或 目录> [--json] [--context 2]
退出码: 0 未发现; 1 发现静默降级; 2 用法错误
"""
import argparse
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

# 降级/回退词汇
MARKER = re.compile(
    r'(未提供|未识别|未覆盖|未入库|未采集|已忽略|被跳过|运行失败|解析失败|读取失败|'
    r'不可用|无法获取|回退到|降级为|走降级|fallback)')

# 三态原因词汇（与项目既定口径一致）
REASON = re.compile(
    r'(原因|不触发\(|无数据\(|skipped\(|missing\(|不适用\(|受限于|限流|'
    r'接口不返回|未随.*分发|输入未|该联赛未|未登记)')

# 白名单：这些是学科/提示语，不是运行期降级，误报代价高
WHITELIST = [
    'D1升赔', '硬降级检查', '禁用于排除方向', '降级死守', '凡降级',
    '降级仅可', '不作排除', '仅作参考', '仅提示', '【必核清单',
]

SEP = re.compile(r'^[=\-─━]{6,}$')


def _is_whitelisted(line):
    return any(w in line for w in WHITELIST)


def scan_text(text, context=2):
    """→ findings: [dict(level, code, line_no, line, near_reason)]"""
    lines = text.split('\n')
    out = []
    for i, raw in enumerate(lines):
        line = raw.rstrip()
        if not line.strip() or SEP.match(line.strip()):
            continue
        if not MARKER.search(line):
            continue
        if _is_whitelisted(line):
            continue
        if REASON.search(line):
            # 同行已给原因 → 合规三态（仍记录，用于给出「合规/静默」分母）
            out.append({'level': 'OK', 'code': 'SD00', 'line_no': i + 1,
                        'line': line.strip()[:160], 'near_reason': '(同行)'})
            continue
        # 上下文窗口找原因
        lo, hi = max(0, i - context), min(len(lines), i + context + 1)
        near = None
        for j in range(lo, hi):
            if j == i:
                continue
            if REASON.search(lines[j]):
                near = lines[j].strip()
                break
        out.append({
            'level': 'FAIL' if near is None else 'OK',
            'code': 'SD01' if near is None else 'SD00',
            'line_no': i + 1,
            'line': line.strip()[:160],
            'near_reason': (near or '')[:120],
        })
    return out


def scan_file(path, context=2):
    text = open(path, encoding='utf-8', errors='ignore').read()
    for f in scan_text(text, context):
        f['file'] = os.path.basename(path)
    return [f for f in scan_text(text, context)]


def main():
    ap = argparse.ArgumentParser(description='静默降级检测（阶段1·检查器②）')
    ap.add_argument('target', help='calc_all 输出 txt 或目录')
    ap.add_argument('--context', type=int, default=2, help='原因允许出现的上下文行数(默认2)')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()

    if not os.path.exists(a.target):
        print('目标不存在: %s' % a.target, file=sys.stderr)
        return 2

    results = []
    if os.path.isdir(a.target):
        for fn in sorted(os.listdir(a.target)):
            if fn.endswith('.txt'):
                p = os.path.join(a.target, fn)
                for f in scan_file(p, a.context):
                    f['file'] = fn
                    results.append(f)
    else:
        for f in scan_file(a.target, a.context):
            f['file'] = os.path.basename(a.target)
            results.append(f)

    fails = [r for r in results if r['level'] == 'FAIL']
    oks = [r for r in results if r['level'] == 'OK']

    if a.json:
        print(json.dumps(results, ensure_ascii=False, indent=1))
        return 1 if fails else 0

    print('=' * 72)
    print('check_silent_degrade — 静默降级检测')
    print('=' * 72)
    print('扫描降级行: %d ｜ 合规(同行/上下文给原因): %d ｜ 🔴静默: %d' % (
        len(results), len(oks), len(fails)))
    if fails:
        print()
        print('🔴 静默降级（宣告了降级却不给原因 = 违反三态铁律）:')
        agg = {}
        for f in fails:
            key = f['line']
            agg.setdefault(key, []).append(f['file'])
        for line, files in sorted(agg.items(), key=lambda x: -len(x[1]))[:20]:
            print('  · %s' % line)
            print('      影响 %d 份输出  e.g. %s' % (len(files), files[0][:50]))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
