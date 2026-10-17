# -*- coding: utf-8 -*-
"""calc_homeaway.py — HAF 主客场因子层·数据层（V3.5.73·2026-08-25·用户指令）
每队×场地子集统计（近5年·五大联赛）+ 主客场增益/衰减系数 → data/tmp/homeaway_table.json
🔴硬性约束: 只用对应场地子集·不混主场/客场·样本不足(n<15)标注风险·不合并取平均

🔴2026-10-17 重构(P2-2): 拆成「建表」与「查表耦合」两个可导入部分。
   原实现把读 Matches.csv 写在模块顶层 → 公开版（未分发 Matches.csv）**连
   「用已发布的 homeaway_table.json 查两队耦合」都做不到**（一 import 就 FileNotFoundError）。
   现: ① 建表逻辑放 _build_table()，只在 __main__ 且有 CSV 时执行
       ② 查表耦合 haf_couple()/haf_couple_checked() 只依赖 homeaway_table.json，可独立导入
🔴公式修正(P2-2): 原对抗耦合三项平均中 (基准 - 主队场均失球) 可为**负**，
   把「强客队 vs 弱主队」的 λa 硬拽下来（实测 斯特拉斯堡 vs PSG 市场客胜 68.3% → HAF 39.6%）。
   现改为**比率(泊松对数线性)口径**，并对 λ 落负/失真加守卫。
用法:
    python calc_homeaway.py                       # 重建 homeaway_table.json（需 data/Matches.csv）
    python calc_homeaway.py --ha "Strasbourg,Paris SG" --league 法甲
"""
import argparse
import io
import json
import math
import os
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8')
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

DIV5 = {'E0': '英超', 'SP1': '西甲', 'D1': '德甲', 'I1': '意甲', 'F1': '法甲'}
# 联赛主客场基准（近5年实测·HAF设计文档第六节）
LEAGUE_BASE = {
    '英超': {'主场胜率': 43.6, '客场胜率': 33.5, '主队均球': 1.56, '客队均球': 1.33},
    '西甲': {'主场胜率': 44.4, '客场胜率': 28.6, '主队均球': 1.43, '客队均球': 1.11},
    '德甲': {'主场胜率': 43.0, '客场胜率': 31.9, '主队均球': 1.73, '客队均球': 1.41},
    '意甲': {'主场胜率': 41.0, '客场胜率': 32.4, '主队均球': 1.49, '客队均球': 1.29},
    '法甲': {'主场胜率': 41.7, '客场胜率': 33.5, '主队均球': 1.50, '客队均球': 1.30},
}

# 🔴HAF 守卫阈值: |λ_HAF − λ_市场| > 0.5 → 只标注·不喂方向判定
HAF_GUARD_DELTA = 0.50


def _table_path():
    for p in (os.path.join(ROOT, 'data', 'tmp', 'homeaway_table.json'),
              os.path.join('data', 'tmp', 'homeaway_table.json')):
        if os.path.exists(p):
            return p
    return None


_TABLE_CACHE = None


def load_table():
    """读 homeaway_table.json（只依赖已发布 JSON·不需要 Matches.csv）"""
    global _TABLE_CACHE
    if _TABLE_CACHE is not None:
        return _TABLE_CACHE
    p = _table_path()
    if not p:
        _TABLE_CACHE = {}
        return _TABLE_CACHE
    _TABLE_CACHE = json.load(open(p, encoding='utf-8'))
    return _TABLE_CACHE


def haf_couple(home_en, away_en, lg, rho=1.0):
    """对抗耦合 λ（泊松对数线性口径）

    🔴2026-10-17 公式修正(P2-2):
      旧: λh = (主队主场均进球 + (基准主均球 − 客队客场均失球) + 基准主均球)/3
          λa = (客队客场均进球 + (基准客均球 − 主队主场均失球) + 基准客均球)/3
          → 中间项在「强客队 vs 弱主队」时为**负**，把强客队 λ 拽下来
      新: 乘性(对数线性·Dixon-Coles 同族):
          λh = 主队主场进攻率 × 客队客场防守率 / 联赛主队均球
          λa = 客队客场进攻率 × 主队主场防守率 / 联赛客队均球
          再乘转化率修正 clamp 0.85-1.15（保留原设计）
      高进球率的强客队在高失球率的主队面前只会**更高**，不会莫名变低。
    返回 (λh, λa)
    """
    T = load_table()
    teams = T.get('_teams') or {}
    h = (teams.get(home_en) or {}).get(lg, {}).get('主场')
    a = (teams.get(away_en) or {}).get(lg, {}).get('客场')
    if not h or not a:
        return None, None
    base = LEAGUE_BASE.get(lg)
    if not base:
        return None, None

    # 乘性耦合（分母防 0）
    att_h = float(h.get('场均进球') or 0.0)
    def_h = float(h.get('场均失球') or 0.0)
    att_a = float(a.get('场均进球') or 0.0)
    def_a = float(a.get('场均失球') or 0.0)
    lh_raw = att_h * (def_a / base['客队均球']) if base['客队均球'] else att_h
    la_raw = att_a * (def_h / base['主队均球']) if base['主队均球'] else att_a

    # 转化率修正（保留原设计·clamp 0.85-1.15）
    ch = h.get('攻防转化率%') or 9.0
    ca = a.get('攻防转化率%') or 9.0
    kh = max(0.85, min(1.15, 1 + (ch - ca) / 100.0))
    ka = max(0.85, min(1.15, 1 + (ca - ch) / 100.0))
    lh = max(0.20, min(5.0, lh_raw * kh))
    la = max(0.20, min(5.0, la_raw * ka))
    return round(lh, 3), round(la, 3)


def haf_couple_checked(home_en, away_en, lg, market_lambda_h=None, market_lambda_a=None):
    """带守卫的耦合 → dict(lh, la, guard, reason)

    guard 非 None 表示 HAF 与市场偏差过大（> HAF_GUARD_DELTA），
    上层应**只作偏移标注、不喂方向判定**（HAF 是历史场地子集统计，市场是当前定价）。
    """
    lh, la = haf_couple(home_en, away_en, lg)
    res = {'lh': lh, 'la': la, 'guard': None, 'reason': None, 'delta_lh': None, 'delta_la': None}
    if lh is None:
        res['guard'] = 'no_profile'
        res['reason'] = 'HAF 档案缺失(%s/%s·%s)' % (home_en, away_en, lg)
        return res
    dl = da = None
    if market_lambda_h is not None:
        dl = lh - float(market_lambda_h)
    if market_lambda_a is not None:
        da = la - float(market_lambda_a)
    res['delta_lh'], res['delta_la'] = (None if dl is None else round(dl, 3),
                                        None if da is None else round(da, 3))
    worst = max([abs(x) for x in (dl, da) if x is not None], default=0.0)
    if worst > HAF_GUARD_DELTA:
        res['guard'] = 'strong_disagreement'
        res['reason'] = ('HAF 与市场偏差 %.2f 球 > %.2f 阈值 → 只标注·不喂方向判定'
                         % (worst, HAF_GUARD_DELTA))
    return res


# ══════════════════════════════════════════════════════════════════
# 建表（需要 data/Matches.csv·未分发时跳过·不影响查表耦合）
# ══════════════════════════════════════════════════════════════════
def _build_table():
    """从 Matches.csv 重建 homeaway_table.json（★ 唯一需要 CSV 的入口）"""
    import csv
    from collections import defaultdict

    p = os.path.join(ROOT, 'data', 'Matches.csv')
    if not os.path.exists(p):
        print('⏭️ data/Matches.csv 不存在（公开版未分发）→ 跳过建表；'
              '已有 homeaway_table.json 仍可用于查表耦合')
        return None

    # 1) 收集近5年五大联赛场次
    matches = []
    with open(p, encoding='utf-8') as f:
        rd = csv.reader(f); hdr = next(rd)
        idx = {k: hdr.index(k) for k in ['Division', 'MatchDate', 'HomeTeam', 'AwayTeam', 'FTResult',
                                         'FTHome', 'FTAway', 'HomeShots', 'AwayShots', 'HomeTarget',
                                         'AwayTarget', 'HomeCorners', 'AwayCorners']}
        for r in rd:
            if len(r) < len(hdr):
                continue
            div = r[idx['Division']]
            if div not in DIV5 or r[idx['MatchDate']][:4] < '2020':
                continue
            d = {'lg': DIV5[div], 'ht': r[idx['HomeTeam']], 'at': r[idx['AwayTeam']],
                 'res': r[idx['FTResult']]}
            try:
                d['fh'] = float(r[idx['FTHome']]); d['fa'] = float(r[idx['FTAway']])
                d['hshots'] = float(r[idx['HomeShots']]) if r[idx['HomeShots']].strip() else None
                d['ashots'] = float(r[idx['AwayShots']]) if r[idx['AwayShots']].strip() else None
                d['htarget'] = float(r[idx['HomeTarget']]) if r[idx['HomeTarget']].strip() else None
                d['atarget'] = float(r[idx['AwayTarget']]) if r[idx['AwayTarget']].strip() else None
                d['hcorn'] = float(r[idx['HomeCorners']]) if r[idx['HomeCorners']].strip() else None
                d['acorn'] = float(r[idx['AwayCorners']]) if r[idx['AwayCorners']].strip() else None
            except Exception:
                continue
            matches.append(d)

    # 2) 每队×场地聚合
    def newstat():
        return defaultdict(lambda: [0, 0, 0, 0, 0, 0, 0, 0, 0])

    home = defaultdict(newstat); away = defaultdict(newstat)
    for m in matches:
        h = home[m['ht']][m['lg']]; a = away[m['at']][m['lg']]
        for s in (h, a):
            s[3] += 1
        if m['res'] == 'H':
            h[0] += 1; a[2] += 1
        elif m['res'] == 'A':
            a[0] += 1; h[2] += 1
        else:
            h[1] += 1; a[1] += 1
        h[4] += m['fh']; h[5] += m['fa']; a[4] += m['fa']; a[5] += m['fh']
        for s, sh, ta, co in ((h, m['hshots'], m['htarget'], m['hcorn']),
                              (a, m['ashots'], m['atarget'], m['acorn'])):
            if sh: s[6] += sh
            if ta: s[7] += ta
            if co: s[8] += co

    def stat_to_dict(s, base_win, base_goals):
        n = s[3]
        if n == 0:
            return None
        win = s[0] / n * 100; draw = s[1] / n * 100
        g_avg = s[4] / n; ga_avg = s[5] / n
        shots = s[6] / n if s[6] else None; target = s[7] / n if s[7] else None
        corn = s[8] / n if s[8] else None
        conv = (s[4] / s[6] * 100) if s[6] else None
        return {
            'n': n, '胜率%': round(win, 1), '平率%': round(draw, 1), '负率%': round(100 - win - draw, 1),
            '场均进球': round(g_avg, 2), '场均失球': round(ga_avg, 2), '场均净胜': round(g_avg - ga_avg, 2),
            '场均射门': round(shots, 1) if shots else None,
            '场均射正': round(target, 1) if target else None,
            '场均角球': round(corn, 1) if corn else None,
            '攻防转化率%': round(conv, 1) if conv else None,
            '胜率增益pp': round(win - base_win, 1), '进球增益': round(g_avg - base_goals, 2),
        }

    out = {'_meta': {'来源': 'Matches.csv 五大联赛近5年(2020+)·2026-08-25·HAF数据层',
                     '联赛基准': LEAGUE_BASE, '样本不足阈值': 15,
                     '耦合口径': '乘性(泊松对数线性)·2026-10-17 修正'},
           '_teams': {}}
    all_teams = sorted(set([m['ht'] for m in matches] + [m['at'] for m in matches]))
    for t in all_teams:
        entry = {}
        for lg, base in LEAGUE_BASE.items():
            hs, as_ = home[t].get(lg), away[t].get(lg)
            hd = stat_to_dict(hs, base['主场胜率'], base['主队均球']) if hs and hs[3] else None
            ad = stat_to_dict(as_, base['客场胜率'], base['客队均球']) if as_ and as_[3] else None
            if hd is None and ad is None:
                continue
            risk = []
            if hd and hd['n'] < 15: risk.append('主场样本不足')
            if ad and ad['n'] < 15: risk.append('客场样本不足')
            entry[lg] = {'主场': hd, '客场': ad, '样本风险': risk,
                         '主场龙系数': round(hd['胜率%'] - ad['胜率%'], 1) if hd and ad else None}
        if entry:
            out['_teams'][t] = entry

    dst = os.path.join(ROOT, 'data', 'tmp', 'homeaway_table.json')
    with open(dst, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print('homeaway_table.json 已生成: %d 队' % len(out['_teams']))
    return out


def _print_couple(hname, aname, only_lg=None):
    """CLI 展示：对抗耦合（统一走 haf_couple·保证与生产同一条公式）"""
    T = load_table()
    if not T:
        print('homeaway_table.json 缺失')
        return
    teams = T['_teams']
    for lg in ([only_lg] if only_lg else list(LEAGUE_BASE)):
        if lg not in LEAGUE_BASE:
            continue
        hv = (teams.get(hname) or {}).get(lg, {}).get('主场')
        av = (teams.get(aname) or {}).get(lg, {}).get('客场')
        if not (hv and av):
            continue
        base = LEAGUE_BASE[lg]
        lh, la = haf_couple(hname, aname, lg)
        print('\n=== 对抗耦合 %s(主场) vs %s(客场) [%s] ===' % (hname, aname, lg))
        print('主队主场: 胜率%.1f%% 场均进球%.2f 失球%.2f 转化率%s%%'
              % (hv['胜率%'], hv['场均进球'], hv['场均失球'], hv['攻防转化率%']))
        print('客队客场: 胜率%.1f%% 场均进球%.2f 失球%.2f 转化率%s%%'
              % (av['胜率%'], av['场均进球'], av['场均失球'], av['攻防转化率%']))
        print('🔴对抗耦合 λh=%.2f λa=%.2f（乘性·泊松对数线性·2026-10-17 修正）' % (lh, la))
        print('   λh = 主队主场进%.2f × (客队客场失%.2f / 联赛客均%.2f)'
              % (hv['场均进球'], av['场均失球'], base['客队均球']))
        print('   λa = 客队客场进%.2f × (主队主场失%.2f / 联赛主均%.2f)'
              % (av['场均进球'], hv['场均失球'], base['主队均球']))
        sys.path.insert(0, HERE)
        try:
            from calc_poisson import probs, pois
            ph, pd_, pa = probs(lh, la)
            p_over = 1 - sum(pois(i, lh) * pois(j, la) for i in range(3) for j in range(3 - i))
            p_over35 = 1 - sum(pois(i, lh) * pois(j, la) for i in range(4) for j in range(4 - i))
            print('\n📊 泊松输出（HAF λ）:')
            print('   胜平负: 主%.1f%% / 平%.1f%% / 客%.1f%%' % (ph * 100, pd_ * 100, pa * 100))
            print('   大小球: O2.5=%.1f%% / O3.5=%.1f%%' % (p_over * 100, p_over35 * 100))
            print('   🔴主客场偏移: 主场增益%+.1fpp(基准%.1f%%)·客场增益%+.1fpp(基准%.1f%%)'
                  % (hv['胜率增益pp'], base['主场胜率'], av['胜率增益pp'], base['客场胜率']))
        except ImportError as e:
            print('泊松输出跳过:', e)
        if only_lg:
            break


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--team', help='查单队档案')
    ap.add_argument('--ha', help='对抗耦合: 主队,客队')
    ap.add_argument('--league', help='限定联赛（如 法甲）')
    ap.add_argument('--build', action='store_true', help='重建 homeaway_table.json（需 Matches.csv）')
    a = ap.parse_args()

    if a.build:
        _build_table()
        return

    if a.team:
        T = load_table()
        t = (T.get('_teams') or {}).get(a.team)
        if not t:
            print('未找到:', a.team)
            return
        for lg, v in t.items():
            print('\n%s [%s] 主场龙系数=%spp 风险=%s'
                  % (a.team, lg, v['主场龙系数'], v['样本风险']))
            print('  主场:', json.dumps(v['主场'], ensure_ascii=False))
            print('  客场:', json.dumps(v['客场'], ensure_ascii=False))
        return

    if a.ha:
        hname, aname = [x.strip() for x in a.ha.split(',')]
        _print_couple(hname, aname, a.league)
        return

    ap.print_help()


if __name__ == '__main__':
    main()
