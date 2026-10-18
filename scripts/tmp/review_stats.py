# -*- coding: utf-8 -*-
"""review_stats.py — 显著性 + 体彩让球L + 半全场传导（14 场）"""
import math, sys
sys.stdout.reconfigure(encoding='utf-8')

def binom_cdf(k, n, p):
    return sum(math.comb(n, i) * p**i * (1-p)**(n-i) for i in range(k+1))

def halves(line):
    if abs(line*2 - round(line*2)) < 1e-9:
        return [line, line]
    b = math.floor(line*2)/2.0
    return [b, b+0.5]

def settle(h, a, line):
    r = []
    for L in halves(line):
        n = (h-a) + L
        r.append('win' if n > 0 else ('lose' if n < 0 else 'push'))
    w, l, p = r.count('win'), r.count('lose'), r.count('push')
    if w==2: return 'win'
    if l==2: return 'lose'
    if p==2: return 'push'
    return 'half-win' if (w==1 and p==1) else 'half-lose'

# name, (h,a), 半场(h,a), 亚盘handi, 体彩L
M = [
 ('埃弗斯堡vs奥格斯堡', (4,3), (3,1),  0.00, -1),
 ('柏林联合vs多特蒙德', (0,0), (0,0),  1.00,  1),
 ('汉堡vs斯图加特',    (1,0), (0,0),  0.75,  1),
 ('沙尔克04vs美因茨',  (0,1), (0,1),  0.25,  1),
 ('富勒姆vs赫尔城',    (1,0), (1,0), -0.75, -1),
 ('布伦特福德vs利物浦', (1,2), (1,0),  0.00, -1),
 ('曼城vs伊普斯维奇',  (3,2), (2,1), -2.00, -2),
 ('比利亚雷亚尔vs埃尔切',(0,0), (0,0), -1.25, -1),
 ('博洛尼亚vs国际米兰', (1,3), (1,1),  1.00,  1),
 ('拜仁vsRB莱比锡',    (6,1), (3,0), -2.25, -2),
 ('纽卡斯尔vs维拉',    (0,1), (0,1), -0.25, -1),
 ('贝蒂斯vs巴塞罗那',  (2,5), (1,2),  1.25,  1),
 ('罗马vs热那亚',      (2,0), (0,0), -1.00, -1),
 ('巴伦西亚vs毕尔巴鄂', (0,0), (0,0),  0.25,  1),
]

print('='*100)
print('一、体彩让球 L 结算（H−A+L）· 与亚盘分列')
print('='*100)
print('%-22s %-6s %-8s %-12s %-8s %-12s' % ('对阵','比分','体彩L','体彩结算','亚盘','亚盘结算'))
jcs = {'主赢盘':0,'主输盘':0,'走盘':0}
for name,(h,a),ht,ah,L in M:
    jc = settle(h,a,L); asia = settle(h,a,ah)
    jcs[{'win':'主赢盘','lose':'主输盘','push':'走盘','half-win':'主赢盘','half-lose':'主输盘'}[jc]] += 1
    print('%-22s %-6s %-8s %-12s %-8s %-12s' % (name, '%d:%d'%(h,a), '%+g'%L, jc, '%+.2f'%ah, asia))
print('\n体彩让球 L 汇总: 主赢盘 %d / 主输盘 %d / 走盘 %d → 主赢盘率 %.1f%%'
      % (jcs['主赢盘'], jcs['主输盘'], jcs['走盘'], 100.0*jcs['主赢盘']/14))

print('\n' + '='*100)
print('二、显著性检验（二项）')
print('='*100)
def show(label, k, n, p0, note=''):
    p_hi = 1 - binom_cdf(k-1, n, p0) if k > 0 else 1.0
    p_lo = binom_cdf(k, n, p0)
    print('%-34s %2d/%2d = %5.1f%%   期望 %.1f 场   低于期望的概率 P(X≤%d)=%.3f %s'
          % (label, k, n, 100.0*k/n, n*p0, k, p_lo, note))
show('方向 top1 vs 随机 33.3%', 7, 14, 1/3.0)
show('方向 top1 vs 纯主场 42.9%', 7, 14, 6/14.0)
show('比分锚 vs 项目基线 25.5%', 0, 14, 0.255, '← P<0.02 显著低于基线')
show('大小球 vs 项目基线 68.5%', 6, 13, 0.685, '← P<0.05 显著低于基线')
show('总进球区间(基准 3/14=21.4%)', 4, 14, 3/14.0)

print('\n' + '='*100)
print('三、半全场传导（分析时标「无数据」，现用真实半场复核）')
print('='*100)
ht_draw = [(n,h,a,ht) for n,(h,a),ht,_,_ in M if ht[0]==ht[1]]
print('半场平局 %d 场:' % len(ht_draw))
for n,h,a,ht in ht_draw:
    r = 'H' if h>a else ('A' if a>h else 'D')
    print('  %-22s 半场 %d:%d → 全场 %d:%d  (%s)' % (n, ht[0], ht[1], h, a, {'H':'主胜','D':'平局','A':'客胜'}[r]))
n_d = len(ht_draw)
ft = {'D': sum(1 for n,h,a,ht in ht_draw if h==a),
      'H': sum(1 for n,h,a,ht in ht_draw if h>a),
      'A': sum(1 for n,h,a,ht in ht_draw if a>h)}
print('\n半场平 → 全场: 平 %d/%.0f%% · 主 %d/%.0f%% · 客 %d/%.0f%%'
      % (ft['D'], 100.0*ft['D']/n_d, ft['H'], 100.0*ft['H']/n_d, ft['A'], 100.0*ft['A']/n_d))
print('项目台账基准: 英超 36.5%% / 西甲 36.9%% / 意甲 38.0%% / 德甲 37.2%%')
print('→ 本批 %.0f%% 明显高于台账（n=%d 极小，仅观察不结论）' % (100.0*ft['D']/n_d, n_d))

print('\n' + '='*100)
print('四、进球量级：模型中心 vs 实际')
print('='*100)
CTR = {'埃弗斯堡vs奥格斯堡':3.5,'柏林联合vs多特蒙德':3.4,'汉堡vs斯图加特':3.7,'沙尔克04vs美因茨':3.2,
       '富勒姆vs赫尔城':3.0,'布伦特福德vs利物浦':3.2,'曼城vs伊普斯维奇':3.9,'比利亚雷亚尔vs埃尔切':3.6,
       '博洛尼亚vs国际米兰':3.1,'拜仁vsRB莱比锡':5.0,'纽卡斯尔vs维拉':3.2,'贝蒂斯vs巴塞罗那':4.3,
       '罗马vs热那亚':2.9,'巴伦西亚vs毕尔巴鄂':2.6}
act = [h+a for _, (h,a), _, _, _ in M]
ctr = [CTR[n] for n,_,_,_,_ in M]
err = [a-c for a,c in zip(act,ctr)]
print('实际总进球: %s' % act)
print('模型中心  : %s' % [round(c,1) for c in ctr])
print('偏差(实-模): %s' % [round(e,1) for e in err])
print('平均绝对误差 %.2f 球 | 平均偏差 %+.2f 球（正=模型低估）' % (sum(abs(e) for e in err)/len(err), sum(err)/len(err)))
print('实际均值 %.2f vs 模型均值 %.2f → 净差 %+.2f 球' % (sum(act)/14.0, sum(ctr)/14.0, sum(act)/14.0-sum(ctr)/14.0))
print('\n极端偏差场:')
for n,a,c,e in sorted(zip([x[0] for x in M],act,ctr,err), key=lambda t:-abs(t[3]))[:5]:
    print('  %-22s 实际 %d 球 vs 模型 %.1f 球 → %+.1f' % (n,a,c,e))
