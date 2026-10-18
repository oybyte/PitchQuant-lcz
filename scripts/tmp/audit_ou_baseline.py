# -*- coding: utf-8 -*-
"""audit_ou_baseline.py — 审计「判大球 68.5%」基线的可复现性与样本外稳定性

问题来源: AGENTS §4.5 P1 声称 441 场盲测「判大球 235 场命中 68.5%、判小球 72 场命中 50.0%」。
本脚本用 4 个批次各自的 result_compare.json 重算，并做时间分割（样本内 vs 样本外）。
"""
import json, os, sys
sys.stdout.reconfigure(encoding='utf-8')
R = r'E:\footbal-github\PitchQuant\data\tmp'
BATCHES = ['batch_203', 'batch_140', 'batch_74', 'batch_2_5_8']  # 由早到晚

allrows = []
for b in BATCHES:
    p = os.path.join(R, b, 'result_compare.json')
    if not os.path.exists(p):
        continue
    j = json.load(open(p, encoding='utf-8'))
    for r in j:
        r['_batch'] = b
    allrows.append((b, j))
    print('%-12s n=%3d' % (b, len(j)))

flat = [r for _, j in allrows for r in j]
print('\n合计 %d 场（去重前）' % len(flat))

# 去重（同 slug 可能跨批重复）
seen = {}
for r in flat:
    seen.setdefault(r['slug'], []).append(r)
dup = {k: v for k, v in seen.items() if len(v) > 1}
print('重复 slug: %d 个' % len(dup))
for k, v in list(dup.items())[:5]:
    print('   ', k, [x['_batch'] for x in v], [x.get('act') for x in v])
uniq = [v[-1] for v in seen.values()]   # 取最新批次
print('去重后 %d 场' % len(uniq))


def stat(rows, label):
    n = len(rows)
    if not n:
        return
    d = {}
    for r in rows:
        d[r.get('ou_dir')] = d.get(r.get('ou_dir'), 0) + 1
    print('\n%s (n=%d)' % (label, n))
    print('  判向分布: %s' % d)
    for k in ('大球', '小球', '中性', '中性·不判'):
        g = [r for r in rows if r.get('ou_dir') == k]
        if not g:
            continue
        hit = sum(1 for r in g if r.get('hit_ou'))
        print('    %-8s n=%3d  命中 %3d  %5.1f%%' % (k, len(g), hit, 100.0*hit/len(g)))


stat(uniq, '全部（去重）')
stat([r for r in uniq if r.get('ou_dir') == '大球'], '仅判大球')

print('\n' + '='*90)
print('时间分割（按批次先后·看样本外是否保持）')
print('='*90)
for i, (b, j) in enumerate(allrows):
    stat(j, '  '.join(['批次', b]))

print('\n' + '='*90)
print('关键核对: AGENTS §4.5 P1 声称「判大球 235 场 68.5% / 判小球 72 场 50.0%」')
print('='*90)
big = [r for r in uniq if r.get('ou_dir') == '大球']
sm = [r for r in uniq if r.get('ou_dir') == '小球']
print('本脚本复算: 判大球 n=%d 命中 %d (%.1f%%) | 判小球 n=%d 命中 %d (%.1f%%)'
      % (len(big), sum(1 for r in big if r.get('hit_ou')),
         100.0*sum(1 for r in big if r.get('hit_ou'))/len(big) if big else 0,
         len(sm), sum(1 for r in sm if r.get('hit_ou')),
         100.0*sum(1 for r in sm if r.get('hit_ou'))/len(sm) if sm else 0))
print('声称    : 判大球 n=235 命中 160.9(68.5%%) | 判小球 n=72 命中 36(50.0%%)')
print('→ n 是否吻合: 大球 %s / 小球 %s' % (
    '✅' if len(big) == 235 else '❌ 差 %+d' % (len(big)-235),
    '✅' if len(sm) == 72 else '❌ 差 %+d' % (len(sm)-72)))
