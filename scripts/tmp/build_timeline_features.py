# -*- coding: utf-8 -*-
"""build_timeline_features.py — 从 2.5.9 output 的 ingest txt 抽「详细时序形态」特征
   🔴 与 sim_features 同一口径族：level / drift / shape / asian / total
   但数据源是 2.5.9 output（澳门逐点时序），比盲测批更丰富"""
import json, os, re, sys
sys.stdout.reconfigure(encoding='utf-8')
D = r'data/tmp/batch_output'
OUTP = os.path.join(D, 'out')

def devig(o):
    try:
        o=[float(x) for x in o]
        if min(o)<=1: return None
        inv=[1/x for x in o]; s=sum(inv)
        return [x/s for x in inv]
    except Exception: return None

def parse_series(t):
    i = t.find('【胜平负固定奖金】')
    if i < 0: return []
    seg = t[i:]
    j = seg.find('【让球')
    if j > 0: seg = seg[:j]
    rows=[]
    for x in seg.split(chr(10)):
        m = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),(\S+),(\S+),(\S+)', x.strip())
        if m:
            try: rows.append((m.group(1), [float(m.group(2)), float(m.group(3)), float(m.group(4))]))
            except ValueError: pass
    return rows

def parse_asian(t):
    m = re.search(r'澳门亚盘时序\((\d+) 点\)：(.*?)(?:\n\S|\Z)', t, re.S)
    if not m: return []
    rows=[]
    for x in m.group(2).split(chr(10)):
        mm = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) 亚盘 (\S+) / (\S+) / (\S+)', x.strip())
        if mm:
            try: rows.append((mm.group(1), mm.group(2), mm.group(3), mm.group(4)))
            except Exception: pass
    return rows

def line_val(s):
    s=str(s).strip()
    if '/' in s:
        a,b=s.split('/')[:2]
        try: return (float(a)+float(b))/2
        except ValueError: return None
    try: return float(s)
    except ValueError: return None

def feats(t):
    eu = parse_series(t)
    F = {}
    seq = []
    for ts, o in eu:
        p = devig(o)
        if p: seq.append(p)
    if len(seq) >= 2:
        first, last = seq[0], seq[-1]
        F['dr_h'] = (last[0]-first[0])*100
        F['dr_d'] = (last[1]-first[1])*100
        F['dr_a'] = (last[2]-first[2])*100
        F['npts'] = len(seq)
        # 形态
        diffs = [seq[i+1][0]-seq[i][0] for i in range(len(seq)-1)]
        absd = [abs(d) for d in diffs]; tot = sum(absd)
        if tot > 1e-9:
            F['eff_h'] = (last[0]-first[0])/tot*100
            F['rev_h'] = float(sum(1 for i in range(1,len(diffs)) if diffs[i]*diffs[i-1] < -1e-12))
        vals = [s[0] for s in seq]
        mean = sum(vals)/len(vals)
        F['vol_h'] = (sum((x-mean)**2 for x in vals)/len(vals))**0.5*100
        F['rng_h'] = (max(vals)-min(vals))*100
    if seq:
        F['lvl_h'], F['lvl_d'], F['lvl_a'] = [x*100 for x in seq[-1]]
        srt = sorted(seq[-1], reverse=True)
        F['skew'] = srt[0]/srt[1]*100 if srt[1] > 0 else 999
        F['dir'] = float(seq[-1].index(max(seq[-1])))
    # 亚盘
    ah = parse_asian(t)
    lines = [line_val(x[2]) for x in ah]
    lines = [x for x in lines if x is not None]
    if len(lines) >= 2:
        F['ah_move'] = lines[-1]-lines[0]
        F['ah_moves'] = float(sum(1 for i in range(1,len(lines)) if lines[i]!=lines[i-1]))
    # S4
    m = re.search(r'强度档=(\w+)', t)
    if m: F['s4tier'] = m.group(1)
    return F

truth = json.load(open(os.path.join(D,'_truth.json'), encoding='utf-8'))
recs = []
for f in sorted(os.listdir(D)):
    if not f.endswith('.txt') or 'vs' not in f: continue
    key = f[:-4]
    t = open(os.path.join(D, f), encoding='utf-8').read()
    F = feats(t)
    if 'lvl_h' not in F: continue
    # 真值
    tr = None
    for k, v in truth.items():
        if k.replace(' ','_').replace('(','').replace(')','') == key: tr = v; break
    if not tr: continue
    recs.append(dict(key=key, truth=tr['act'], tot=tr['tot'], F=F))
json.dump(recs, open(os.path.join(D,'_tlfeat.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
from collections import Counter
print('样本', len(recs))
print('方向', dict(Counter(r['truth'] for r in recs)))
print('特征维度均值 %.1f' % (sum(len(r['F']) for r in recs)/len(recs)))
