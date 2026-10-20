# -*- coding: utf-8 -*-
"""review_1020.py — 10-20 八场复盘（口径严格按 AGENTS §6）
   direction_hit_top1: 仅第一推荐
   direction_hit_any : 含并列（主口径）
   比分: 仅主锚+次锚
   大小球: 相对 2.5 固定线
   基线对照: 永远押主胜 / 永远押大 / 模型反向
"""
import os, re, sys, json
sys.stdout.reconfigure(encoding='utf-8')
OUT='data/tmp/batch_1020/out'

# 用户给定赛果（主,客）
TRUTH = {
 '00_30_意甲_蒙扎_vs_卡利亚里': (4,0),
 '01_00_瑞典超_代格福什_vs_卡尔马': (1,2),
 '02_45_意甲_帕尔马_vs_都灵': (0,3),
 '02_45_法乙_罗德兹_vs_蒙彼利埃': (0,3),
 '03_00_英超_托特纳姆热刺_vs_考文垂': (3,1),
 '03_00_西甲_赫塔菲_vs_巴列卡诺': (1,1),
 '03_15_葡超_布拉加_vs_吉维森特': (1,2),
 '07_00_巴西甲_科林蒂安_vs_维多利亚': (1,1),
}
def actual(hg,ag):
    return '主胜' if hg>ag else ('平局' if hg==ag else '客胜')

rows=[]
for key,(hg,ag) in TRUTH.items():
    p=os.path.join(OUT,'10-20_'+key+'.txt')
    if not os.path.exists(p): print('缺文件:',key); continue
    t=open(p,encoding='utf-8').read()
    def g(pat,grp=1,d='—'):
        m=re.search(pat,t); return m.group(grp).strip() if m else d
    imp=re.search(r'隐含: 主([0-9.]+)%/平([0-9.]+)%/客([0-9.]+)%',t)
    pr=[float(x) for x in imp.groups()] if imp else [0,0,0]
    LAB=['主胜','平局','客胜']
    fav=LAB[pr.index(max(pr))]
    model=g(r'方向\(欧亚综合\): (\S+?)\(',1)
    conf=g(r'方向\(欧亚综合\): \S+?\((\w+)\)',1)
    par=g(r'并列:(\S+?) \|',1)
    skew=int(g(r'skew精确计算\(未校准\): [0-9.]+/[0-9.]+ = (\d+)%',1,'0') or 0)
    weak='🔴🔴弱共识场' in t
    # 🔴锚真源: 「现场比分引擎」段的主锚建议/次锚建议
    #   （C21 为 N/A——缺 CS 比分盘；锚另有 live_score_engine 来源）
    anchor=g(r'主锚建议:\s*(\d+:\d+)',1,None)
    second=g(r'次锚建议:\s*(\d+:\d+)',1,None)
    ou=g(r'大小球判向: \*\*(\S+?)\*\*',1,None)
    net=g(r'市场净胜期望档: (\S+)',1,None)
    act=actual(hg,ag); tot=hg+ag
    rows.append(dict(key=key,skew=skew,weak=weak,fav=fav,model=model,conf=conf,par=par,
                     anchor=anchor,second=second,ou=ou,net=net,
                     hg=hg,ag=ag,act=act,tot=tot,score='%d:%d'%(hg,ag)))

print('='*100)
print('10-20 八场复盘（口径: AGENTS §6 · 全 8 场数据为 STALE 非临场·V6 硬门拒绝）')
print('='*100)
hdr='%-30s %-5s %-4s %-5s %-6s %-4s %-4s %-7s %-6s %-7s' % (
    '场次','skew','弱?','模型','并列','实际','top1','any','大小球','比分')
print(hdr); print('-'*100)
t1=a1=0
ou_n=ou_hit=0
score_hit=0
for r in rows:
    ok1 = (r['model']==r['act'])
    okany = ok1 or (r['par']=='yes' and r['act']=='平局')
    t1+=ok1; a1+=okany
    # 比分：仅主锚+次锚
    sc = (r['score'] in [r['anchor'],r['second']] and r['anchor'] is not None)
    if sc: score_hit+=1
    # 大小球（仅判向场次）
    ous='—'
    if r['ou'] and r['ou']!='中性·不判':
        ou_n+=1
        hi = (r['ou']=='大球' and r['tot']>2.5) or (r['ou']=='小球' and r['tot']<2.5)
        ou_hit+=hi
        ous=('%s%s'%(r['ou'],'✅' if hi else '❌'))
    print('%-30s %-5d %-4s %-5s %-6s %-4s %-4s %-7s %-6s %-7s' % (
        r['key'].replace('_',' ')[:30], r['skew'], '是' if r['weak'] else '否',
        r['model'], r['par'], r['act'], '✅' if ok1 else '❌', '✅' if okany else '❌',
        ous, ('✅%s'%r['score']) if sc else '❌%s'%r['score']))

n=len(rows)
print()
print('='*100)
print('命中统计（n=%d）' % n)
print('='*100)
print('  方向 top1（仅第一推荐）    %d/%d = %.1f%%' % (t1,n,100*t1/n))
print('  方向 any （含并列·主口径）  %d/%d = %.1f%%' % (a1,n,100*a1/n))
if ou_n: print('  大小球（仅判向场次）        %d/%d = %.1f%%' % (ou_hit,ou_n,100*ou_hit/ou_n))
print('  比分（仅主锚+次锚）        %d/%d = %.1f%%' % (score_hit,n,100*score_hit/n))
print()
print('=== 基线对照（AGENTS §6 必做）===')
home=sum(1 for r in rows if r['act']=='主胜')
draw=sum(1 for r in rows if r['act']=='平局')
away=sum(1 for r in rows if r['act']=='客胜')
over=sum(1 for r in rows if r['tot']>2.5)
fav=sum(1 for r in rows if r['fav']==r['act'])
print('  永远押主胜      %d/%d = %.1f%%' % (home,n,100*home/n))
print('  永远押客胜      %d/%d = %.1f%%' % (away,n,100*away/n))
print('  永远押平局      %d/%d = %.1f%%' % (draw,n,100*draw/n))
print('  市场热门        %d/%d = %.1f%%' % (fav,n,100*fav/n))
print('  永远押大球      %d/%d = %.1f%%' % (over,n,100*over/n))
rev=sum(1 for r in rows if r['model'] and r['model']!=r['act'])
print('  模型反向        %d/%d = %.1f%%  (反向=押非模型方向中隐含最高者·此处仅计数) ' % (rev,n,100*rev/n))
print()
w=[r for r in rows if r['weak']]
print('=== 弱共识场专项（修复验证·样本外）===')
print('  本批弱共识场 n=%d' % len(w))
for r in w:
    ok1=(r['model']==r['act']); okany=ok1 or (r['par']=='yes' and r['act']=='平局')
    print('    %-26s skew=%-4d 模型=%-4s 并列=%-4s 实际=%-4s top1=%s any=%s' % (
        r['key'].replace('_',' ')[:26], r['skew'], r['model'], r['par'], r['act'],
        '✅' if ok1 else '❌', '✅' if okany else '❌'))
wt1=sum(1 for r in w if r['model']==r['act'])
wany=sum(1 for r in w if r['model']==r['act'] or (r['par']=='yes' and r['act']=='平局'))
print('    弱共识: top1 %d/%d=%.1f%%  any %d/%d=%.1f%%' % (
    wt1,len(w),100*wt1/max(len(w),1), wany,len(w),100*wany/max(len(w),1)))
print()
print('  🔴 修复价值: 若未修复(弱共识不并列), any 口径将=top1口径')
print('     修复后 any=%d ｜ 修复前(模拟)=%d  → 多命中 %d 场' % (a1, t1, a1-t1))
json.dump(rows, open('data/tmp/_review1020.json','w',encoding='utf-8'), ensure_ascii=False, indent=1)
