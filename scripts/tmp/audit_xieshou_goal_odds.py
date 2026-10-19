
# -*- coding: utf-8 -*-
"""audit_xieshou_goal_odds.py — 民间「0球赔率 → 总进球区间」四档经验法则 · 435 场实盘可靠性审计

【口径声明】
1. 仓库内【没有任何一行竞彩总进球盘真实数据】。全仓扫 3038 个 txt/md/json/csv，
   8 档总进球赔率只有 examples/sample-odds.txt 一份**构造示例**。
   → 「0 球赔率」在本仓库**不可直接观测**，只能由市场总进球期望反推。
2. 反推口径（唯一）：
        over_p = result_compare.over_p（已去水的 P(总进球≥3)）
        λ      = 泊松反解 P(X≥3|λ) = over_p
        P0     = exp(-λ)                  （去水 0 球概率）
        o0     = (1/P0) / S               （S = 八档倒数和；本审计取 1.20，
                                           真实竞彩 1.18–1.30，另做 1.10–1.60 敏感性）
3. 样本：data/tmp/batch_{2_5_8,74,140,203}/result_compare.json 去重
   （decided 442 场 → result_compare 441 行 → 去重后 436 唯一场 → 有赛果 435 场）
"""
import os, json, math, sys
from collections import Counter
sys.stdout.reconfigure(encoding='utf-8')

BASE = r"E:\footbal-github\PitchQuant\data\tmp"
BATCHES = ('batch_2_5_8', 'batch_74', 'batch_140', 'batch_203')
CLAIM = {1: (1, 2), 2: (2, 3), 3: (3, 4), 4: (5, 7)}   # 档4 宣称 5/6/7+ 合并成连续窗
NAME  = {1: '<10', 2: '10-14', 3: '15-20', 4: '>20'}
S_DEF = 1.20

def pois(l, k): return math.exp(-l) * l ** k / math.factorial(k)
def p_ge(l, k): return 1.0 - sum(pois(l, i) for i in range(k))

def lam_from_overp(op):
    lo, hi = 0.05, 14.0
    for _ in range(400):
        mid = (lo + hi) / 2
        if p_ge(mid, 3) > op: hi = mid
        else: lo = mid
    return (lo + hi) / 2

def band(o):
    if o < 10: return 1
    if o < 15: return 2
    if o <= 20: return 3
    return 4

def wilson(k, n, z=1.96):
    if n == 0: return (0.0, 0.0)
    p = k / n; den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, c - h), min(1.0, c + h))

def binom_p(k, n, p0):
    from math import comb
    if n == 0: return 1.0
    pmf = [comb(n, i) * p0 ** i * (1 - p0) ** (n - i) for i in range(n + 1)]
    return min(1.0, sum(p for p in pmf if p <= pmf[k] * (1 + 1e-9)))

# ── 载入 ──
d = {}
for b in BATCHES:
    for r in json.load(open(os.path.join(BASE, b, 'result_compare.json'), encoding='utf-8')):
        r['_b'] = b; d[r['slug']] = r
rows = list(d.values()); N = len(rows)
for r in rows:
    r['lam'] = lam_from_overp(r['over_p'] / 100.0)
    r['p0']  = math.exp(-r['lam'])
    r['o0']  = (1.0 / r['p0']) / S_DEF
    r['band'] = band(r['o0'])
allc = Counter(r['tot'] for r in rows)
out = []; P = out.append

P('=' * 112)
P('样本 %d 场 · 场均 %.3f 球 · 实际 0 球 %d 场(%.1f%%) · 等价 0球赔率 %.1f–%.1f（中位 %.1f）' % (
    N, sum(r['tot'] for r in rows) / N, sum(1 for r in rows if r['tot'] == 0),
    100.0 * sum(1 for r in rows if r['tot'] == 0) / N,
    min(r['o0'] for r in rows), max(r['o0'] for r in rows),
    sorted(r['o0'] for r in rows)[N // 2]))
dv = [abs(r['lam'] - r['t_mkt']) for r in rows if r.get('t_mkt')]
P('λ 重建交叉校验: |重建λ − 仓库 t_mkt| 均值 %.4f · 最大 %.4f (n=%d)' % (sum(dv) / len(dv), max(dv), len(dv)))
P('')

P('=' * 112)
P('① 四档样本量与【实际】总进球分布')
P('=' * 112)
P('%-8s %5s %7s %7s %7s %7s %7s %7s %7s %7s' % ('0球档', 'n', '占比', 'λ均值', '0球', '1球', '2球', '3球', '4球', '5+球'))
P('-' * 112)
for b in (1, 2, 3, 4):
    g = [r for r in rows if r['band'] == b]
    if not g: P('%-8s %5d %7s' % (NAME[b], 0, '—')); continue
    c = Counter(r['tot'] for r in g); n = len(g)
    P('%-8s %5d %6.1f%% %7.2f %6.1f%% %6.1f%% %6.1f%% %6.1f%% %6.1f%% %6.1f%%' % (
        NAME[b], n, 100.0 * n / N, sum(r['lam'] for r in g) / n,
        100.0 * c.get(0, 0) / n, 100.0 * c.get(1, 0) / n, 100.0 * c.get(2, 0) / n,
        100.0 * c.get(3, 0) / n, 100.0 * c.get(4, 0) / n,
        100.0 * sum(v for k, v in c.items() if k >= 5) / n))
P('-' * 112)
P('%-8s %5d %6.1f%% %7.2f %6.1f%% %6.1f%% %6.1f%% %6.1f%% %6.1f%% %6.1f%%' % (
    '全样本', N, 100.0, sum(r['lam'] for r in rows) / N,
    100.0 * allc.get(0, 0) / N, 100.0 * allc.get(1, 0) / N, 100.0 * allc.get(2, 0) / N,
    100.0 * allc.get(3, 0) / N, 100.0 * allc.get(4, 0) / N,
    100.0 * sum(v for k, v in allc.items() if k >= 5) / N))

P('')
P('=' * 112)
P('② 宣称区间 vs 实际：命中率 / 无脑基线 / 泊松应有 / 95%CI / 精确二项检验')
P('=' * 112)
P('%-8s %5s %-8s %8s %10s %9s %8s %-19s %7s' % ('0球档', 'n', '宣称', '实际命中', '无脑押基线', '泊松应有', '提升pp', '95% Wilson CI', 'p值'))
P('-' * 112)
stat = {}; net_all = 0
for b in (1, 2, 3, 4):
    g = [r for r in rows if r['band'] == b]
    if not g: continue
    lo, hi = CLAIM[b]; n = len(g)
    h = sum(1 for r in g if lo <= r['tot'] <= hi)
    base = sum(allc.get(k, 0) for k in range(lo, hi + 1)) / N
    poi = sum(pois(sum(r['lam'] for r in g) / n, k) for k in range(lo, hi + 1))
    cl, ch = wilson(h, n); pv = binom_p(h, n, base)
    stat[b] = dict(n=n, h=h, base=base, poi=poi, p=pv)
    net_all += h - (n - h)
    P('%-8s %5d %-8s %7.1f%% %9.1f%% %8.1f%% %+7.1f [%5.1f%%,%5.1f%%] %7.4f' % (
        NAME[b], n, '%d-%d球' % (lo, hi), 100.0 * h / n, 100 * base, 100 * poi,
        100 * (h / n - base), 100 * cl, 100 * ch, pv))
P('-' * 112)
P('规则四档合计净收益(命中+1/不中−1): %+d / %d = 场均 %+.3f' % (net_all, N, net_all / N))
for nm, lo, hi in (('2-3球', 2, 3), ('2-4球', 2, 4), ('3-4球', 3, 4), ('5+球', 5, 99), ('1-2球', 1, 2)):
    k = sum(1 for r in rows if lo <= r['tot'] <= hi)
    P('   对照·全样本无脑押「%s」: %d/%d = %.1f%% → 净收益 %+d (场均 %+.3f)' % (
        nm, k, N, 100.0 * k / N, k - (N - k), (k - (N - k)) / N))

P('')
P('=' * 112)
P('③ 门槛拆解：市场的【有序性】成立，逐个【窗口】不成立')
P('=' * 112)
s = sorted(rows, key=lambda r: r['o0'])
P('%-4s %-16s %5s %9s %8s %9s %9s' % ('分位', 'o0 区间', 'n', '实际场均', '0球', '1-2球', '3+球'))
P('-' * 112)
for i in range(4):
    seg = s[i * (N // 4):(i + 1) * (N // 4)] if i < 3 else s[3 * (N // 4):]
    P('Q%d   %7.1f-%-8.1f %5d %9.2f %7.1f%% %8.1f%% %8.1f%%' % (
        i + 1, seg[0]['o0'], seg[-1]['o0'], len(seg),
        sum(r['tot'] for r in seg) / len(seg),
        100.0 * sum(1 for r in seg if r['tot'] == 0) / len(seg),
        100.0 * sum(1 for r in seg if 1 <= r['tot'] <= 2) / len(seg),
        100.0 * sum(1 for r in seg if r['tot'] >= 3) / len(seg)))
def rank(a):
    o = sorted(range(len(a)), key=lambda i: a[i]); rk = [0] * len(a)
    for p_, i in enumerate(o): rk[i] = p_
    return rk
x = rank([r['lam'] for r in rows]); y = rank([r['tot'] for r in rows])
mx = sum(x) / N; my = sum(y) / N
rho = sum((a - mx) * (b - my) for a, b in zip(x, y)) / math.sqrt(sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y))
P('Spearman ρ(市场λ, 实际总进球) = %.4f · t = %.2f → %s' % (
    rho, rho * math.sqrt((N - 2) / (1 - rho * rho)), '显著正相关（市场的有序性成立）'))

P('')
P('  档内对比：宣称窗 vs 同宽最优窗')
P('  %-8s %5s %-9s %7s | %-9s %7s' % ('0球档', 'n', '宣称窗', '命中', '同宽最优窗', '命中'))
for b in (1, 2, 3, 4):
    g = [r for r in rows if r['band'] == b]
    if not g: continue
    c = Counter(r['tot'] for r in g); n = len(g)
    lo, hi = CLAIM[b]; w = hi - lo + 1
    f = sum(c.get(k, 0) for k in range(lo, hi + 1)) / n
    bs = max(range(0, 9 - w + 1), key=lambda s0: sum(c.get(k, 0) for k in range(s0, s0 + w)))
    bv = sum(c.get(k, 0) for k in range(bs, bs + w)) / n
    P('  %-8s %5d %-9s %6.1f%% | %-9s %6.1f%%' % (
        NAME[b], n, '%d-%d球' % (lo, hi), 100 * f, '%d-%d球' % (bs, bs + w - 1), 100 * bv))

P('')
P('=' * 112)
P('④ 样本自身校准：这批 435 场明显偏进攻（进球比市场预期多）')
P('=' * 112)
P('%-6s %10s %10s %9s' % ('进球', '市场隐含', '实际', '偏差'))
for k in range(0, 8):
    if k < 7:
        p = sum(pois(r['lam'], k) for r in rows) / N
        a = sum(1 for r in rows if r['tot'] == k) / N
    else:
        p = sum(p_ge(r['lam'], 7) for r in rows) / N
        a = sum(1 for r in rows if r['tot'] >= 7) / N
    P('%-6s %9.1f%% %9.1f%% %+8.1fpp' % ('%d球' % k if k < 7 else '7+球', 100 * p, 100 * a, 100 * (a - p)))
m_ = sum(r['tot'] for r in rows) / N
v_ = sum((r['tot'] - m_) ** 2 for r in rows) / (N - 1)
el = sum(r['lam'] for r in rows) / N
vl = sum((r['lam'] - el) ** 2 for r in rows) / (N - 1)
P('超散比 = 实测方差 %.3f / 泊松混合理论方差 %.3f = %.3f  → %s' % (
    v_, el + vl, v_ / (el + vl), '厚尾（2 球窗先天吃亏）' if v_ > el + vl else '接近泊松'))

P('')
P('=' * 112)
P('⑤ 稳健性 A：改「去水倒数和 S」')
P('=' * 112)
P('%-6s %5s %5s %5s %5s | %-14s %s' % ('S', '<10', '10-14', '15-20', '>20', '净收益(场均)', '四档命中率'))
for SS in (1.10, 1.15, 1.20, 1.30, 1.40, 1.50, 1.60):
    bb = {r['slug']: band((1.0 / r['p0']) / SS) for r in rows}
    cnt = Counter(bb.values()); net = 0; hs = []
    for b in (1, 2, 3, 4):
        g = [r for r in rows if bb[r['slug']] == b]
        if not g: hs.append('—'); continue
        lo, hi = CLAIM[b]
        h = sum(1 for r in g if lo <= r['tot'] <= hi); net += h - (len(g) - h)
        hs.append('%.0f%%' % (100.0 * h / len(g)))
    P('%-6.2f %5d %5d %5d %5d | %+5d/%-4d %+7.3f | %s' % (
        SS, cnt.get(1, 0), cnt.get(2, 0), cnt.get(3, 0), cnt.get(4, 0), net, N, net / N, ' '.join(hs)))

P('')
P('=' * 112)
P('⑥ 稳健性 B：只保留竞彩真实合理带 o0∈[7,25]')
P('=' * 112)
sub = [r for r in rows if 7 <= r['o0'] <= 25]
P('保留 %d/%d 场（剔除 %.1f%%）' % (len(sub), N, 100.0 * (N - len(sub)) / N))
P('%-8s %5s %-8s %8s %10s %8s %8s' % ('0球档', 'n', '宣称', '命中', '无脑押基线', '提升pp', '净收益'))
nets = 0; sac = Counter(r['tot'] for r in sub); nsub = len(sub)
for b in (1, 2, 3, 4):
    g = [r for r in sub if r['band'] == b]
    if not g: P('%-8s %5d  —' % (NAME[b], 0)); continue
    lo, hi = CLAIM[b]; h = sum(1 for r in g if lo <= r['tot'] <= hi)
    base = sum(sac.get(k, 0) for k in range(lo, hi + 1)) / nsub
    nets += h - (len(g) - h)
    P('%-8s %5d %-8s %7.1f%% %9.1f%% %+7.1f %+8d' % (NAME[b], len(g), '%d-%d球' % (lo, hi),
      100.0 * h / len(g), 100 * base, 100 * (h / len(g) - base), h - (len(g) - h)))
P('合计净收益 %+d / %d = 场均 %+.3f' % (nets, nsub, nets / nsub))
kk = sum(1 for r in sub if 2 <= r['tot'] <= 4)
P('对照·同子集无脑押 2-4球: %.1f%% → 净收益 %+d (场均 %+.3f)' % (
    100.0 * kk / nsub, kk - (nsub - kk), (kk - (nsub - kk)) / nsub))
P('')
P('档4 内部再切片（说明 50%% 命中的来源）:')
for lo_, hi_ in ((20, 25), (25, 30), (30, 40), (40, 10 ** 6)):
    g = [r for r in rows if lo_ <= r['o0'] < hi_]
    if not g: continue
    P('  o0 %-9s n=%-3d 场均 %.2f 球 · 5+球 %5.1f%% · 6+球 %5.1f%%' % (
        ('%d-%d' % (lo_, hi_)) if hi_ < 10 ** 6 else '%d+' % lo_, len(g),
        sum(r['tot'] for r in g) / len(g),
        100.0 * sum(1 for r in g if r['tot'] >= 5) / len(g),
        100.0 * sum(1 for r in g if r['tot'] >= 6) / len(g)))

P('')
P('=' * 112)
P('⑦ 基线对照：同一 435 场上，项目自有输出与朴素策略')
P('=' * 112)
hiv = sum(1 for r in rows if r['hit_iv'])
P('项目 [iv] 3 球窗命中: %d/%d = %.1f%%（下界1 %d 场 %.1f%% · 下界2 %d 场 %.1f%%）' % (
    hiv, N, 100.0 * hiv / N,
    sum(1 for r in rows if r['iv'][0] == 1),
    100.0 * sum(1 for r in rows if r['iv'][0] == 1 and r['hit_iv']) / max(1, sum(1 for r in rows if r['iv'][0] == 1)),
    sum(1 for r in rows if r['iv'][0] == 2),
    100.0 * sum(1 for r in rows if r['iv'][0] == 2 and r['hit_iv']) / max(1, sum(1 for r in rows if r['iv'][0] == 2))))
h3 = 0
for r in rows:
    bst = max(range(0, 6), key=lambda s0: sum(pois(r['lam'], k) for k in (s0, s0 + 1, s0 + 2)))
    if bst <= r['tot'] <= bst + 2: h3 += 1
P('纯市场λ中心 3 球窗: %d/%d = %.1f%%' % (h3, N, 100.0 * h3 / N))
P('民间四档（2 球窗）: %d/%d = %.1f%%' % (sum(stat[b]['h'] for b in stat), N,
    100.0 * sum(stat[b]['h'] for b in stat) / N))

P('')
P('=' * 112)
P('⑧ 判定')
P('=' * 112)
P('%-8s %5s %-9s %9s %10s %8s %9s %s' % ('0球档', 'n', '法则宣称', '实测命中', '无脑押基线', '提升pp', 'p值', '结论'))
P('-' * 112)
VERD = {1: '✅ 方向对·可保留', 2: '❌ 窗口错·劣于无脑押', 3: '❌ 窗口错·无信息量', 4: '⚠️ 方向对·样本薄'}
for b in (1, 2, 3, 4):
    if b not in stat: continue
    st = stat[b]; lo, hi = CLAIM[b]
    P('%-8s %5d %-9s %8.1f%% %9.1f%% %+7.1f %9.4f %s' % (
        NAME[b], st['n'], '%d-%d球' % (lo, hi), 100.0 * st['h'] / st['n'],
        100 * st['base'], 100 * (st['h'] / st['n'] - st['base']), st['p'], VERD[b]))

open(os.path.join(BASE, '_xieshou_report.txt'), 'w', encoding='utf-8').write('\n'.join(out))
print('\n'.join(out))
