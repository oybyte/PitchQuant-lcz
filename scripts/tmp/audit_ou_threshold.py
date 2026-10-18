# -*- coding: utf-8 -*-
"""audit_ou_threshold.py — 大小球判向切点 A/B（435 场·可复现）

背景: calc_all 曾同时存在两套判向切点 ——
  ① over_p 概率分类器 (over_p>=54 判大 / <=46 判小)  ← AGENTS §4.5 旧文引用
  ② O2.5 赔率阈值   (<1.90 判大 / >2.10 判小)      ← 代码实际执行
本脚本量化两者关系，支撑 2026-10-18 的口径收敛决策。

结论（见 docs/整改复核_2026-10-17_435场证据.md 与 AGENTS §4.5 P1）:
  · 在**都做出判向**的场次上结果 100% 相同（McNemar 分歧=0）→ 只是不同切点
  · 差异仅在覆盖范围：赔率切点 371 场净+101 / 概率切点 275 场净+85
  · 赔率切点增量 100 场（over_p∈(46,54) 命中 58%）净收益 21%，p≈0.055 边缘
  → 保留现行阈值，但收敛为单一真源 over_under_direction()

用法: python scripts/tmp/audit_ou_threshold.py
"""
import json, os, sys
sys.stdout.reconfigure(encoding='utf-8')
R = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                 'data', 'tmp')
ORDER = ['batch_203', 'batch_140', 'batch_74', 'batch_2_5_8']   # 由早到晚


def load():
    seen = {}
    for b in ORDER:
        p = os.path.join(R, b, 'result_compare.json')
        if not os.path.exists(p):
            continue
        for r in json.load(open(p, encoding='utf-8')):
            if r.get('o25') and r.get('over_p') is not None:
                r['_b'] = b
                seen[r['slug']] = r
    return list(seen.values())


def by_odds(r):
    o = r['o25']
    if o < 1.90:  return r['tot'] > 2.5
    if o > 2.10:  return r['tot'] < 2.5
    return None


def by_prob(r, hi=54, lo=46):
    p = r['over_p']
    if p >= hi: return r['tot'] > 2.5
    if p <= lo: return r['tot'] < 2.5
    return None


def ev(fn, rows):
    """→ (可判, 命中, 准确率, 净收益)"""
    v = [fn(r) for r in rows]
    v = [x for x in v if x is not None]
    if not v: return (0, 0, 0.0, 0)
    h = sum(1 for x in v if x)
    return (len(v), h, 100.0 * h / len(v), 2 * h - len(v))


def main():
    rows = load()
    print('样本 %d 场（4 批次去重）\n' % len(rows))

    print('=' * 96)
    print('一、全样本对比')
    print('=' * 96)
    print('%-30s %8s %8s %10s %9s' % ('规则', '可判', '命中', '准确率', '净收益'))
    for lab, fn in (('赔率切点 <1.90 / >2.10 (现行)', by_odds),
                    ('概率切点 over_p>=54 / <=46', by_prob)):
        n, h, a, s = ev(fn, rows)
        print('%-30s %8d %8d %9.1f%% %+9d' % (lab, n, h, a, s))

    print()
    print('=' * 96)
    print('二、walk-forward（前向链式·样本外）')
    print('=' * 96)
    print('%-6s %-26s %-18s %-18s' % ('折', '训练', '赔率切点', '概率切点'))
    for i in range(1, len(ORDER)):
        tr = [r for b in ORDER[:i] for r in rows if r['_b'] == b]
        te = [r for r in rows if r['_b'] == ORDER[i]]
        if not te: continue
        a = ev(by_odds, te); b_ = ev(by_prob, te)
        print('%-6d %-26s %-18s %-18s' % (
            i, '%d 场' % len(tr),
            '%d/%d=%.1f%%' % (a[1], a[0], a[2]), '%d/%d=%.1f%%' % (b_[1], b_[0], b_[2])))

    print()
    print('=' * 96)
    print('三、两者关系：都判的场次上是否分歧（McNemar）')
    print('=' * 96)
    both = onlyO = onlyP = neither = 0
    for r in rows:
        a, b_ = by_odds(r), by_prob(r)
        if a is None or b_ is None: continue
        if a and b_: both += 1
        elif a: onlyO += 1
        elif b_: onlyP += 1
        else: neither += 1
    print('  两者都对 %d | 只有赔率对 %d | 只有概率对 %d | 都错 %d' % (both, onlyO, onlyP, neither))
    print('  → 分歧 %d 场 %s' % (onlyO + onlyP,
          '（=0 → 同一刻度不同切点，无"谁更准"之争）' if onlyO + onlyP == 0 else ''))

    print()
    print('=' * 96)
    print('四、覆盖率/准确率权衡（切点越松，覆盖越高）')
    print('=' * 96)
    print('%-32s %8s %8s %10s %9s' % ('方案', '可判', '命中', '准确率', '净收益'))
    cands = [
        ('赔率 <1.90/>2.10 (现行)', by_odds),
        ('概率 over_p>=54/<=46', by_prob),
        ('赔率 <1.70/>2.10 (只判大球强)', lambda r: (r['tot'] > 2.5) if r['o25'] < 1.70 else ((r['tot'] < 2.5) if r['o25'] > 2.10 else None)),
        ('赔率 <1.50/>2.30 (仅极端)', lambda r: (r['tot'] > 2.5) if r['o25'] < 1.50 else ((r['tot'] < 2.5) if r['o25'] > 2.30 else None)),
    ]
    for lab, fn in cands:
        n, h, a, s = ev(fn, rows)
        print('%-32s %8d %8d %9.1f%% %+9d' % (lab, n, h, a, s))

    print()
    print('=' * 96)
    print('五、分档实证（打印"依据"用·与 calc_all.OU_BAND_ACTUAL 对齐）')
    print('=' * 96)
    for lo, hi in ((1.00, 1.30), (1.30, 1.50), (1.50, 1.70), (1.70, 1.90), (1.90, 2.10), (2.10, 2.30)):
        g = [r for r in rows if lo <= r['o25'] < hi]
        if not g: continue
        ov = sum(1 for r in g if r['tot'] > 2.5)
        print('  %.2f-%.2f  n=%3d  实际大2.5 %3d  %.1f%%' % (lo, hi, len(g), ov, 100.0 * ov / len(g)))


if __name__ == '__main__':
    main()
