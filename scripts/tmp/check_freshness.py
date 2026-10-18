#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_freshness.py — 时点新鲜度门（阶段1·检查器③）

为什么存在
----------
data-2.5.9 单场这一批里，同一场比赛的三个市场时点数量完全不同
（澳门欧赔 4 点 / 亚盘 3 点 / 大小球 2 点），而最新时点距开赛的间隔
逐场差异很大——26 场全部落在「赛前 2.5 小时以上」，没有一场进入临场窗口。

后果不是数据缺失，而是**名分问题**：

  · V6 盘口联动规定「赛前 60-90 分钟才成立」，本批 26/26 都不可能成立，
    但必核清单里 C09 仍逐场打「[必做·源:欧盘临场]」
  · 输出里出现「V6 四象限」等字样时，读者无法从文本判断它是「算了」
    还是「没算但没说话」

本检查器把「数据到底新不新」变成可读的结论：对每场给出**最新时点距开赛的分钟数**，
并判定该场的 V6 / 临场类模块应标「可用」还是「不适用(原因)」。

阈值（与项目 V6 条文一致）
--------------------------
  ≤ 90 min   → 临场，V6 可判定
  90-180 min → 次临场，V6 可作弱参考（须标注）
  > 180 min  → 非临场，V6 不适用（须显式标原因，且不得引用四象限结论）

用法
----
    python scripts/tmp/check_freshness.py <输入txt 或 目录> [--max-min 90] [--json]
退出码: 0 全部可用/已正确标注; 1 存在「非临场却宣称 V6 可用」; 2 用法错误
"""
import argparse
import datetime
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

KICKOFF_RE = re.compile(
    r'比赛时间[:：]\s*(?:(\d{4})-)?(\d{2})-(\d{2})\s+(\d{2}):(\d{2})')
FETCH_RE = re.compile(r'抓取\s*(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2}):(\d{2})')
ROW_RE = re.compile(r'^(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2})(?::(\d{2}))?\s*,', re.M)

LIVE_MIN = 90
SEMI_MIN = 180


def _dt(y, mo, d, hh, mi, ss=0):
    try:
        return datetime.datetime(int(y), int(mo), int(d), int(hh), int(mi), int(ss))
    except ValueError:
        return None


def parse_times(text):
    fetched = None
    fm = FETCH_RE.search(text)
    if fm:
        fetched = _dt(*fm.groups())

    ko = None
    m = KICKOFF_RE.search(text)
    if m:
        y, mo, d, hh, mi = m.groups()
        if not y:
            # 输入模板只给 MM-DD HH:MM（年份在「2026/2027赛季」里）→ 以抓取年份为基，
            # 跨年（开赛月比抓取月小 6 个月以上）则进一位
            y = str(fetched.year) if fetched else '2026'
            if fetched and int(mo) + 6 < fetched.month:
                y = str(int(y) + 1)
        ko = _dt(y, mo, d, hh, mi)

    # 各市场时间戳（逐行）。🔴只有【胜平负】是可做形态学的真时序通道；
    # 其余市场在本数据结构下多为单行，抓取时刻被当作时间戳写入，不能当「最新市场时点」。
    per = {}
    for sec in ('胜平负固定奖金', '让球胜平负固定奖金', '半全场胜平负固定奖金',
                '总进球固定奖金', '比分固定奖金'):
        seg = re.search(r'【%s[^】]*】\s*\n(.*?)(?=\n【|\Z)' % re.escape(sec), text, re.S)
        if not seg:
            continue
        rows = ROW_RE.findall(seg.group(1))
        ts = [_dt(*[x or 0 for x in g]) for g in rows]
        ts = [t for t in ts if t]
        if ts:
            per[sec] = ts
    return ko, fetched, per


def classify(minutes):
    if minutes is None:
        return 'UNKNOWN'
    if minutes <= LIVE_MIN:
        return 'LIVE'
    if minutes <= SEMI_MIN:
        return 'SEMI'
    return 'STALE'


# V6 结论具体形态（引用即视为使用了 V6）
# V6 结论具体形态（引用即视为使用了 V6）
V6_CLAIM = re.compile(
    r'(V6\s*四象限|V6四象限|引导四象限|剪刀差|卡位|退盘真假)')

# 反向语义：「禁与 V6 四象限同档引用」是**警示**，不是引用。
# 必须区分，否则门会把它自己的警示语当成违规。
V6_NEGATED = re.compile(
    r'(禁与|禁引用|禁当|不得引用|不得当|不可引用|不能引用|'
    r'不适用|不成立|仅作|仅为|仅供|未回测|无出处|'
    r'不作为|不参与)')


def find_v6_claims(text):
    """只算真正的 V6 引用，排除警示语/三态否定语境"""
    hits = set()
    for m in V6_CLAIM.finditer(text):
        lo = max(0, m.start() - 24)
        ctx = text[lo:m.end() + 6]
        if V6_NEGATED.search(ctx):
            continue
        # 防误报：硬门自己的拒绝行会把 V6 各子项名字列一遍
        #（「V6 四象限/剪刀差/卡位/退盘 一律不得引用」）——那是拒绝，不是引用。
        line_start = text.rfind('\n', 0, m.start()) + 1
        line_end = text.find('\n', m.end())
        line = text[line_start:line_end if line_end > 0 else len(text)]
        if V6_NEGATED.search(line) or 'V6 硬门' in line or '一律不得引用' in line:
            continue
        hits.add(m.group(1))
    return sorted(hits)

# calc_match 硬门拒绝时必须出现的标记
GATE_REFUSED = '🚫 硬门拒绝'
GATE_WEAK = '⚠️ 弱门'
GATE_LIVE = '✅ 可判定'


def check_output_dir(out_dir, rows):
    """下游合规：非临场场次的输出不得引用 V6，且必须出现硬门拒绝行"""
    findings = []
    by_key = {}
    for r in rows:
        by_key[r['file']] = r
    for fn in sorted(os.listdir(out_dir)):
        if not fn.endswith('.txt'):
            continue
        base = fn[:-4]
        key = base + '.txt'
        if key not in by_key:
            continue
        row = by_key[key]
        out = open(os.path.join(out_dir, fn), encoding='utf-8', errors='ignore').read()
        claims = find_v6_claims(out)
        if row['band'] == 'STALE':
            if claims:
                findings.append({
                    'level': 'FAIL', 'file': fn,
                    'msg': '非临场(距开赛 %.0f 分钟)但输出仍引用 V6 结论: %s'
                           % (row['minutes_before_ko'], ' / '.join(sorted(set(claims)))),
                })
            elif GATE_REFUSED not in out:
                findings.append({
                    'level': 'FAIL', 'file': fn,
                    'msg': '非临场但输出未出现硬门拒绝行 —— 无法证明 V6 被阻断',
                })
        elif row['band'] == 'SEMI' and claims:
            findings.append({
                'level': 'WARN', 'file': fn,
                'msg': '次临场(距开赛 %.0f 分钟)引用 V6 —— 仅可弱参考，不得当强信号'
                       % row['minutes_before_ko'],
            })
        elif row['band'] == 'LIVE' and (GATE_LIVE not in out):
            findings.append({
                'level': 'WARN', 'file': fn,
                'msg': '临场场次但输出未出现 V6 可判定行',
            })
    return findings


def check_file(path):
    text = open(path, encoding='utf-8', errors='ignore').read()
    ko, fetched, per = parse_times(text)
    # 新鲜度只看【胜平负】真时序通道
    series = per.get('胜平负固定奖金') or []
    latest = max(series) if series else None
    mins = None
    if ko and latest:
        mins = (ko - latest).total_seconds() / 60.0
    band = classify(mins)

    # 文本里是否已显式声明临场状态
    declares = bool(re.search(r'(非临场|临场|无临场数据|不触发\(原因)', text))
    claims_v6 = bool(re.search(r'(V6 四象限|V6四象限|盘口联动.*(触发|成立))', text))

    level = 'OK'
    msg = ''
    if band == 'STALE' and claims_v6:
        level = 'FAIL'
        msg = '最新时点距开赛 %.0f 分钟（>%d，非临场），文中仍出现 V6 结论' % (mins, SEMI_MIN)
    elif band in ('STALE', 'SEMI') and not declares:
        level = 'WARN'
        msg = '最新时点距开赛 %.0f 分钟，未见临场状态声明' % mins

    return {
        'file': os.path.basename(path),
        'kickoff': ko.strftime('%Y-%m-%d %H:%M') if ko else None,
        'fetched': fetched.strftime('%Y-%m-%d %H:%M:%S') if fetched else None,
        'latest_point': latest.strftime('%Y-%m-%d %H:%M') if latest else None,
        'minutes_before_ko': round(mins, 1) if mins is not None else None,
        'band': band,
        'series_points': len(series),
        'first_point': series[0].strftime('%m-%d %H:%M') if series else None,
        'sections': {k: len(v) for k, v in per.items()},
        'declares_live_state': declares,
        'claims_v6': claims_v6,
        'level': level,
        'msg': msg,
    }


def main():
    ap = argparse.ArgumentParser(description='时点新鲜度门（阶段1·检查器③）')
    ap.add_argument('target', help='标准输入 txt 或目录')
    ap.add_argument('--output', help='calc_all 输出目录（验证下游是否守住 V6 硬门）')
    ap.add_argument('--strict', action='store_true', help='WARN 也算失败（默认只有 FAIL 阻断）')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()

    if not os.path.exists(a.target):
        print('目标不存在: %s' % a.target, file=sys.stderr)
        return 2

    files = []
    if os.path.isdir(a.target):
        files = [os.path.join(a.target, f) for f in sorted(os.listdir(a.target))
                 if f.endswith('.txt') and not f.endswith('.pin.txt')]
    else:
        files = [a.target]

    rows = [check_file(p) for p in files]
    fails = [r for r in rows if r['level'] == 'FAIL']
    warns = [r for r in rows if r['level'] == 'WARN']

    out_findings = []
    if a.output:
        if not os.path.isdir(a.output):
            print('输出目录不存在: %s' % a.output, file=sys.stderr)
            return 2
        out_findings = check_output_dir(a.output, rows)

    if a.json:
        print(json.dumps({'inputs': rows, 'output_findings': out_findings},
                         ensure_ascii=False, indent=1))
        bad = fails or [f for f in out_findings if f['level'] == 'FAIL']
        if a.strict:
            bad = bad or [f for f in out_findings if f['level'] == 'WARN']
        return 1 if bad else 0

    print('=' * 90)
    print('check_freshness — 时点新鲜度门')
    print('=' * 90)
    print('%-40s %-8s %-9s %-9s %-7s %s' % ('场次', '判定', '距开赛', '末点时刻', '时序点', 'V6 可用'))
    print('-' * 92)
    for r in rows:
        uso = '%s' % (r['minutes_before_ko'] if r['minutes_before_ko'] is not None else '—')
        band_cn = {'LIVE': '临场', 'SEMI': '次临场', 'STALE': '非临场', 'UNKNOWN': '无法判定'}[r['band']]
        v6 = {'LIVE': '✅ 可判定', 'SEMI': '⚠️ 仅弱参考', 'STALE': '❌ 不适用', 'UNKNOWN': '? '}[r['band']]
        lp = (r['latest_point'] or '—')[-11:] if r['latest_point'] else '—'
        print('%-40s %-8s %-9s %-9s %-7d %s' % (
            r['file'][:40], band_cn, uso, lp, r['series_points'], v6))
    print()
    print('分布: 临场 %d ｜ 次临场 %d ｜ 非临场 %d ｜ 无法判定 %d' % (
        sum(1 for r in rows if r['band'] == 'LIVE'),
        sum(1 for r in rows if r['band'] == 'SEMI'),
        sum(1 for r in rows if r['band'] == 'STALE'),
        sum(1 for r in rows if r['band'] == 'UNKNOWN')))
    if fails:
        print('\n🔴 输入本身存在问题:')
        for r in fails:
            print('  · %s — %s' % (r['file'][:52], r['msg']))
    elif warns:
        print('\n⚠️ 未见临场状态声明: %d 份' % len(warns))

    if a.output:
        print()
        print('─' * 90)
        print('下游硬门合规检查（--output）')
        print('─' * 90)
        if not out_findings:
            print('✅ 全部场次守住 V6 硬门（非临场不引用·硬门拒绝行齐备）')
        else:
            of = [f for f in out_findings if f['level'] == 'FAIL']
            ow = [f for f in out_findings if f['level'] == 'WARN']
            for f in of:
                print('❌ %s — %s' % (f['file'][:48], f['msg']))
            for f in ow:
                print('⚠️ %s — %s' % (f['file'][:48], f['msg']))
            fails = fails + of
            if a.strict:
                fails = fails + ow
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
