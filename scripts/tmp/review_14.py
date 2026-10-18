# -*- coding: utf-8 -*-
"""review_14.py — 14 场复盘（口径严格按 AGENTS.md §6）
  · direction_hit_top1 : 仅第一推荐
  · direction_hit_any  : 含并列/次方向（主口径）
  · 比分命中           : 仅主锚+次锚（第3/4候选不算）
  · 总进球区间         : 实际 ∈ [下界, 上界]
  · 大小球             : 🔴 相对 2.5 固定线（信号源口径）
  · 让球               : H−A+L 结算
  · 基线对照           : 永远主胜 / 永远客胜 / 永远平 / 永远大2.5 / 永远小2.5 / 模型反向
"""
import json, math, os, sys
sys.stdout.reconfigure(encoding='utf-8')
D = r'E:\footbal-github\PitchQuant\data\tmp\batch_14'

# ── 我的预测（来自 reports/2026-10-17_14场_分析报告.md §1 总览表）──
PRED = [
 # name,                  dir_top1, dir_parallel, conf,     a1,    a2,    bs,        lo, hi, center, handi, price_dir, agg_dir, agg_gap
 ('埃弗斯堡_vs_奥格斯堡',    'A',      'D',           'LOW',     '1:2','2:2', '大球强',   3, 4, 3.5,  0.00,  'A', 'H', 3.9),
 ('柏林联合_vs_多特蒙德',    'A',      None,          'MID-LOW', '1:2','1:3', '大球强',   3, 4, 3.4,  1.00,  'A', 'A', 33.2),
 ('汉堡_vs_斯图加特',       'A',      None,          'LOW',     '1:2','1:3', '大球强',   3, 4, 3.7,  0.75,  'A', 'A', 23.4),
 ('沙尔克04_vs_美因茨',     'A',      'D',           'LOW',     '1:2','1:1', '大球强',   2, 4, 3.2,  0.25,  'A', 'A', 9.0),
 ('富勒姆_vs_赫尔城',       'H',      'D',           'MID-LOW', '2:1','1:1', '大球',     2, 4, 3.0, -0.75,  'H', 'H', 37.1),
 ('布伦特福德_vs_利物浦',    'H',      'D',           'LOW',     '2:1','2:2', '大球强',   2, 4, 3.2,  0.00,  'H', 'H', 5.9),
 ('曼彻斯特城_vs_伊普斯维奇', 'H',      None,          'HIGH',    '2:1','3:1', '大球强',   3, 5, 3.9, -2.00,  'H', 'H', 66.8),
 ('比利亚雷亚尔_vs_埃尔切',  'H',      None,          'HIGH',    '2:1','3:1', '大球强',   3, 4, 3.6, -1.25,  'H', 'H', 57.6),
 ('博洛尼亚_vs_国际米兰',    'A',      None,          'MID-LOW', '1:2','2:2', '大球强',   2, 4, 3.1,  1.00,  'A', 'A', 32.6),
 ('拜仁慕尼黑_vs_RB莱比锡',  'H',      None,          'MID',     '2:1','3:1', '大球强',   4, 6, 5.0, -2.25,  'H', 'H', 71.0),
 ('纽卡斯尔联_vs_阿斯顿维拉', 'H',      'D',           'LOW',     '2:1','1:1', '大球强',   2, 4, 3.2, -0.25,  'H', 'H', 8.8),
 ('皇家贝蒂斯_vs_巴塞罗那',  'A',      None,          'LOW',     '1:2','1:3', '大球强',   3, 5, 4.3,  1.25,  'A', 'A', 36.7),
 ('罗马_vs_热那亚',         'H',      None,          'MID',     '2:1','1:0', '大球',     2, 3, 2.9, -1.00,  'H', 'H', 39.4),
 ('巴伦西亚_vs_毕尔巴鄂竞技', 'A',      'D',           'LOW',     '1:1','1:2', '中性',     1, 3, 2.6,  0.25,  'A', 'A', 7.3),
]

# ── 实际赛果 ──
REAL = {
 '埃弗斯堡_vs_奥格斯堡': (4, 3), '柏林联合_vs_多特蒙德': (0, 0), '汉堡_vs_斯图加特': (1, 0),
 '沙尔克04_vs_美因茨': (0, 1), '富勒姆_vs_赫尔城': (1, 0), '布伦特福德_vs_利物浦': (1, 2),
 '曼彻斯特城_vs_伊普斯维奇': (3, 2), '比利亚雷亚尔_vs_埃尔切': (0, 0), '博洛尼亚_vs_国际米兰': (1, 3),
 '拜仁慕尼黑_vs_RB莱比锡': (6, 1), '纽卡斯尔联_vs_阿斯顿维拉': (0, 1), '皇家贝蒂斯_vs_巴塞罗那': (2, 5),
 '罗马_vs_热那亚': (2, 0), '巴伦西亚_vs_毕尔巴鄂竞技': (0, 0),
}


def res(h, a):
    return 'H' if h > a else ('A' if a > h else 'D')


def _halves(line):
    """四分之一线 → 两条相邻整/半球线（floor(L*2)/2 与 +0.5）；整/半球线原样返回"""
    if abs(line * 2 - round(line * 2)) < 1e-9:
        return [line, line]
    b = math.floor(line * 2) / 2.0
    return [b, b + 0.5]


def settle_handicap(h, a, line):
    """H−A+L 结算（正=主队赢盘）→ 'win'/'lose'/'push'/'half-win'/'half-lose'"""
    r = []
    for L in _halves(line):
        n = (h - a) + L
        r.append('win' if n > 0 else ('lose' if n < 0 else 'push'))
    w, l_, p = r.count('win'), r.count('lose'), r.count('push')
    if w == 2: return 'win'
    if l_ == 2: return 'lose'
    if p == 2: return 'push'
    return 'half-win' if (w == 1 and p == 1) else 'half-lose'


rows = []
for (name, d1, dpar, conf, a1, a2, bs, lo, hi, ctr, handi, pdir, adir, gap) in PRED:
    h, a = REAL[name]
    r = res(h, a)
    tot = h + a
    hit1 = (r == d1)
    hitany = hit1 or (dpar is not None and r == dpar)
    # 新 §6.5 裁决（gap>=3 才裁决；gap<3 不裁决→三向覆盖）
    if gap < 3:
        arb_dir, arb_note = None, 'gap<3·不裁决'
    elif adir == pdir:
        arb_dir, arb_note = adir, '一致'
    else:
        arb_dir, arb_note = adir, '裁决覆盖'
    arb_hit = (arb_dir is not None and r == arb_dir)
    score = '%d:%d' % (h, a)
    sh = (score == a1) or (score == a2)
    tr = (lo <= tot <= hi)
    if bs == '中性':
        ou = None
    else:
        ou = (tot > 2.5) if bs.startswith('大球') else (tot < 2.5)
        if tot == 2.5: ou = 'push'
    hc = settle_handicap(h, a, handi)
    rows.append(dict(name=name, d1=d1, dpar=dpar, conf=conf, a1=a1, a2=a2, bs=bs, lo=lo, hi=hi,
                     ctr=ctr, handi=handi, pdir=pdir, adir=adir, gap=gap, arb_dir=arb_dir,
                     arb_note=arb_note, real=score, r=r, tot=tot, hit1=hit1, hitany=hitany,
                     arb_hit=arb_hit, sh=sh, tr=tr, ou=ou, hc=hc))


def pct(n, d):
    return '%.1f%%' % (100.0 * n / d) if d else '-'


print('=' * 118)
print('14 场复盘 · 逐场明细（口径：AGENTS.md §6）')
print('=' * 118)
print('%-22s %-4s %-7s %-4s %-9s %-9s %-5s %-9s %-4s %-5s %-6s' % (
    '对阵', '预测', '置信', '实际', '比分锚', '总进球', '区间', '大小球', '让球', '裁决', '价/聚'))
for x in rows:
    dmap = {'H': '主胜', 'D': '平局', 'A': '客胜'}
    ou_s = {True: '✅', False: '❌', 'push': '走', None: '—(中性)'}[x['ou']]
    print('%-22s %-4s %-7s %-4s %-9s %-5s(%-4s) %-5s %-4s %-6s %-6s %s' % (
        x['name'][:22], dmap[x['d1']] + ('+' + dmap[x['dpar']] if x['dpar'] else ''), x['conf'],
        dmap[x['r']], x['a1'] + '/' + x['a2'], x['tot'], '命中' if x['tr'] else '未中',
        '✅' if x['tr'] else '❌', ou_s,
        {'win': '主赢盘', 'lose': '主输盘', 'push': '走盘',
         'half-win': '主半赢', 'half-lose': '主半输'}[x['hc']],
        x['arb_note'], '%s/%s' % (x['pdir'], x['adir'])))
    if x['sh']:
        print('     🔴 比分命中!')

n = len(rows)
print('\n' + '=' * 118)
print('汇总（n=%d）' % n)
print('=' * 118)
hit1 = sum(1 for x in rows if x['hit1'])
hitany = sum(1 for x in rows if x['hitany'])
arbh = sum(1 for x in rows if x['arb_hit'])
sh = sum(1 for x in rows if x['sh'])
tr = sum(1 for x in rows if x['tr'])
ouj = [x for x in rows if x['ou'] is not None]
oum = sum(1 for x in ouj if x['ou'] is True)
hcw = sum(1 for x in rows if x['hc'] in ('win', 'half-win'))
hcl = sum(1 for x in rows if x['hc'] in ('lose', 'half-lose'))
hcp = sum(1 for x in rows if x['hc'] == 'push')

print('方向 top1          : %2d/%d  %s' % (hit1, n, pct(hit1, n)))
print('方向 any(含并列)   : %2d/%d  %s' % (hitany, n, pct(hitany, n)))
print('方向 top1(新§6.5裁决后): %2d/%d  %s' % (arbh, n, pct(arbh, n)))
print('比分命中(主锚+次锚): %2d/%d  %s' % (sh, n, pct(sh, n)))
print('总进球区间         : %2d/%d  %s' % (tr, n, pct(tr, n)))
print('大小球(相对2.5)    : %2d/%d  %s   [可判 %d 场·中性不判 %d 场]' % (oum, len(ouj), pct(oum, len(ouj)), len(ouj), n - len(ouj)))
print('让球 H−A+L         : 主赢盘 %d / 主输盘 %d / 走盘 %d  → %s' % (hcw, hcl, hcp, pct(hcw, n)))

print('\n' + '=' * 118)
print('基线对照（AGENTS §6 强制）')
print('=' * 118)
counts = {'H': sum(1 for x in rows if x['r'] == 'H'),
          'D': sum(1 for x in rows if x['r'] == 'D'),
          'A': sum(1 for x in rows if x['r'] == 'A')}
over_all = sum(1 for x in rows if x['tot'] > 2.5)
print('实际分布           : 主胜 %d / 平 %d / 客胜 %d   |  大2.5 %d / 小2.5 %d' % (
    counts['H'], counts['D'], counts['A'], over_all, n - over_all))
print('永远押主胜         : %2d/%d  %s' % (counts['H'], n, pct(counts['H'], n)))
print('永远押客胜         : %2d/%d  %s' % (counts['A'], n, pct(counts['A'], n)))
print('永远押平           : %2d/%d  %s' % (counts['D'], n, pct(counts['D'], n)))
print('模型 top1          : %2d/%d  %s' % (hit1, n, pct(hit1, n)))
print('模型 反向(押非首选) : %2d/%d  %s' % (n - hit1, n, pct(n - hit1, n)))
print('永远押大球2.5       : %2d/%d  %s' % (over_all, n, pct(over_all, n)))
print('永远押小球2.5       : %2d/%d  %s' % (n - over_all, n, pct(n - over_all, n)))
print('模型 大小球(可判%d场) : %2d/%d  %s' % (len(ouj), oum, len(ouj), pct(oum, len(ouj))))

print('\n' + '=' * 118)
print('置信度分层（方向 top1）')
print('=' * 118)
for c in ('HIGH', 'MID', 'MID-LOW', 'LOW'):
    g = [x for x in rows if x['conf'] == c]
    if not g:
        continue
    h_ = sum(1 for x in g if x['hit1'])
    print('%-8s n=%2d  命中 %2d  %s   (%s)' % (c, len(g), h_, pct(h_, len(g)),
                                              ', '.join(x['name'].split('_')[0] for x in g)))

print('\n' + '=' * 118)
print('错判明细（方向 top1 未中）')
print('=' * 118)
for x in rows:
    if not x['hit1']:
        dmap = {'H': '主胜', 'D': '平局', 'A': '客胜'}
        print('  %-22s 预测 %-4s → 实际 %-4s (%-5s)  置信 %-7s  聚合=%s(gap %.1f)' % (
            x['name'][:22], dmap[x['d1']], dmap[x['r']], x['real'], x['conf'], dmap[x['adir']], x['gap']))

json.dump(rows, open(os.path.join(D, '_review.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1, default=str)
print('\n落盘: data/tmp/batch_14/_review.json')
