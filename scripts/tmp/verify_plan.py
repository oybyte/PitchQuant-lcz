# -*- coding: utf-8 -*-
"""verify_plan.py — 核对整改方案里每个数字"""
import json, os, sys
from collections import Counter
sys.stdout.reconfigure(encoding='utf-8')
R = r'E:\footbal-github\PitchQuant\data\tmp'
bad = []
seen = {}
for b in ('batch_203','batch_140','batch_74','batch_2_5_8'):
    p = os.path.join(R,b,'result_compare.json')
    if not os.path.exists(p): continue
    for r in json.load(open(p,encoding='utf-8')): seen[r['slug']]=r
rows=list(seen.values())
def ck(l,c,g):
    print(('OK  ' if c else 'FAIL')+' %-40s %s'%(l,g))
    if not c: bad.append(l)

ck('去重后 435 场', len(rows)==435, len(rows))
big=[r for r in rows if r.get('ou_dir')=='大球']; sm=[r for r in rows if r.get('ou_dir')=='小球']
hb=sum(1 for r in big if r.get('hit_ou')); hs=sum(1 for r in sm if r.get('hit_ou'))
ck('判大球 232/159 = 68.5%', (len(big),hb)==(232,159), '%d/%d=%.1f%%'%(len(big),hb,100.0*hb/len(big)))
ck('判小球 70/36 = 51.4%', (len(sm),hs)==(70,36), '%d/%d=%.1f%%'%(len(sm),hs,100.0*hs/len(sm)))
for b,exp_n,exp_h in (('batch_203',102,72),('batch_140',78,55),('batch_74',38,23),('batch_2_5_8',17,11)):
    g=[r for r in json.load(open(os.path.join(R,b,'result_compare.json'),encoding='utf-8')) if r.get('ou_dir')=='大球']
    ck('%s 大球 %d/%d'%(b,exp_n,exp_h), (len(g),sum(1 for r in g if r.get('hit_ou')))==(exp_n,exp_h),
       '%d/%d'%(len(g),sum(1 for r in g if r.get('hit_ou'))))

# 0球分离度
lo=[r for r in rows if r.get('o25') and r['o25']<1.70]
hi=[r for r in rows if r.get('o25') and r['o25']>2.10]
zl=100.0*sum(1 for r in lo if r['tot']==0)/len(lo); zh=100.0*sum(1 for r in hi if r['tot']==0)/len(hi)
ck('大球强档 0球率 2.1%', abs(zl-2.1)<0.15, '%.1f%%'%zl)
ck('小球档 0球率 9.1%', abs(zh-9.1)<0.15, '%.1f%%'%zh)
ck('差 +7.0pp', abs((zh-zl)-7.0)<0.3, '%.1fpp'%(zh-zl))
z0=sum(1 for r in rows if r['tot']==0)
ck('全样本 0球 24/435 = 5.5%', z0==24, '%d/%d=%.1f%%'%(z0,len(rows),100.0*z0/len(rows)))

# 档位下限 A/B
def tot(s):
    try:
        h,a=map(int,s.split(':')); return h+a
    except: return None
gA=sum(1 for r in rows if tot(r['a1']) is not None and tot(r['a1'])==tot(r['score']))
gB=0
for r in rows:
    o=r['o25']; need=3 if o<1.70 else (2 if o<1.90 else 0)
    cand=[c for c in [r['a1'],r['a2'],r.get('a3')] if c and tot(c) is not None]
    pick=next((c for c in cand if tot(c)>=need), cand[0] if cand else None)
    if pick and tot(pick)==tot(r['score']): gB+=1
ck('照搬Top1 86/435 = 19.8%', gA==86, '%d/%d=%.1f%%'%(gA,len(rows),100.0*gA/len(rows)))
ck('抬高后 85/435 = 19.5%', gB==85, '%d/%d=%.1f%%'%(gB,len(rows),100.0*gB/len(rows)))
ck('档位规则差 -1 场', gB-gA==-1, gB-gA)

# 分档 n 与 Top1 满足率
for lo_,hi_,need,exp_n in ((1.00,1.70,3,188),(1.70,1.90,2,128)):
    g=[r for r in rows if lo_<=r['o25']<hi_]
    ok=sum(1 for r in g if tot(r['a1']) is not None and tot(r['a1'])>=need)
    ck('档 %.2f-%.2f n=%d'%(lo_,hi_,exp_n), len(g)==exp_n, len(g))
    ck('  该档 Top1 满足>=%d: %d/%d'%(need,ok,len(g)), True, '%d/%d=%.0f%%'%(ok,len(g),100.0*ok/len(g)))

# 每档 0球/1球表
BANDS=[(1.30,1.50),(1.50,1.70),(1.70,1.90),(1.90,2.10),(2.10,2.30),(2.30,2.60)]
exp={1.30:(22,0.0,9.1),1.50:(156,2.6,11.5),1.70:(128,7.0,14.1),1.90:(64,9.4,15.6),2.10:(41,7.3,14.6),2.30:(14,14.3,21.4)}
for lo_ in (1.30,1.50,1.70,1.90,2.10,2.30):
    g=[r for r in rows if lo_<=r['o25']<lo_+0.2]
    n=len(g); z=100.0*sum(1 for r in g if r['tot']==0)/n; o=100.0*sum(1 for r in g if r['tot']==1)/n
    e=exp[lo_]
    ck('档 %.2f: n=%d 0球%.1f%% 1球%.1f%%'%(lo_,e[0],e[1],e[2]), n==e[0] and abs(z-e[1])<0.15 and abs(o-e[2])<0.15,
       '%d %.1f%% %.1f%%'%(n,z,o))

# goal_bins 表确实无 g0
gb=json.load(open(os.path.join(R,'goal_bins_table.json'),encoding='utf-8'))
k0=list(gb)[0]
ck('goal_bins 表字段无 g0', 'g0' not in gb[k0] and 'g01' in gb[k0], sorted(gb[k0].keys()))
ck('goal_bins 无 prob_0 字段', all('prob_0' not in json.dumps(v) for v in gb.values()), 'ok')

print('\n'+('✅ 整改方案全部数字复核通过' if not bad else '❌ '+'; '.join(bad)))
