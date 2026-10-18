# -*- coding: utf-8 -*-
"""review_anchor.py — 反事实：若照搬脚本 Top1/Top2 会怎样？（校验"禁机械照搬"这条规则本身）"""
import os, re, sys
sys.stdout.reconfigure(encoding='utf-8')
D = r'E:\footbal-github\PitchQuant\data\tmp\batch_14\out'
CASES = [
 ('埃弗斯堡_vs_奥格斯堡','10-17_21_30_德甲_埃弗斯堡_vs_奥格斯堡',(4,3),'1:2','2:2'),
 ('柏林联合_vs_多特蒙德','10-17_21_30_德甲_柏林联合_vs_多特蒙德',(0,0),'1:2','1:3'),
 ('汉堡_vs_斯图加特','10-17_21_30_德甲_汉堡_vs_斯图加特',(1,0),'1:2','1:3'),
 ('沙尔克04_vs_美因茨','10-17_21_30_德甲_沙尔克04_vs_美因茨',(0,1),'1:2','1:1'),
 ('富勒姆_vs_赫尔城','10-17_22_00_英超_富勒姆_vs_赫尔城',(1,0),'2:1','1:1'),
 ('布伦特福德_vs_利物浦','10-17_22_00_英超_布伦特福德_vs_利物浦',(1,2),'2:1','2:2'),
 ('曼彻斯特城_vs_伊普斯维奇','10-17_22_00_英超_曼彻斯特城_vs_伊普斯维奇',(3,2),'2:1','3:1'),
 ('比利亚雷亚尔_vs_埃尔切','10-17_22_15_西甲_比利亚雷亚尔_vs_埃尔切',(0,0),'2:1','3:1'),
 ('博洛尼亚_vs_国际米兰','10-18_00_00_意甲_博洛尼亚_vs_国际米兰',(1,3),'1:2','2:2'),
 ('拜仁慕尼黑_vs_RB莱比锡','10-18_00_30_德甲_拜仁慕尼黑_vs_RB莱比锡',(6,1),'2:1','3:1'),
 ('纽卡斯尔联_vs_阿斯顿维拉','10-18_00_30_英超_纽卡斯尔联_vs_阿斯顿维拉',(0,1),'2:1','1:1'),
 ('皇家贝蒂斯_vs_巴塞罗那','10-18_00_30_西甲_皇家贝蒂斯_vs_巴塞罗那',(2,5),'1:2','1:3'),
 ('罗马_vs_热那亚','10-18_02_45_意甲_罗马_vs_热那亚',(2,0),'2:1','1:0'),
 ('巴伦西亚_vs_毕尔巴鄂竞技','10-18_03_00_西甲_巴伦西亚_vs_毕尔巴鄂竞技',(0,0),'1:1','1:2'),
]

print('='*118)
print('反事实 A：若照搬脚本 Top1/Top2（我的报告里"禁机械照搬"驳回了几条，这里看驳回对不对）')
print('='*118)
print('%-24s %-6s %-9s %-9s %-6s %-9s %-6s %-5s' % ('对阵','实际','脚本Top1/2','我的主/次锚','脚本中','我中','驳回','判定'))
raw_hit = my_hit = 0
for name, f, (h, a), m1, m2 in CASES:
    t = open(os.path.join(D, f + '.txt'), encoding='utf-8').read()
    tops = re.search(r'Top5比分: ([^\n]+)', t).group(1)
    t1, t2 = [s.split('(')[0].strip() for s in tops.split('|')][:2]
    sc = '%d:%d' % (h, a)
    rh = sc in (t1, t2); mh = sc in (m1, m2)
    raw_hit += rh; my_hit += mh
    overridden = (t1, t2) != (m1, m2)
    verdict = ''
    if overridden and rh and not mh: verdict = '🔴 驳回错了（原本会中）'
    elif overridden and not rh and mh: verdict = '✅ 驳回对了'
    elif overridden and rh and mh: verdict = '⚠️ 都中（无影响）'
    elif overridden: verdict = '— 都没中'
    print('%-24s %-6s %-9s %-9s %-6s %-9s %-6s %s' % (
        name[:24], sc, t1 + '/' + t2, m1 + '/' + m2, '✅' if rh else '❌', '✅' if mh else '❌',
        '是' if overridden else '否', verdict))
print('\n照搬脚本 Top1/Top2 : %d/14 = %.0f%%' % (raw_hit, 100.0*raw_hit/14))
print('我的主锚/次锚      : %d/14 = %.0f%%' % (my_hit, 100.0*my_hit/14))

print('\n' + '='*118)
print('反事实 B：实际比分在 Top5 里的"排名"分布（池内≠可及）')
print('='*118)
rank = []
for name, f, (h, a), m1, m2 in CASES:
    t = open(os.path.join(D, f + '.txt'), encoding='utf-8').read()
    tops = [s.split('(')[0].strip() for s in
            re.search(r'Top5比分: ([^\n]+)', t).group(1).split('|')]
    sc = '%d:%d' % (h, a)
    r = tops.index(sc) + 1 if sc in tops else None
    rank.append((name, sc, r))
for name, sc, r in rank:
    print('  %-24s 实际 %-4s → Top5 排名 %s' % (name[:24], sc, ('#%d' % r) if r else '池外'))
inpool = [r for _, _, r in rank if r]
from collections import Counter
print('\n池内 %d 场，排名分布: %s' % (len(inpool), dict(sorted(Counter(inpool).items()))))
print('→ 排名 ≤2（可锚）: %d 场；排名 3-5（池内但不可锚）: %d 场' % (
    sum(1 for r in inpool if r <= 2), sum(1 for r in inpool if r >= 3)))
