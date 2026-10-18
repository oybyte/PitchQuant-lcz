# -*- coding: utf-8 -*-
"""verify_claims.py — 核对报告 §5 §6 §7 §8 的事实性断言（用显式映射，不猜文件名）"""
import json, os, re, sys
sys.stdout.reconfigure(encoding='utf-8')
D = r'E:\footbal-github\PitchQuant\data\tmp\batch_14'
OUT = os.path.join(D, 'out')
rows = json.load(open(os.path.join(D, '_review.json'), encoding='utf-8'))
F = {
 '埃弗斯堡_vs_奥格斯堡':'10-17_21_30_德甲_埃弗斯堡_vs_奥格斯堡',
 '柏林联合_vs_多特蒙德':'10-17_21_30_德甲_柏林联合_vs_多特蒙德',
 '汉堡_vs_斯图加特':'10-17_21_30_德甲_汉堡_vs_斯图加特',
 '沙尔克04_vs_美因茨':'10-17_21_30_德甲_沙尔克04_vs_美因茨',
 '富勒姆_vs_赫尔城':'10-17_22_00_英超_富勒姆_vs_赫尔城',
 '布伦特福德_vs_利物浦':'10-17_22_00_英超_布伦特福德_vs_利物浦',
 '曼彻斯特城_vs_伊普斯维奇':'10-17_22_00_英超_曼彻斯特城_vs_伊普斯维奇',
 '比利亚雷亚尔_vs_埃尔切':'10-17_22_15_西甲_比利亚雷亚尔_vs_埃尔切',
 '博洛尼亚_vs_国际米兰':'10-18_00_00_意甲_博洛尼亚_vs_国际米兰',
 '拜仁慕尼黑_vs_RB莱比锡':'10-18_00_30_德甲_拜仁慕尼黑_vs_RB莱比锡',
 '纽卡斯尔联_vs_阿斯顿维拉':'10-18_00_30_英超_纽卡斯尔联_vs_阿斯顿维拉',
 '皇家贝蒂斯_vs_巴塞罗那':'10-18_00_30_西甲_皇家贝蒂斯_vs_巴塞罗那',
 '罗马_vs_热那亚':'10-18_02_45_意甲_罗马_vs_热那亚',
 '巴伦西亚_vs_毕尔巴鄂竞技':'10-18_03_00_西甲_巴伦西亚_vs_毕尔巴鄂竞技'}
bad = []
tops_of = {}
for x in rows:
    t = open(os.path.join(OUT, F[x['name']] + '.txt'), encoding='utf-8').read()
    tops_of[x['name']] = [s.split('(')[0].strip() for s in
                          re.search(r'Top5比分: ([^\n]+)', t).group(1).split('|')]

raw = sum(1 for x in rows if x['real'] in tops_of[x['name']][:2])
inp = sum(1 for x in rows if x['real'] in tops_of[x['name']])
le2 = sum(1 for x in rows if x['real'] in tops_of[x['name']][:2])
print('§5 照搬 Top1/Top2 命中: %d/14 = %.1f%%   (报告 1/14 = 7.1%%)' % (raw, 100.0*raw/14))
print('§6.1 实际比分在 Top5 池内: %d/14 = %.0f%%   (报告 6/14 = 43%%)' % (inp, 100.0*inp/14))
# 排名 ≤2 的场次
rk2 = sum(1 for x in rows if x['real'] in tops_of[x['name']][:2])
print('§6.1 排名 ≤2（真正可锚）: %d 场   (报告 1 场)' % rk2)
if raw != 1: bad.append('§5 %d!=1' % raw)
if inp != 6: bad.append('§6.1 %d!=6' % inp)
if rk2 != 1: bad.append('§6.1 排名≤2 %d!=1' % rk2)

act = [x['tot'] for x in rows]
CTR = [3.5,3.4,3.7,3.2,3.0,3.2,3.9,3.6,3.1,5.0,3.2,4.3,2.9,2.6]
LINES = [3.25,3.00,3.25,3.00,2.75,3.00,3.50,3.25,2.75,4.75,3.00,3.50,2.50,2.50]
O25 = [1.461,1.511,1.384,1.615,1.726,1.584,1.327,1.442,1.652,1.140,1.635,1.256,1.840,2.057]
print('\n§7 实际均 %.2f | 模型均 %.2f | 市场线均 %.2f' % (sum(act)/14.0, sum(CTR)/14.0, sum(LINES)/14.0))
print('   模型高估 %+.2f | 市场高估 %+.2f | MAE %.2f  (报告 +0.69/+0.36/2.14)'
      % (sum(CTR)/14.0-sum(act)/14.0, sum(LINES)/14.0-sum(act)/14.0,
         sum(abs(a-c) for a,c in zip(act,CTR))/14.0))
if abs(sum(CTR)/14.0-sum(act)/14.0-0.69) > 0.02: bad.append('§7 模型偏差')
if abs(sum(LINES)/14.0-sum(act)/14.0-0.36) > 0.02: bad.append('§7 市场偏差')
if abs(sum(abs(a-c) for a,c in zip(act,CTR))/14.0-2.14) > 0.01: bad.append('§7 MAE')

ALL = [(2,1),(2,2),(1,1),(1,3),(2,2),(0,2),(0,2),(0,1),(1,0),(4,0),(2,2),(4,3),(0,0),(1,0),(0,1),
       (1,0),(1,2),(3,2),(0,0),(1,3),(1,3),(6,1),(0,1),(2,5),(3,4),(2,0),(0,0),(1,0)]
le1 = sum(1 for h,a in ALL if h+a <= 1)
print('\n§7.1 全晚 28 场 ≤1 球: %d = %.0f%%   (报告 10 = 36%%)' % (le1, 100.0*le1/28))
if le1 != 10: bad.append('§7.1 %d!=10' % le1)

bs = {'hi':[0,0], 'mid':[0,0]}
for o, tot in zip(O25, act):
    k = 'hi' if o < 1.70 else ('mid' if o < 1.90 else None)
    if k:
        bs[k][0] += 1; bs[k][1] += 1 if tot > 2.5 else 0
print('§7.2 大球强 %d场中%d (%.0f%%) | 大球 %d场中%d  (报告 11/6=54.5%%, 2/0)'
      % (bs['hi'][0], bs['hi'][1], 100.0*bs['hi'][1]/bs['hi'][0], bs['mid'][0], bs['mid'][1]))
if (bs['hi'][0], bs['hi'][1]) != (11, 6): bad.append('§7.2 大球强档')
if (bs['mid'][0], bs['mid'][1]) != (2, 0): bad.append('§7.2 大球档')
if max(O25) > 2.10: bad.append('§7.2 P1 停判应 0 触发')

con = [x for x in rows if x['pdir'] != x['adir']]
print('\n§8 两引擎一致 %d/14 | 冲突 %d | gap<3 %d 场  (报告 13/1/0)'
      % (14-len(con), len(con), sum(1 for x in rows if x['gap'] < 3)))
if (14-len(con), len(con), sum(1 for x in rows if x['gap']<3)) != (13,1,0): bad.append('§8')

print('\n' + ('✅ 报告 §5/§6/§7/§8 事实断言全部复核通过' if not bad else '❌ ' + '; '.join(bad)))
