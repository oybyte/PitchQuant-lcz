# -*- coding: utf-8 -*-
"""赔率快照保存（T-0 早盘时点·🔴支持多时点累积·供完整分析做赔率变动对比）

用法:
  python data/tmp/snapshot_save.py --leagues 欧国联 --bj 22:00-06:00 --tag nl   # 抓取并存一份快照
  python data/tmp/snapshot_save.py --leagues 英超,西甲,欧冠 --bj 22:00-06:00 --tag eu5   # 🔴五大联赛+欧战
  python data/tmp/snapshot_save.py --list                                        # 列出全部快照
  python data/tmp/snapshot_save.py --diff "Belgium vs France"                    # 🔴该场跨快照赔率时序(变动)
落盘:
  data/tmp/snapshots/<tag>_<YYYYMMDD_HHMMSS>.json   原始全市场（脚本消费）
  data/tmp/snapshots/<tag>_<YYYYMMDD_HHMMSS>.md     人读盘口表（分析引用）

🔴 数据隔离（2026-09-28 固化）:
  - 文件名**秒级时间戳** → 多次调取**各自成文件·只增不改·绝不覆盖**（可无限累积成时序）
  - 分析时**按 event_id / 队名精确匹配本场**·🔴**禁跨场复用**（防场次错配污染）
  - 同场多份 → 按 saved_at 排序 · 最早=早盘(T-0) · 最新=临场(T-n)
🔴 定位: 预分析与完整分析之间的「时间锚」。完整分析(Step0-11) 读入 →
  与竞彩 txt(赛前)/终赔 对比 → 支撑 V1 双源变动 / V2 诱阻盘 / V6 盘口联动 / P1-3 Steam / P2-1 CLV。
"""
import argparse, datetime as dt, glob, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_retry import fetch_json

KEY = os.environ.get('ODDS_API_KEY', '')
LG = {
    # 🔴2026-09-29 接口-1 修复（《双通道问题汇总》P1-1/接口-1）:
    #   并入 五大联赛 + 欧联 + 欧冠（slug 与 prestep_fetch.LG 同源）→
    #   ⑤.5 双通道的机构通道不再只在欧国联可用 · 主战场(五大联赛+欧战)同样可拉快照。
    '英超': ['england-premier-league'],
    '西甲': ['spain-laliga'],
    '德甲': ['germany-bundesliga'],
    '意甲': ['italy-serie-a'],
    '法甲': ['france-ligue-1'],
    '欧联': ['international-clubs-uefa-europa-league'],
    '欧冠': ['international-clubs-uefa-champions-league'],
    '欧国联': ['international-uefa-nations-league-league-%s-gr-%d' % (g, i) for g in 'abcd' for i in range(1, 5)],
}
SNAP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'snapshots')
BJ_OFFSET = 8


def bj_window(lo, hi):
    """「今晚」窗口（北京时）。凌晨 0-6 点运行 → 归前一晚开始的窗口。"""
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) + dt.timedelta(hours=BJ_OFFSET)
    d0 = now.replace(hour=int(lo[:2]), minute=int(lo[3:]), second=0, microsecond=0)
    if now.hour < 6:
        d0 -= dt.timedelta(days=1)
    span = (int(hi[:2]) - int(lo[:2])) % 24 or 8
    return d0.strftime('%Y-%m-%d %H:%M'), (d0 + dt.timedelta(hours=span)).strftime('%Y-%m-%d %H:%M')


def _extract(raw):
    """从 1xbet 原始市场提取关键盘口"""
    out = dict(ml='-', ah='-', o25='-', o35='-', btts='-', cs='-', upd='-')
    if not isinstance(raw, dict):
        return out
    bk = (raw.get('bookmakers') or {}).get('1xbet') or []

    def find(name):
        for m in bk:
            if (m.get('name') or '').lower() == name.lower():
                return m
        return None

    m = find('ML')
    if m and m.get('odds'):
        o = m['odds'][0]
        out['ml'] = '%s/%s/%s' % (o.get('home'), o.get('draw'), o.get('away'))
        out['upd'] = (m.get('updatedAt') or '')[:16].replace('T', ' ')
    s = find('Spread')
    if s and s.get('odds'):
        best = min(s['odds'], key=lambda x: abs((x.get('hdp') or 0) + 1.0))
        out['ah'] = '让%+.2f 主%s/客%s' % (best.get('hdp', 0), best.get('home'), best.get('away'))
    tt = find('Totals')
    if tt and tt.get('odds'):
        for x in tt['odds']:
            if abs((x.get('hdp') or 0) - 2.5) < 0.01:
                out['o25'] = 'O%s/U%s' % (x.get('over'), x.get('under'))
            if abs((x.get('hdp') or 0) - 3.5) < 0.01:
                out['o35'] = 'O%s/U%s' % (x.get('over'), x.get('under'))
    b = find('Both Teams To Score')
    if b and b.get('odds'):
        out['btts'] = '是%s/否%s' % (b['odds'][0].get('yes'), b['odds'][0].get('no'))
    c = find('Correct Score')
    if c and c.get('odds'):
        lo = min(c['odds'], key=lambda x: float(x.get('odds') or 99))
        out['cs'] = '%s=%s' % (lo.get('label'), lo.get('odds'))
    return out


def _load_all():
    out = []
    for f in sorted(glob.glob(os.path.join(SNAP_DIR, '*.json'))):
        try:
            d = json.load(open(f, encoding='utf-8'))
        except Exception:
            continue
        if 'games' not in d:
            continue
        d['_file'] = os.path.basename(f)
        out.append(d)
    out.sort(key=lambda x: x.get('saved_at', ''))
    return out


def _match(g, key):
    k = key.lower().replace('vs', ' ').split()
    h = (g.get('home') or '').lower()
    a = (g.get('away') or '').lower()
    return all(w in h or w in a for w in k) if k else False


# 🔴2026-09-29 修复(P0·数据链断裂): 快照存**英文**队名，而竞彩 txt 是**中文**队名 →
#   原 _match 纯英文子串匹配 → 中文输入恒不命中 → calc_all N21 恒报「无本场快照匹配」。
#   实测: 09-28 三场(Belgium/France 等 N21 均未命中) → 快照**未真正进入决策链**。
#   修法: 国家队中文→英文表（nl_team_cn_en.json）+ 🔴俱乐部中文→英文表（data_bridge.TEAM_ALIASES）。
_NL_CN2EN = None
_CLUB_ALIAS = None


def _nl_map():
    """国家队中文名 → 英文（懒加载 data/tmp/nl_team_cn_en.json）"""
    global _NL_CN2EN
    if _NL_CN2EN is None:
        try:
            _p = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'nl_team_cn_en.json')
            _NL_CN2EN = json.load(open(_p, encoding='utf-8')).get('teams', {}) or {}
        except Exception:
            _NL_CN2EN = {}
    return _NL_CN2EN


def _club_map():
    """🔴2026-09-29 接口-2 修复（《双通道问题汇总》接口-2）:
    俱乐部中文名 → 英文（懒加载 data/online_learning/data_bridge.TEAM_ALIASES·191 条）。
    此前 cn2en 只查国家队表 → 五大联赛/欧冠中文队名恒不命中 → 快照匹配失效。"""
    global _CLUB_ALIAS
    if _CLUB_ALIAS is None:
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                            '..', 'online_learning'))
            import data_bridge as _db
            _CLUB_ALIAS = getattr(_db, 'TEAM_ALIASES', {}) or {}
        except Exception:
            _CLUB_ALIAS = {}
    return _CLUB_ALIAS


def _first(v):
    """别名表值 → 首个英文字符串（兼容 str / list / tuple）"""
    if isinstance(v, (list, tuple)) and v:
        return v[0]
    return v if isinstance(v, str) else None


def cn2en(name):
    """中文队名 → 快照英文名（🔴逐名转换·禁整体拼接后再转换）
    🔴2026-09-29 接口-2: 加载顺序 = 先国家队表(nl_team_cn_en.json) → 再俱乐部表(data_bridge.TEAM_ALIASES)"""
    if not name:
        return name or ''
    m = _nl_map()
    if name in m:
        return m[name]
    for cn, en in m.items():
        if cn and cn in name:
            return en
    c = _club_map()
    if name in c:
        return _first(c[name]) or name
    for cn, en in c.items():
        if cn and cn in name:
            return _first(en) or name
    return name


def find_for(home, away, limit=None):
    """🔴按队名匹配本场快照（供 calc_all / 完整分析消费·数据链闭环）
    返回 {count, first, last, points}；count=0 表示无早盘时点(T-0 缺失)
    🔴2026-09-29: 入参支持**中文**队名（逐名转英文后匹配·修跨语言不命中 P0）
    🔴联赛无关: 五大联赛/欧冠/欧国联 数据到位即自动接入"""
    ds = _load_all()
    hits = []
    _kh, _ka = cn2en(home), cn2en(away)
    for d in ds:
        for g in d.get('games', []):
            if _match(g, '%s %s' % (_kh, _ka)):
                hits.append({'saved_at': d.get('saved_at'), 'file': d['_file'],
                             'kickoff_bj': g.get('kickoff_bj'), 'event_id': g.get('event_id'),
                             'extract': _extract(g.get('raw_1xbet'))})
    if limit:
        hits = hits[-limit:]
    return {'count': len(hits), 'first': hits[0] if hits else None,
            'last': hits[-1] if hits else None, 'points': hits}


def _imp(o):
    """三个赔率 → 去水隐含概率(%)"""
    try:
        a, b, c = [1.0 / float(x) for x in o]
    except Exception:
        return None
    s = a + b + c
    return (100 * a / s, 100 * b / s, 100 * c / s)


def _ah_hdp(s):
    """亚盘串 → (盘口, 主水, 客水)"""
    m = re.search(r'让([+-][0-9.]+)\s*主([0-9.]+)/客([0-9.]+)', s or '')
    return (float(m.group(1)), float(m.group(2)), float(m.group(3))) if m else None


def delta_for(home, away, end_ml=None, end_ah=None, end_o25=None, end_label=None):
    """🔴跨快照算「变动」→ 供 V1/V2/V6/P1-3 判定消费（非仅展示）
    🔴2026-09-29 增强（用户指令「把 prestep 快照 与 正式执行时的赔率 串联成完整欧亚盘时间序列」）:
       end_ml/end_ah/end_o25 = 「正式执行时点」（calc_all 的 --eu/--handi/--o25）→ 作为序列**末点**
       未给 → 退回「快照末点」（原行为·兼容）
    返回 {count, ml_pp, ml_chg_pct, ah, o25_imp, signal[], span, series[], end_label}"""
    from snapshot_save import find_for as _ff
    r = _ff(home, away)
    out = {'count': r['count'], 'ml_pp': None, 'ml_chg_pct': None, 'ah': None, 'o25_imp': None,
           'signal': [], 'span': None, 'series': [], 'end_label': None}
    # 🔴2026-09-29 P2-4 修复（《全量审计报告·V3.5.76 复检》）:
    #   ① 初始 dict 补 'ml_chg_pct': None —— 原实现无此键，而 docstring 声明含它 →
    #      消费端 calc_all `if _dl['ml_chg_pct']` 在无快照时抛 KeyError（被外层 except 吞成「异常」）
    #   ② 无 prestep 快照但给了「正式执行时点」→ 仍输出该单点序列（count=1），
    #      原实现直接 return → 有 --eu 也报「共 0 时点」（丢掉正式执行时点）
    if r['count'] < 1:
        if end_ml:
            out['end_label'] = end_label or '正式执行'
            out['series'] = [{'at': out['end_label'], 'ml': end_ml, 'ah': end_ah or '-',
                              'o25': end_o25 or '-', 'src': '正式分析(--eu/--handi/--o25)'}]
            out['count'] = 1
            out['span'] = '%s（无 prestep 快照·仅正式执行时点）' % out['end_label']
        return out
    fe = r['first']['extract']
    # 🔴序列（完整时点链：全部 prestep 快照）
    out['series'] = [{'at': p['saved_at'], 'ml': p['extract']['ml'], 'ah': p['extract']['ah'],
                      'o25': p['extract']['o25'], 'src': p['file']} for p in r['points']]
    # 🔴末点: 优先「正式执行时点」·否则取快照末点
    if end_ml:
        le = {'ml': end_ml, 'ah': end_ah or '-', 'o25': end_o25 or '-'}
        _ls = end_label or '正式执行'
        out['end_label'] = _ls
        out['series'].append({'at': _ls, 'ml': le['ml'], 'ah': le['ah'], 'o25': le['o25'],
                              'src': '正式分析(--eu/--handi/--o25)'})
    else:
        if r['count'] < 2:
            return out
        le = r['last']['extract']
        _ls = r['last']['saved_at']
    out['span'] = '%s → %s' % (r['first']['saved_at'], _ls)
    out['count'] = len(out['series'])
    # ── ML 去水隐含概率变动(pp) ──
    i0, i1 = _imp(fe['ml'].split('/')), _imp(le['ml'].split('/'))
    if i0 and i1:
        d = [round(i1[k] - i0[k], 1) for k in range(3)]
        out['ml_pp'] = d
        # 🔴口径对齐 AGENTS D1/D2: **赔率变动%**（升赔≥2T累计>3%）·非隐含pp（2026-09-28 修正）
        try:
            _o0 = [float(x) for x in fe['ml'].split('/')]
            _o1 = [float(x) for x in le['ml'].split('/')]
            _ch = [round(100 * (_o1[k] - _o0[k]) / _o0[k], 1) for k in range(3)]
            out['ml_chg_pct'] = _ch
            if _ch[0] >= 3.0:
                out['signal'].append('🔴D1 背离嫌疑: 主胜赔率 %+.1f%%（早盘→最新·阈值+3%%）→ 降档/不排除' % _ch[0])
            elif _ch[0] <= -3.0:
                out['signal'].append('🟢主胜降赔 %+.1f%%（资金流入·主方向升权线索）' % _ch[0])
            if _ch[2] <= -3.0:
                out['signal'].append('🔴客胜降赔 %+.1f%%（客队被看好·V1 双源变动）' % _ch[2])
            elif _ch[2] >= 3.0:
                out['signal'].append('🟡客胜升赔 %+.1f%%（客队被看淡·修正53 S2 参考）' % _ch[2])
            if abs(_ch[1]) >= 3.0:
                out['signal'].append('🟡平局赔率 %+.1f%%（平赔异动·修正53 组A 参考）' % _ch[1])
        except Exception:
            pass
        out['ml_pp'] = d
    # ── 亚盘盘口/水位变动 → V2 诱阻 / V6 联动 ──
    a0, a1 = _ah_hdp(fe['ah']), _ah_hdp(le['ah'])
    if a0 and a1:
        out['ah'] = {'hdp': '%.2f → %.2f' % (a0[0], a1[0]), 'hw': '%.3f → %.3f' % (a0[1], a1[1])}
        if a1[0] != a0[0]:
            out['signal'].append('🔴盘口移动: 让%.2f → 让%.2f（%s）'
                                 % (a0[0], a1[0], '加深=阻/诱上风险' if a1[0] < a0[0] else '退盘=诱阻关注'))
        if abs(a1[1] - a0[1]) >= 0.15:
            out['signal'].append('🟡主水变动 %.3f → %.3f（水位剪刀差·V2 四步第②步）' % (a0[1], a1[1]))
    # ── O2.5 隐含变动 → Step6 大球方向 ──
    try:
        o0 = 1.0 / float(fe['o25'].split('/')[0].lstrip('O'))
        o1 = 1.0 / float(le['o25'].split('/')[0].lstrip('O'))
        out['o25_imp'] = round(100 * (o1 - o0), 1)
        if abs(out['o25_imp']) >= 3.0:
            out['signal'].append('%s大球隐含 %+.1fpp（Step6 量级参考）'
                                 % ('🟢' if out['o25_imp'] > 0 else '🔵', out['o25_imp']))
    except Exception:
        pass
    return out


def dual_channel(jc_1x2=None, jc_handi=None, ah_from=None, ah_to=None, window_min=None):
    """🔴双通道四象限判定（V3.5.76·2026-09-29 用户方案《竞彩×欧亚盘双通道动态判定机制》）
    公众通道 = 竞彩逐T（jc_1x2=[(t,(H,D,A)),...]·抽水 12.8%·散户情绪代理）
    机构通道 = 欧亚盘时序（ah_from/ah_to="让±X 主Y/客Z" 早盘→临场·抽水 6.9%·机构意图）

    window_min（🔴2026-09-29 P1-3 修复: 此前文档称已支持但函数无此参数 → 文档-代码不一致）:
      距开赛分钟数 → 窗口分级，写入返回的 window 字段
        >48h(2880min) → 「⚠️烟雾弹 → 机构通道降级弱参考」（早期盘口失真）
        ≤90min        → 「✅临场 → 信息密度最高」
        90-2880       → 「常规窗口」｜None → 「未知·不降级」

    🔴铁律: 只调置信度 ≤±1 档·永不反转 L2 硬核方向·未回测项标「⏳待回测·仅参考」
    🔴follow 口径唯一性（P2-2）: 本函数 C2.follow 为**唯一 follow 判定口径**；
       fundflow_analyzer.rlm_detect(ah_from, ah_to) 转为其**佐证/独立观测**（不同阈值·不互替）
    返回 {C1,C2,C3,quadrant(Q号,名,动作,依据),window,notes[]}｜无竞彩 → C1=None 三态
    """
    res = {'C1': None, 'C2': None, 'C3': None, 'quadrant': None, 'window': None, 'notes': []}
    # 🔴P1-3: 窗口分级（>48h 烟雾弹降级 · ≤90min 临场最强）
    if window_min is not None:
        try:
            _w = float(window_min)
            if _w > 2880:
                res['window'] = {'min': _w, 'grade': '⚠️早盘>48h · 烟雾弹 → 机构通道降级为弱参考'}
            elif _w <= 90:
                res['window'] = {'min': _w, 'grade': '✅临场≤90min → 信息密度最高'}
            else:
                res['window'] = {'min': _w, 'grade': '常规窗口（90min-48h）'}
        except Exception:
            res['window'] = None
    if not jc_1x2 or len(jc_1x2) < 2:
        res['notes'].append('⚪双通道: 未传竞彩逐T → 公众通道不可判(三态)')
        return res
    try:
        v0, v1 = jc_1x2[0][1], jc_1x2[-1][1]
        if len(v0) < 3 or len(v1) < 3:
            res['notes'].append('⚪双通道: 竞彩赔率列不完整')
            return res
    except Exception:
        res['notes'].append('⚪双通道: 竞彩逐T 格式异常')
        return res
    fi = min(range(3), key=lambda i: v0[i])           # 初盘最低赔 = 公众热门
    fav = ('H', 'D', 'A')[fi]
    c1 = round(100 * (v1[fi] - v0[fi]) / v0[fi], 2)   # C1 公众热门方向降赔%(负=降赔)
    res['C1'] = {'fav': fav, 'pct': c1}
    a0, a1 = _ah_hdp(ah_from), _ah_hdp(ah_to)
    if not (a0 and a1):
        res['notes'].append('⚪双通道: 欧亚盘口不可解析（缺早盘/临场亚盘）→ 机构通道不可判(三态)')
        return res
    hdp_chg = round(a1[0] - a0[0], 2)
    hw_chg = round(a1[1] - a0[1], 3)
    if fav == 'H':                                     # 热门=主 → 盘口加深(更负) 或 主水降
        follow = (hdp_chg < -0.01) or (hw_chg <= -0.03)
    elif fav == 'A':                                   # 热门=客 → 盘口变浅(更正) 或 客水降(≈主水升)
        follow = (hdp_chg > 0.01) or (hw_chg >= 0.03)
    else:                                              # 热门=平 → 盘口不动即跟进
        follow = abs(hdp_chg) < 0.01 and abs(hw_chg) < 0.03
    res['C2'] = {'hdp_chg': hdp_chg, 'hw_chg': hw_chg, 'follow': follow}
    res['C3'] = {'water_dir': ('降=防御' if hw_chg <= -0.01 else ('升=诱' if hw_chg >= 0.01 else '平')),
                 'hdp_moved': abs(hdp_chg) >= 0.01}
    # ── 四象限（优先级 Q2 > Q1 > Q4 > Q3·诱盘警报最优先）──
    if c1 <= -2.0 and follow is False:
        res['quadrant'] = ('Q2', '诱盘警报', '公众热捧但欧亚不跟进 → 热门方向降1档 + 强制并列次方向（D1 纪律联动）',
                           '⚠️ 竞彩降赔≠方向（4场样本命中25%）·本象限依据充分')
    elif c1 <= -2.0 and follow is True:
        res['quadrant'] = ('Q1', '共识确认', '公众+机构同向 → 置信度 +0.5 档（spread<2% 且热门<1.50 可 +1 档）',
                           '✅ P0-1 已回测（spread<2% +8.7/+17.6pp）')
    elif c1 >= 2.0 and follow is True:
        res['quadrant'] = ('Q4', '阻盘信号', '欧亚看好但拉高赔率阻买 → 按欧亚方向 +0.5 档·标注「阻盘·非诱」',
                           '⏳待回测·仅参考（行业共识）')
    elif -2.0 < c1 < 2.0 and abs(hdp_chg) >= 0.01:
        # 🔴P2-1 修复(2026-09-29): 收紧为 -2.0 < c1 < 2.0 ——
        #   公众「主动看衰」(c1>=2.0) ≠ 「公众未察觉的冷门」，此前 c1>=2.0 被误标 Q3
        res['quadrant'] = ('Q3', '冷门前兆', '仅欧亚独自动·公众未察觉 → 提示关注（不直接调档·等 Steam 确认）',
                           '⏳待回测·仅参考（中文欧亚盘圈方法）')
    elif c1 >= 2.0 and follow is False:
        # 🔴P2-1 修复: 公众主动看衰 + 机构未跟 → 共识看衰（非冷门前兆·不调档）
        res['notes'].append('⚪双通道: 公众主动看衰(%+.2f%%) + 机构未跟进 → 共识看衰·不调档（非冷门前兆）' % c1)
    if res['quadrant']:
        q = res['quadrant']
        res['notes'].append('🟣双通道四象限 %s %s: %s' % (q[0], q[1], q[2]))
        res['notes'].append('   └ %s' % q[3])
    else:
        res['notes'].append('⚪双通道四象限: 未触发（C1 %+.2f%% · 欧亚跟进=%s）' % (c1, follow))
    return res


def list_snapshots():
    """列出已有快照（🔴含时点顺序·供安全选取·防跨场复用）"""
    ds = _load_all()
    if not ds:
        print('（无快照）')
        return
    for d in ds:
        w = d.get('window_bj', ['?', '?'])
        print('%s  存于 %s  窗口 %s → %s  (%d 场)' % (
            d['_file'], d.get('saved_at', '?'), w[0], w[1], len(d.get('games', []))))
        for g in d.get('games', []):
            print('     %s  %-22s vs %-22s  eventId=%s' % (
                (g.get('kickoff_bj') or '')[-5:], g.get('home'), g.get('away'), g.get('event_id')))


def diff(key):
    """🔴某场跨快照的赔率时序（多时点 → 变动）"""
    ds = _load_all()
    hits = []
    for d in ds:
        for g in d.get('games', []):
            if _match(g, key):
                hits.append((d.get('saved_at', '?'), d['_file'], g))
    if not hits:
        print('未找到该场（检查队名·用 --list 查看已有场次）')
        return
    print('=== %s 的赔率时序（%d 个时点）===' % (key, len(hits)))
    print('| 抓取时刻 | 文件 | ML 主/平/客 | 亚盘 | O2.5 | 市场更新 |')
    print('|:--|:--|:--|:--|:--|:--|')
    for t, f, g in hits:
        s = _extract(g.get('raw_1xbet'))
        print('| %s | %s | %s | %s | %s | %s |' % (t, f, s['ml'], s['ah'], s['o25'], s['upd']))
    if len(hits) >= 2:
        a, b = _extract(hits[0][2].get('raw_1xbet')), _extract(hits[-1][2].get('raw_1xbet'))
        print()
        print('🔴 变动（最早 → 最新）:')
        for lbl, k in (('ML', 'ml'), ('亚盘', 'ah'), ('O2.5', 'o25')):
            if a[k] != b[k]:
                print('   %-5s %s → %s' % (lbl, a[k], b[k]))
            else:
                print('   %-5s %s（未变）' % (lbl, a[k]))
        print('   ⏱ 时间跨度: %s → %s' % (hits[0][0], hits[-1][0]))
        # 🔴2026-09-28: 接入 delta_for → 直接输出判定信号（用户指令「模型判定依据模块输出」·非仅展示）
        _d = delta_for(key.split(' vs ')[0], key.split(' vs ')[-1]) if ' vs ' in key else None
        if _d and _d.get('signal'):
            print()
            print('🔴 判定信号（模块输出 → V1 双源变动 / V2 诱阻盘 / V6 盘口联动 / Step6 量级）:')
            for s in _d['signal']:
                print('   %s' % s)
        elif _d:
            print()
            print('⚪ 变动未触发阈值（赔率 <3% / 盘口未动 / 水位 <0.15 / 隐含 <3pp）')
    else:
        print()
        print('ℹ️ 仅 1 个时点 → 再抓一次即可形成变动对比（V1/V2/V6/P1-3 需要 ≥2 时点）')


def collect(leagues, lo, hi, t0, t1):
    rows, misses = [], []
    for lg in leagues.split(','):
        for slug in LG.get(lg.strip(), []):
            u = 'https://api.odds-api.io/v3/events?apiKey=%s&sport=football&league=%s&status=pending' % (KEY, slug)
            d = fetch_json(u)
            if not d:
                misses.append(slug)
                continue
            evs = d.get('events') if isinstance(d, dict) else d
            for e in (evs or []):
                ts = (e.get('date') or '')[:16].replace('T', ' ')
                if not ts:
                    continue
                try:
                    utc = dt.datetime.strptime(ts, '%Y-%m-%d %H:%M')
                except Exception:
                    continue
                bj = (utc + dt.timedelta(hours=BJ_OFFSET)).strftime('%Y-%m-%d %H:%M')
                if not (t0 <= bj <= t1):
                    continue
                rows.append({'league': lg, 'slug': slug, 'event_id': e.get('id'),
                             'home': e.get('home'), 'away': e.get('away'), 'kickoff_bj': bj})
    return rows, misses


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--leagues', default='欧国联')
    ap.add_argument('--bj', default='22:00-06:00')
    ap.add_argument('--tag', default='nl')
    ap.add_argument('--list', action='store_true', help='列出已有快照及场次（不拉取）')
    ap.add_argument('--diff', help='显示某场跨快照的赔率时序（如 "Belgium vs France"）')
    a = ap.parse_args()
    if a.list:
        list_snapshots()
        return
    if a.diff:
        diff(a.diff)
        return
    lo, hi = a.bj.split('-')
    t0, t1 = bj_window(lo, hi)
    print('窗口(北京): %s → %s' % (t0, t1))
    rows, misses = collect(a.leagues, lo, hi, t0, t1)
    print('窗口内 %d 场 ｜ slug 拉取失败 %d 个%s' % (
        len(rows), len(misses), ('（可能漏场: %s）' % ','.join(misses[:4])) if misses else ''))
    for r in rows:
        u = 'https://api.odds-api.io/v3/odds?apiKey=%s&eventId=%s&bookmakers=1xbet' % (KEY, r['event_id'])
        r['raw_1xbet'] = fetch_json(u)
    ts = dt.datetime.now().strftime('%Y%m%d_%H%M%S')   # 🔴秒级: 同分钟多次调用亦不覆盖
    os.makedirs(SNAP_DIR, exist_ok=True)
    jp = os.path.join(SNAP_DIR, '%s_%s.json' % (a.tag, ts))
    json.dump({'saved_at': dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'window_bj': [t0, t1],
               'source': 'Odds-API v3 (1xbet 全市场)', 'games': rows},
              open(jp, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('✅ JSON 落盘:', jp)
    md = ['# 赔率快照 %s（%s → %s·北京）' % (ts, t0, t1), '',
          '> 🔴 用途: 完整分析(Step0-11)时读入 → 与竞彩 txt/终赔对比 → 支撑 V1 双源变动 / V2 诱阻盘 / V6 盘口联动 / P1-3 Steam',
          '> 🔴 数据隔离: 秒级命名·只增不改·按 event_id/队名匹配本场·禁跨场复用', '',
          '| 开赛 | 场次 | ML 主/平/客 | 亚盘(让球·主水/客水) | O2.5 | O3.5 | BTTS | CS最低 | 市场更新 | eventId |',
          '|:--|:--|:--|:--|:--|:--|:--|:--|:--|:--|']
    for r in rows:
        s = _extract(r.get('raw_1xbet'))
        md.append('| %s | %s vs %s | %s | %s | %s | %s | %s | %s | %s | %s |' % (
            r['kickoff_bj'][-5:], r['home'], r['away'], s['ml'], s['ah'], s['o25'], s['o35'],
            s['btts'], s['cs'], s['upd'], r['event_id']))
    md += ['', '> 口径: ML=1xbet 胜平负 · 亚盘=Spread(近 -1 档·主/客水) · O2.5/O3.5=Totals · BTTS · CS最低=Correct Score 最低赔率比分']
    mp = os.path.join(SNAP_DIR, '%s_%s.md' % (a.tag, ts))
    open(mp, 'w', encoding='utf-8').write(chr(10).join(md) + chr(10))
    print('✅ MD 落盘:', mp)
    for r in rows:
        print('   %s  %-22s vs %-22s  eventId=%s' % (r['kickoff_bj'][-5:], r['home'], r['away'], r['event_id']))


if __name__ == '__main__':
    main()
