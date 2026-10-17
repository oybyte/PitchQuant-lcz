
# -*- coding: utf-8 -*-
"""v259_consistency.py — 数值自洽性体检（不只查接线，查数字对不对）"""
import json, os, re, sys
sys.stdout.reconfigure(encoding='utf-8')
DEST = os.path.join('data','tmp','batch_v259_today')
OUT = os.path.join(DEST, 'out')
man = json.load(open(os.path.join(DEST,'_manifest.json'), encoding='utf-8'))
bases = [m['name'].replace(' ','_').replace('(','').replace(')','') for m in man]

DIRMAP = {'主胜':'H','平局':'D','客胜':'A'}
def outcome(sc):
    a,b = map(int, sc.split(':'))
    return 'H' if a>b else ('D' if a==b else 'A')

rows = []
for m, b in zip(man, bases):
    t = open(os.path.join(OUT, b+'.txt'), encoding='utf-8').read()
    d = re.search(r'方向\(欧亚综合\): (\S+?)\(([A-Z\-]+)\)', t)
    a = re.search(r'主锚建议: (\S+) \| 次锚建议: (\S+)\(', t)
    dv = re.search(r'隐含: 主([\d.]+)%/平([\d.]+)%/客([\d.]+)%', t)
    sk = re.search(r'skew精确计算: ([\d.]+)/([\d.]+) = ([\d.]+)%', t)
    lam = re.search(r'λ: 主([\d.]+) 客([\d.]+) 总([\d.]+)', t)
    agg = re.search(r'聚合: 主([\d.]+)% 平([\d.]+)% 客([\d.]+)% \| O2\.5([\d.]+)%', t)
    amc = re.search(r'锚-市场一致性: ([^\n|]+)', t)
    rows.append(dict(name=m['name'], dir=d.group(1) if d else None, conf=d.group(2) if d else None,
                     a1=a.group(1) if a else None, a2=a.group(2) if a else None,
                     dev=list(map(float, dv.groups())) if dv else None,
                     skew=float(sk.group(3)) if sk else None,
                     sk_pair=(float(sk.group(1)), float(sk.group(2))) if sk else None,
                     lam=(float(lam.group(1)), float(lam.group(2))) if lam else None,
                     agg=list(map(float, agg.groups())) if agg else None,
                     amc=(amc.group(1).strip() if amc else None)))

print('%-38s %-8s %-14s %-10s %-10s %s' % ('场次','方向','主锚/次锚','锚向','一致','备注'))
print('-'*118)
issues = []
for r in rows:
    o1 = outcome(r['a1']) if r['a1'] else None
    o2 = outcome(r['a2']) if r['a2'] else None
    want = DIRMAP.get(r['dir'])
    ok = want in (o1,o2)
    if not ok: issues.append(('锚向不含方向', r['name'], '%s vs %s/%s' % (r['dir'], o1, o2)))
    print('%-38s %-8s %-14s %-10s %-10s %s' % (
        r['name'][:38], r['dir'], '%s/%s' % (r['a1'], r['a2']),
        '%s/%s' % (o1,o2), '✅' if ok else '🔴',
        (r['amc'] or '')[:26]))

print()
print('=== 数值自洽性 ===')
bad = 0
for r in rows:
    if r['dev'] and r['skew'] and r['sk_pair']:
        # skew 应 = 最大/次大
        hi, lo = max(r['dev']), sorted(r['dev'])[-2]
        calc = round(hi/lo*100, 1)
        if abs(calc - r['skew']) > 1.5:
            bad += 1
            print('  🔴 skew 与隐含不符: %s  隐含%s → %.1f%% 但报 %.1f%%' % (r['name'][:30], r['dev'], calc, r['skew']))
    if r['lam'] and r['agg']:
        lh, la = r['lam']
        # λ 主客差应与聚合方向一致
        if abs(lh-la) > 0.15:
            lam_dir = 'H' if lh>la else 'A'
            agg_dir = ['H','D','A'][max(range(3), key=lambda i: r['agg'][i])]
            if lam_dir != agg_dir:
                bad += 1
                print('  🔴 λ 与聚合方向相反: %s  λ %.2f/%.2f → %s，聚合最高 %s' % (r['name'][:30], lh, la, lam_dir, agg_dir))
    if r['agg']:
        s = sum(r['agg'][:3])
        if abs(s-100) > 1.5:
            bad += 1
            print('  🔴 聚合概率和≠100: %s  %.1f' % (r['name'][:30], s))
print('数值异常: %d' % bad)
print()
print('锚向不含方向: %d 场' % len(issues))
for i in issues: print('   ', i[1], '|', i[2])
