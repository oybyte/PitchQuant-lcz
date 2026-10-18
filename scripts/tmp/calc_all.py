# calc_all.py — 全覆盖预计算聚合器 + 必核清单生成器（步骤遗失结构性根除·支柱A）
# 用法: python calc_all.py <竞彩txt路径> [联赛key] [--eu 主,平,客] [--handi 盘口] [--o25 大小球赔率] [--home_water 主水] [--elo 主队ELO差]
# 原理: 一次性输出全部确定性计算(calc_match管道) + 脚本生成的必核清单(非LLM自我清单·防自我遗漏)
# 输出: 完整预计算报告 + [必核清单] 段——LLM 照清单逐项消费·缺项=输出不完整

import io, sys, os, subprocess, re, json
sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)  # 🔴2026-09-15合并(源自workbuddy): 防Windows管道块缓冲/丢行

# 🔴2026-09-15 修复: 数据表统一路径解析(data/tmp/)——原用 dirname(__file__) 拼表名, 表不在 scripts/tmp/ 下
import table_paths as _tp  # noqa: E402

# ── 必核清单（脚本硬编码·随模型规则更新·替代LLM自我清单）──
CHECKLIST = [
    # (编号, 必核项, 触发条件(脚本判定·None=必做), 数据来源/脚本)
    ('C01', 'Step1 去抽水+校准+方向差距+skew', None, 'calc_match'),
    ('C02', 'Step1 赔率档查表(odds_table·H/D/A实际率)', None, 'odds_table.json'),
    ('C03', 'Step1 凯利+反抽水比(>1.30触发F1)', None, 'calc_match'),
    ('C04', 'V1 双源赔率变动+形态学', None, 'calc_match+欧盘'),
    ('C05', 'V2 诱阻盘四步(让球变动/水位交叉/半全场/P0-P1)', None, 'calc_match'),
    ('C06', 'V3 水位联动(盘口未变前提)', None, '欧盘spread'),
    ('C07', 'V4 半全场传导+半场三元', None, 'calc_match'),
    ('C08', 'V5+V5+ 跨市场分歧+反向校验', None, 'calc_match --eu'),
    ('C09', 'V6 盘口联动(赛前60-90min临场·无→标不触发)', None, '欧盘临场'),
    ('C10', 'Step3 场景44/45/46(+欧战六项核查表·欧战才完整)', '欧战', 'SL-europe-db'),
    ('C11', 'Step3.5 情境F1-F7', None, 'calc_match反抽水'),
    ('C12', 'Step4 修正26基本面ABCDE', None, '基本面'),
    ('C13', 'Step4.5 联赛子模型(五大联赛才触发)', '五大联赛', 'SK-league-*'),
    ('C14', 'Step5 方向判定D1-D4+修正53 S1-S7', None, 'calc_match+calc_v3572'),
    ('C15', '🔴欧亚综合: direction_full(handi校正·诱盘信号)', None, 'calc_v3572'),
    ('C16', '🔴诱阻识别: match_classifier+intent(庄家主导才)', '总分>=3', 'calc_v3572'),
    ('C17', 'Step6 大球深度(O2.5→档位·goal_bin_probs)', None, 'calc_v3572'),
    ('C18', 'Step7 泊松λ反推+比分谱系+查表+融合', None, 'calc_poisson'),
    ('C19', 'Step7 净胜档多档候选(margin_candidates_pool)', None, 'calc_match'),
    ('C20', 'Step7 市场一致性检查+条件化锚定两步', None, 'calc_match'),
    ('C21', 'Step7 盈亏矩阵+资金流+主锚次锚+停止分支', None, 'CS赔率'),
    ('C22', 'Step8 总进球概率化+凯利联动', None, 'calc_match'),
    ('C23', '新闻伤停(SL-news-crawl·唯一源·三态)', None, 'SL-news-crawl'),
    ('C24', 'api-football三端点(官方概率/13家赔率/伤停)', '五大联赛+欧战', 'SL-api-football-chain'),
    ('C25', 'footballcharts基本面(λ/校准/蒙特卡洛)·⛔源已废弃(2026-09-15·域名DNS全失效)→降级 understat_xg+SK-xg-depth+联赛校准(按“无数据”三态标注·不算遗漏)', '五大联赛', 'SL-footballcharts-fetch'),
    ('C26', 'clubelo ELO(修正41一致性)', '五大联赛+欧战', 'SL-elo-fetch'),
    ('C27', 'xG深度比分判定(understat·防泄露)', '五大联赛', 'SK-xg-depth'),
    ('C28', '比分命中口径标注(主锚/次锚·第3/4候选不算)', None, '口径铁律'),
    ('C29', '自检表22项逐项证据', None, 'checklist'),
    ('C30', '落盘: case_write add/review + raw七节 + check_luopan', None, 'case_write'),
]

# 统一联赛归一化（审计 P0 修复·三套命名空间统一）——
# 原 _LMAP 只认 E0/SP1/I1/D1/F1/ec，传 epl/laliga/seriea/bundesliga/ligue1 等常见别名时
# 静默降级为「非五大」→ C13 联赛子模型 / C25 footballcharts / C27 xG 三大模块不触发
# （实测对比: 同一场英超 epl→[不触发·非五大] / E0→[必做]，已证实）。
_LG_ALIAS = {
    # 中文标准名（透传）
    '英超': '英超', '西甲': '西甲', '意甲': '意甲', '德甲': '德甲', '法甲': '法甲',
    '欧冠': '欧冠', '欧联': '欧联', '欧协联': '欧协联', '英冠': '英冠', '日职': '日职',
    # 英文代码（Matches.csv 口径）
    'E0': '英超', 'SP1': '西甲', 'I1': '意甲', 'D1': '德甲', 'F1': '法甲',
    # 英文别名（常见输入写法·大小写不敏感）
    'epl': '英超', 'premier': '英超', 'premierleague': '英超',
    'laliga': '西甲', 'liga': '西甲',
    'seriea': '意甲',
    'bundesliga': '德甲', 'bundes': '德甲',
    'ligue1': '法甲',
    'championship': '英冠', 'jleague': '日职', 'j1': '日职',
    # 欧战别名
    'ec': '欧冠', 'ucl': '欧冠', 'champions': '欧冠', 'championsleague': '欧冠',
    'el': '欧联', 'uel': '欧联', 'europa': '欧联', 'europaleague': '欧联',
    'uecl': '欧协联', 'conference': '欧协联', 'conferenceleague': '欧协联',
}


# 🔴2026-10-17(P0·反抽水基准)：calc_match.LEAGUE_VIG 的键是英文 slug
#   （epl/bundesliga/seriea/laliga/ligue1/championship/eredivisie…），
#   而调用方长期只传中文「英超」→ LEAGUE_VIG 恒不命中 → 一律落「缺省6.9%」
#   （实测 data-2.5.9 单场批 26/26 场如此）。
#   本表让 slug 也能归一，同时保留 slug 供 calc_match 查表用（见 lg_vig_key）。
_LG_SLUG2CN = {
    'epl': '英超', 'championship': '英冠', 'league1': '英甲', 'league2': '英乙',
    'bundesliga': '德甲', 'bundesliga2': '德乙', 'seriea': '意甲', 'serieb': '意乙',
    'laliga': '西甲', 'laliga2': '西乙', 'ligue1': '法甲', 'ligue2': '法乙',
    'eredivisie': '荷甲', 'portugal': '葡超', 'finland': '芬超', 'norway': '挪超',
    'japan': '日职联', 'china': '中超', 'ec': '欧冠',
}


def lg_vig_key(league):
    """联赛 → calc_match.LEAGUE_VIG 的键（英文 slug）。认不出返回 None（=标无数据）。"""
    if not league:
        return None
    s = str(league).strip()
    if s.lower() in _LG_SLUG2CN:
        return s.lower()
    for slug, cn in _LG_SLUG2CN.items():
        if s == cn:
            return slug
    return None


def norm_league(x):
    """联赛归一化 → 中文标准名（2026-09-15审计P0修复·接受 中文名/英文代码/英文别名·大小写与分隔符不敏感）
    2026-10-17 增补：同时接受 LEAGUE_VIG 的英文 slug（epl/bundesliga/…）。"""
    if not x:
        return x
    s = str(x).strip()
    k = s.lower().replace(' ', '').replace('-', '')
    return (_LG_ALIAS.get(s) or _LG_ALIAS.get(k)
            or _LG_SLUG2CN.get(k) or s)


def _layer_state_lines(txt_path, league_cn, eu=None, o25=None, handi=None):
    """C13/C26/C27 先行层三态统一声明（HAF / ELO / xG）

    🔴2026-10-17 修复(P2-1): 三层都有「数据域覆盖」限制，但原先三态写法不统一:
        · ELO 有「无数据(原因)」规定
        · HAF 缺失时 calc_all 完全无声
        · xG 缺失时同样无声
      实测本批 14/22 场 HAF 缺、10/22 ELO 缺、20/22 xG 缺 —— 报告里只能手写声明。
      现统一为「恒出现」的三行，缺失也出现并写原因（禁止笼统「无数据」）。
    """
    import os as _o, json as _j, re as _cr, sys as _s
    out = []
    _s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__)))
    EU5 = ('英超', '西甲', '德甲', '意甲', '法甲')

    # 队名（从 txt 头）
    home = away = None
    try:
        _t = open(txt_path, encoding='utf-8').read()
        _m = _cr.search(r'([^\s()（）]+)\s*[(（]主[)）]\s*[Vv][Ss]\s*([^\s()（）]+)\s*[(（]客[)）]', _t)
        if _m:
            home, away = _m.group(1), _m.group(2)
    except Exception:
        pass

    # 🔴2026-10-17: 中文队名归一（单一入口·HAF/ELO/xG 共用）
    #   输入 txt 用服务端命名（RB莱比锡/汉堡…），mapping 表用另一套（莱比锡红牛）——
    #   不归一 → 查表静默 miss（HAF 曾对 14 场批命中 0/8）。
    _CN_ALIAS = {'RB莱比锡': '莱比锡红牛', '莱比锡': '莱比锡红牛', '拜仁': '拜仁慕尼黑',
                 '巴伦西亚': '瓦伦西亚', '毕尔巴鄂竞技': '毕尔巴鄂竞技',
                 '国际米兰': '国际米兰', '国米': '国际米兰'}
    _home_cn = _CN_ALIAS.get(home, home)
    _away_cn = _CN_ALIAS.get(away, away)

    # ── HAF(C13/Step4.6) ──
    try:
        import calc_homeaway as _HA
        _T = _HA.load_table()
        _teams = (_T or {}).get('_teams') or {}
        _in_domain = bool(_teams) and league_cn in (_HA.LEAGUE_BASE or {})
        if not _teams:
            out.append('  🔴HAF(Step4.6): ⏭️ 不触发(原因: homeaway_table.json 缺失/未分发)')
        elif not _in_domain:
            out.append('  🔴HAF(Step4.6): ⏭️ 不触发(原因: 本联赛不在覆盖域·HAF 仅覆盖五大联赛·%s)' % league_cn)
        else:
            # 🔴2026-10-17(P1): 原为 24 条硬编码别名表 → 表外队伍一律落到
            #   「别名未命中」，HAF 对同一联赛的大部分场次形同不存在（14 场批命中率 0/8）。
            #   改为优先读唯一真源 data/team_name_mapping_2025-26.json（246 队·中→英），
            #   硬编码表仅作历史兜底（Mapping 未覆盖时）。
            _map = {'埃弗顿': 'Everton', '切尔西': 'Chelsea', '富勒姆': 'Fulham', '布伦特福德': 'Brentford',
                    '利物浦': 'Liverpool', '曼彻斯特城': 'Man City', '伊普斯维奇': 'Ipswich',
                    '西班牙人': 'Espanol', '马德里竞技': 'Ath Madrid', '比利亚雷亚尔': 'Villarreal',
                    '埃尔切': 'Elche', '威尼斯': 'Venezia', '那不勒斯': 'Napoli',
                    '云达不莱梅': 'Werder Bremen', '帕德博恩': 'Paderborn', '奥格斯堡': 'Augsburg',
                    '柏林联合': 'Union Berlin', '多特蒙德': 'Dortmund', '沙尔克04': 'Schalke 04',
                    '美因茨': 'Mainz', '斯特拉斯堡': 'Strasbourg', '巴黎圣日耳曼': 'Paris SG'}
            try:
                _mp = _tp.find_table('team_name_mapping_2025-26.json')
                if not _mp:
                    import os as _os
                    _cand = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(
                        _os.path.abspath(__file__)))), 'data', 'team_name_mapping_2025-26.json')
                    _mp = _cand if _os.path.exists(_cand) else None
                if _mp:
                    for _t in (_j.load(open(_mp, encoding='utf-8')).get('teams') or []):
                        _cn, _en = _t.get('cn'), _t.get('en')
                        if _cn and _en and _cn not in _map:
                            _map[_cn] = _en
            except Exception:
                pass
            # HAF 表内个别队名与 Mapping 的英文名不同（表来自 Matches.csv 历史命名），需二次对齐
            _haf_alias = {'FC Schalke 04': 'Schalke 04', 'Schalke': 'Schalke 04',
                          'Hamburg': 'Hamburg', 'Hamburger SV': 'Hamburg',
                          'Bayern München': 'Bayern Munich', 'Leipzig': 'RB Leipzig',
                          'Newcastle United': 'Newcastle', 'Real Betis': 'Betis',
                          'Athletic Bilbao': 'Ath Bilbao', 'Athletic Club': 'Ath Bilbao',
                          'Internazionale': 'Inter'}
            _haf_alias_hits = {}

            def _haf_of(cn):
                for nm in ([cn, _map.get(cn)] + _haf_alias_hits.get(cn, [])):
                    if not nm:
                        continue
                    nm = _haf_alias.get(nm, nm)
                    if nm in _teams:
                        return nm
                return None

            _h = _haf_of(_home_cn)
            _a = _haf_of(_away_cn)
            if _h and _a and _h in _teams and _a in _teams:
                _lh, _la = _HA.haf_couple(_h, _a, league_cn)
                if _lh:
                    out.append('  🔴HAF(Step4.6): ✅ ok → λh=%.2f λa=%.2f（乘性耦合·%s/%s）'
                               % (_lh, _la, _h, _a))
                else:
                    out.append('  🔴HAF(Step4.6): ⚠️ 无数据(原因: 该联赛场地子集缺失)')
            else:
                _miss = [x for x, y in ((home, _h), (away, _a)) if not y]
                out.append('  🔴HAF(Step4.6): ⚠️ 无数据(原因: 队伍不在 139 队档案内·%s)'
                           % ('/'.join(_miss) or '别名未命中'))
    except Exception as _e:
        out.append('  🔴HAF(Step4.6): ⚠️ 无数据(原因: 模块不可用·%s)' % str(_e)[:50])

    # ── ELO(C26/修正41) ──
    try:
        _ep = _tp.find_table('clubelo_20261016.json')
        if not _ep:
            out.append('  🔴ELO(修正41): ⏭️ 不触发(原因: clubelo 本地快照缺失)')
        elif league_cn not in EU5:
            out.append('  🔴ELO(修正41): ⏭️ 不触发(原因: 本联赛不在覆盖域·clubelo 快照仅五大联赛·%s)' % league_cn)
        else:
            # 🔴2026-10-17(P1): 原只输出「由执行者按队查」→ 执行者无入口 → 实际从未消费。
            #   现按队名查 clubelo 快照，直接给出 Elo 差与档位（查不到则三态标注）。
            _elo = _j.load(open(_ep, encoding='utf-8')).get('leagues', {}).get(league_cn, {})
            _pool = {}
            for _t in (_elo.get('teams') or []):
                _pool[(_t.get('name') or '').strip()] = _t.get('elo')
            _emap = {}
            try:
                _mp2 = _tp.find_table('team_name_mapping_2025-26.json')
                if _mp2:
                    for _t in (_j.load(open(_mp2, encoding='utf-8')).get('teams') or []):
                        if _t.get('cn') and _t.get('en'):
                            _emap[_t['cn']] = _t['en']
            except Exception:
                pass
            # 🔴2026-10-17(P1): 名称解析原本"单次精确匹配"→ clubelo 命名与 Mapping 命名
            #   不一致的队（Stuttgart/VfB Stuttgart、Roma/AS Roma、Genoa/Genoa CFC、
            #   Bologna/Bologna FC、Mainz/Mainz 05、Inter Milan/Internazionale…）一律落空。
            #   现改为「候选名集合 + 归一化(去重音/去俱乐部前后缀) + 包含匹配」三级解析。
            _cand = {'曼彻斯特城': ['Man City', 'Manchester City'],
                     '巴黎圣日耳曼': ['Paris SG', 'Paris Saint-Germain', 'Paris'],
                     '拜仁慕尼黑': ['Bayern Munich', 'Bayern München', 'Bayern'],
                     '莱比锡红牛': ['RB Leipzig', 'Leipzig'], 'RB莱比锡': ['RB Leipzig', 'Leipzig'],
                     '纽卡斯尔联': ['Newcastle', 'Newcastle United'],
                     '皇家贝蒂斯': ['Real Betis', 'Betis'], '毕尔巴鄂竞技': ['Ath Bilbao', 'Athletic Club'],
                     '国际米兰': ['Inter', 'Internazionale'], '沙尔克04': ['Schalke 04', 'Schalke'],
                     '汉堡': ['Hamburg', 'Hamburger SV'], '阿森纳': ['Arsenal'],
                     '曼彻斯特联': ['Man United', 'Manchester United'],
                     '托特纳姆热刺': ['Tottenham'], '布伦特福德': ['Brentford'],
                     '埃弗斯堡': ['Elversberg'], '赫尔城': ['Hull'],
                     '多特蒙德': ['Dortmund'], '美因茨': ['Mainz'], '奥格斯堡': ['Augsburg'],
                     '斯图加特': ['Stuttgart'], '罗马': ['Roma'], '热那亚': ['Genoa'],
                     '博洛尼亚': ['Bologna'], '巴伦西亚': ['Valencia'], '瓦伦西亚': ['Valencia'],
                     '柏林联合': ['Union Berlin'], '富勒姆': ['Fulham'], '利物浦': ['Liverpool'],
                     '比利亚雷亚尔': ['Villarreal'], '埃尔切': ['Elche']}

            def _norm(s):
                s = (s or '').lower()
                for _a, _b in (('ä', 'a'), ('ö', 'o'), ('ü', 'u'), ('é', 'e'), ('í', 'i'),
                               ('á', 'a'), ('ó', 'o'), ('ñ', 'n'), ('ç', 'c'), ('è', 'e')):
                    s = s.replace(_a, _b)
                for _w in ('fc ', 'fc', 'cf ', 'ac ', 'as ', 'ssc ', 'ss ', 'sc ', '1. ', 'afc ',
                           'club ', 'calcio ', '.', '-', ' ', "'"):
                    s = s.replace(_w, '')
                return s

            _pool_norm = {}
            for _k in _pool:
                _pool_norm.setdefault(_norm(_k), _k)

            def _elo_of(cn):
                _names = [cn, _emap.get(cn)] + _cand.get(cn, [])
                for nm in _names:
                    if nm and nm in _pool:
                        return _pool[nm], nm
                for nm in _names:
                    if not nm:
                        continue
                    _hit = _pool_norm.get(_norm(nm))
                    if _hit:
                        return _pool[_hit], _hit
                for nm in _names:
                    if not nm or len(_norm(nm)) < 4:
                        continue
                    _n = _norm(nm)
                    for _pk, _orig in _pool_norm.items():
                        if _n in _pk or _pk in _n:
                            return _pool[_orig], _orig
                return None, None

            _eh, _hn = _elo_of(_home_cn)
            _ea, _an = _elo_of(_away_cn)
            if _eh and _ea:
                _d = _eh - _ea
                out.append('  🔴ELO(修正41): ✅ 快照 %s → %s %s %.0f vs %s %s %.0f | ELO差 %+.0f'
                           % (_elo.get('date') or '', home, _hn, _eh, away, _an, _ea, _d))
                if abs(_d) >= 30:
                    out.append('    → |ELO差|>=30: 触发低赔-ELO背离纪律（低赔方向≠ELO强方→该向降1档+强制2向覆盖）'
                               '·执行者须按 Step5 对照→强方=%s' % (home if _d > 0 else away))
                else:
                    out.append('    → |ELO差|<30: ELO 不构成方向依据（仅背景·不调档）')
            else:
                out.append('  🔴ELO(修正41): ⚠️ 无数据(原因: 队伍不在 clubelo 快照·%s/%s)'
                           % (home if not _eh else 'ok', away if not _ea else 'ok'))
    except Exception as _e:
        out.append('  🔴ELO(修正41): ⚠️ 无数据(原因: %s)' % str(_e)[:50])

    # ── xG(C27/SK-xg-depth) ──
    try:
        _xp = _tp.find_table('xg_La_liga_2026.json')
        if not _xp:
            out.append('  🔴xG(SK-xg-depth): ⏭️ 不触发(原因: understat 本地快照缺失)')
        else:
            # 🔴2026-10-17(P1): 原实现只有 4 条硬编码队名 → 覆盖判据与实际可用队伍不符
            #   （西甲全 20 队都在快照里，却被判「该队不在快照」）。改为按 title 精确匹配 +
            #   直接算滚动 xG/xGA（近 8 场·防泄露·rolling_features 与 xg_depth_upgrade 同源）。
            _xd = _j.load(open(_xp, encoding='utf-8'))
            _pool_xg = {v.get('title'): v for v in (_xd.get('teams') or {}).values() if v.get('title')}
            _xn = {'皇家贝蒂斯': 'Real Betis', '巴塞罗那': 'Barcelona', '毕尔巴鄂竞技': 'Athletic Club',
                   '马德里竞技': 'Atletico Madrid', '西班牙人': 'Espanyol', '巴伦西亚': 'Valencia',
                   '瓦伦西亚': 'Valencia', '比利亚雷亚尔': 'Villarreal', '埃尔切': 'Elche',
                   '皇家社会': 'Real Sociedad', '塞维利亚': 'Sevilla', '赫塔费': 'Getafe',
                   '阿拉维斯': 'Alaves', '奥萨苏纳': 'Osasuna', '莱万特': 'Levante',
                   '塞尔塔': 'Celta', '拉约': 'Rayo Vallecano'}
            _xh = _pool_xg.get(_xn.get(_home_cn, _home_cn))
            _xa = _pool_xg.get(_xn.get(_away_cn, _away_cn))
            if not _xh:  # 归一化回退（去重音/包含匹配）
                _n0 = _norm(_home_cn)
                for _tk, _tv in _pool_xg.items():
                    if _n0 and (_n0 in _norm(_tk) or _norm(_tk) in _n0):
                        _xh, _xa = _tv, _xa
                        _home_cn = _tk
                        break
            if not _xa:
                _n1 = _norm(_away_cn)
                for _tk, _tv in _pool_xg.items():
                    if _n1 and (_n1 in _norm(_tk) or _norm(_tk) in _n1):
                        _xa, _xh = _tv, _xh
                        _away_cn = _tk
                        break
            if league_cn == '西甲' and _xh and _xa:
                import xg_depth_upgrade as _XG
                _allxga = [h.get('xGA', 0) for v in _pool_xg.values() for h in (v.get('history') or [])[:8]]
                _avg = sum(_allxga) / len(_allxga) if _allxga else 1.6
                _fa = _XG.rolling_features([(h['xG'], h['xGA'], h['h_a'] == 'h')
                                            for h in _xh['history'][-8:]], n=8)
                _fb = _XG.rolling_features([(h['xG'], h['xGA'], h['h_a'] == 'h')
                                            for h in _xa['history'][-8:]], n=8)
                _lh = _fa['xg_mean'] * (_fb['xga_mean'] / _avg)
                _la = _fb['xg_mean'] * (_fa['xga_mean'] / _avg)
                out.append('  🔴xG(SK-xg-depth): ✅ ok → %s xG %.2f/xGA %.2f (σ%.2f) | %s xG %.2f/xGA %.2f (σ%.2f)'
                           % (home, _fa['xg_mean'], _fa['xga_mean'], _fa['xg_std'],
                              away, _fb['xg_mean'], _fb['xga_mean'], _fb['xg_std']))
                out.append('    → λ0(xG·相对防守修正·联赛均xGA %.2f) = 主 %.2f / 客 %.2f (总 %.2f)'
                           % (_avg, _lh, _la, _lh + _la))
            elif league_cn == '西甲':
                out.append('  🔴xG(SK-xg-depth): ⚠️ 无数据(原因: 队伍不在西甲 xG 快照·%s/%s)'
                           % (home if not _xh else 'ok', away if not _xa else 'ok'))
            else:
                out.append('  🔴xG(SK-xg-depth): ⏭️ 不触发(原因: 本联赛(%s)不在覆盖域·understat 本地快照仅西甲)' % league_cn)
    except Exception as _e:
        out.append('  🔴xG(SK-xg-depth): ⚠️ 无数据(原因: %s)' % str(_e)[:50])
    return out


def _parse_cross_book(txt_path):
    """从输入头解析跨机构读数 → dict 或 None

    🔴2026-10-17(P1-4): SKILL 曾宣称 calc_all「必传 --max_h/--max_d/--max_a」，
       但脚本从未实现 → 修正35 机构 Max 分歧**从未被消费**（实测传参只得到「未知参数(已忽略)」）。
       而真实输入头**已经带**这一行，可自动解析，不需要人工传参:
         跨机构即盘：348 家 · 最高价 3.4/3.75/2.48 · 最低价 2.72/3.0/1.65
       故改为自动解析（无需 --max_*），缺失时三态标注。
    """
    import re as _cr
    try:
        text = open(txt_path, encoding='utf-8').read()
    except Exception:
        return None
    m = _cr.search(r'(\d+)\s*家[^\n]*?最高价\s*([\d.]+)\s*/\s*([\d.]+)\s*/\s*([\d.]+)'
                   r'(?:[^\n]*?最低价\s*([\d.]+)\s*/\s*([\d.]+)\s*/\s*([\d.]+))?', text)
    if not m:
        return None
    try:
        return {'n_books': int(m.group(1)),
                'max': [float(m.group(2)), float(m.group(3)), float(m.group(4))],
                'min': [float(m.group(5)), float(m.group(6)), float(m.group(7))]
                if m.group(5) else None}
    except (TypeError, ValueError):
        return None


def cross_book_divergence(txt_path, eu=None, explicit_max=None):
    """跨机构分歧（修正35）: (Max − 中位)/中位 · 输出三向分歧 + 方向判读

    口径与 bookmaker_spread 通道 C 一致：(Max − 基准)/基准。
    基准优先用传入的欧盘（--eu·当前定价），无则用最低价与最高价的中点。
    返回输出行列表（**永远非空**·缺失走三态）。
    """
    cb = _parse_cross_book(txt_path)
    out = []
    # 显式 --max_* 优先（若调用方仍手传）
    base = None
    if eu:
        try:
            _e = [float(x) for x in str(eu).split(',')]
            if len(_e) == 3 and all(x > 1 for x in _e):
                base = _e
        except (TypeError, ValueError):
            base = None

    if cb is None and explicit_max is None:
        out.append('  🔴跨机构分歧: ⚠️无数据(原因: 输入文件未提供「最高价/最低价」行·未传 --max_h) '
                   '→ 修正35 不触发(禁以单家冒充跨机构)')
        return out

    mx = explicit_max or (cb.get('max') if cb else None)
    mn = (cb.get('min') if cb else None)
    nb = (cb.get('n_books') if cb else None)
    if not mx:
        out.append('  🔴跨机构分歧: ⚠️无数据(原因: 最高价不可解析) → 修正35 不触发')
        return out
    if base is None:
        if mn:
            base = [(a + b) / 2 for a, b in zip(mx, mn)]
        else:
            out.append('  🔴跨机构分歧: ⚠️无数据(原因: 无基准价·既无 --eu 也无最低价) → 修正35 不触发')
            return out

    legs = ('主', '平', '客')
    devs = []
    for i, lab in enumerate(legs):
        d = (mx[i] - base[i]) / base[i] * 100 if base[i] else 0.0
        devs.append(d)
    detail = ' · '.join('%s%+.1f%%' % (legs[i], devs[i]) for i in range(3))
    out.append('  🔴跨机构分歧(修正35): %s%s | 最高价 %s | 基准 %s' % (
        ('%d 家 · ' % nb) if nb else '', detail,
        '/'.join('%g' % x for x in mx),
        '/'.join('%.2f' % x for x in base)))
    _maxdev = max(abs(d) for d in devs)
    if _maxdev < 5:
        out.append('     → Max分歧 %.1f%% < 5%% 档: 低可信(实测该档准确率 44.5%%·降级)' % _maxdev)
    elif _maxdev > 10:
        out.append('     → Max分歧 %.1f%% > 10%% 档: 方向**更可信**(实测 51.6%%·反直觉·升级参考)' % _maxdev)
    else:
        out.append('     → Max分歧 %.1f%% 落 5-10%% 中性档' % _maxdev)
    _top = max(range(3), key=lambda i: devs[i])
    out.append('     → 偏离最大方向: %s(最高价高出基准 %+.1f%%)·机构在该向给出更高赔付'
               % (legs[_top], devs[_top]))
    return out


def _canonical_log_name(txt_path, league=None):
    """预测日志文件名的唯一规范化入口 → YYYY-MM-DD_HHMM_联赛_主队_vs_客队.json

    🔴2026-10-17(P1-3): 原实现直接沿用输入 txt 基名 → 同场不同分隔符产生重复文件，
      且无参数调用会落 `--help.json`。此函数保证「同一场 → 同一文件」。
    """
    import re as _cr

    def _clean(s):
        s = (s or '').strip()
        s = _cr.sub(r'[\\/:*?"<>|]+', '', s)
        s = _cr.sub(r'\s+', '', s)
        return s

    stem = os.path.splitext(os.path.basename(txt_path))[0]
    try:
        text = open(txt_path, encoding='utf-8').read()
    except Exception:
        text = ''

    mt = _cr.search(r'比赛时间[:：]\s*(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2})', text)
    if mt and all(mt.groups()):
        y, mo, d, hh, mi = mt.groups()
        datepart = '%s-%s-%s_%s%s' % (y, mo, d, hh, mi)
    else:
        m2 = _cr.search(r'(\d{2})-(\d{2})\s+(\d{2}):(\d{2})', stem)
        datepart = ('2026-%s-%s_%s%s' % (m2.group(1), m2.group(2), m2.group(3), m2.group(4))
                    if m2 else 'undated')

    lg = _clean(norm_league(league) or '')
    if not lg:
        m3 = _cr.search(r'赛事[:：]\s*\S*?([\u4e00-\u9fa5]{2,6}(?:联|杯|甲|超|乙))', text)
        lg = _clean(m3.group(1)) if m3 else ''

    home = away = ''
    m4 = _cr.search(r'([^\s()（）]+)\s*[(（]主[)）]\s*[Vv][Ss]\s*([^\s()（）]+)\s*[(（]客[)）]', text)
    if m4:
        home, away = _clean(m4.group(1)), _clean(m4.group(2))

    parts = [datepart]
    if lg:
        parts.append(lg)
    if home and away:
        parts.append('%s_vs_%s' % (home, away))
    else:
        parts.append(_clean(stem) or 'unknown')
    return '_'.join(parts) + '.json'


# ══════════════════════════════════════════════════════════════════════
# 大小球判向 · 单一真源（2026-10-18·ou_dir 口径统一）
# ══════════════════════════════════════════════════════════════════════
# 背景: 本文件曾同时存在两套判向切点 ——
#   ① over_p 概率分类器 (over_p>=54 判大 / <=46 判小)  ← 441 场盲测实际所用
#   ② O2.5 赔率阈值   (<1.90 判大 / >2.10 判小)      ← 代码实际执行
# 在 435 场上实测: 两套规则在**都做出判向的场次**上结果 100% 相同
#   （McNemar 分歧=0）→ 它们只是同一单调刻度上的不同切点，没有"谁更准"之争。
#
# 净收益口径（判对 +1 / 判错 -1 / 不判 0）· 全样本 435 场:
#   A 赔率 1.90/2.10 : 可判 371  净 +101  准确率 63.6%   ← 现行·已保留
#   B 概率 54/46     : 可判 275  净  +85  准确率 65.5%
#   A 的增量全部来自 over_p∈(46,54) 的 100 场"中段"(命中 58%)——
#   该净收益 21% 的二项单侧 p≈0.055，落在显著性边缘，故**不宣称 A 更优**，
#   仅按"用户决策 + 现行行为不变"保留 A。
#
# 🔴 纪律: 判向阈值只在本处定义。任何消费点（打印/校验/下游）一律调用
#   over_under_direction()，禁止内联 1.90/2.10 或 54/46。
OU_BIG_ODDS_MAX = 1.90      # O2.5 <  此值 → 大球（实测 64.9%，n=316）
OU_SMALL_ODDS_MIN = 2.10    # O2.5 >  此值 → 小球（实测 56.4%，n=55）
SMALL_BALL_NEUTRAL = True   # 小球档停判开关（保留：判小球≈随机边缘）

# 分档实证大球率（435 场·用于打印"依据"，随表变化时须同步复核）
OU_BAND_ACTUAL = (
    (1.00, 1.30, 90.0, 10), (1.30, 1.50, 81.8, 22), (1.50, 1.70, 64.7, 156),
    (1.70, 1.90, 60.2, 128), (1.90, 2.10, 60.9, 64), (2.10, 2.30, 41.5, 41),
)


def over_under_direction(o25):
    """O2.5 赔率 → '大球' | '小球' | '中性'（唯一真源·三态）

    边界: 1.90 属中性（开区间右端）、2.10 属中性（开区间左端）。
    缺失/非法 → '中性'（禁默认判大或判小）。
    """
    try:
        o = float(o25)
    except (TypeError, ValueError):
        return '中性'
    if o <= 0:
        return '中性'
    if o < OU_BIG_ODDS_MAX:
        return '大球'
    if o > OU_SMALL_ODDS_MIN:
        return '小球'
    return '中性'


# 🔴 2026-10-18「必核清单可满足性」修复
#   问题：30 项清单里有 5 项在本数据结构下**永远不可能完成**，却仍标「必做」：
#     C21 盈亏矩阵(需 CS 盘·快照未提供)  C23 新闻伤停(分析禁止联网)
#     C24 api-football(禁止联网)  C25 footballcharts(源已废弃)  C30 落盘(需未分发的案例库)
#   后果：清单长期含「做不到的必做项」→ 执行者会开始心里打折，连真该做的也跳。
#   修法：按**本次运行的实际数据来源与配置**动态定三态，禁硬编码 SKIP。
CHECKLIST_NOTE = {
    'C21': 'N/A(原因:快照未提供 CS 比分盘·禁以竞彩让球盘冒充)',
    'C23': 'N/A(原因:分析阶段禁止联网·无伤停源)',
    'C24': 'N/A(原因:分析阶段禁止联网·无官方概率/13家)',
    'C25': 'N/A(原因:footballcharts 域名已失效·降级 understat_xg)',
    'C30': 'N/A(原因:案例库 data/case-library 未随公开版分发)',
}


def gen_checklist(league, eu=None, handi=None, o25=None, is_europe=False, is_top5=False, v6_status=None,
                  offline=True):
    """脚本生成必核清单(附数据状态·LLM照单逐项消费)

    🔴 offline=True（分析阶段恒真·net_policy.for_analysis()）时，依赖联网的项目标 N/A。
    """
    lines = ['', '=' * 70, '【必核清单·脚本生成(2026-09-02·防自我遗漏·LLM逐项执行不可跳过)】', '=' * 70]
    n_na = 0
    for cid, item, cond, src in CHECKLIST:
        if cond == '欧战' and not is_europe:
            lines.append('  %s %-40s [不触发·非欧战]' % (cid, item))
        elif cond == '五大联赛' and not is_top5:
            lines.append('  %s %-40s [不触发·非五大]' % (cid, item))
        elif cid == 'C09' and v6_status:
            lines.append('  %s %-40s [%s]' % (cid, item, v6_status))
        elif cid in CHECKLIST_NOTE:
            # 伤停与 api-football 仅在联网复盘时才可能成立
            na = CHECKLIST_NOTE[cid]
            if cid in ('C23', 'C24') and not offline:
                lines.append('  %s %-40s [必做·源:%s]' % (cid, item, src))
                continue
            n_na += 1
            lines.append('  %s %-40s [%s]' % (cid, item, na))
        else:
            lines.append('  %s %-40s [必做·源:%s]' % (cid, item, src))
    if n_na:
        lines.append('  ⚠️ 上述 %d 项在**本数据结构/本次运行**下不可能完成 → 已标 N/A（不计入完成度·不得为凑清单而编造结论）' % n_na)
    lines.append('  🔴执行纪律: 逐项执行·每项输出数值证据·条件层三态(触发/不触发(原因)/无数据(原因))·无证据=未执行=禁止通过')
    return '\n'.join(lines)

def _extract_cs_bqc(txt_path):
    """提取竞彩txt比分盘/半全场末盘串(评审P0接入·live引擎输入)·多时点取末值
    支持三格式: A胜胜= 等号 / B'发布时间,胜胜'表头 / C纯逗号无表头(2026-09-10·错误13)
    🔴2026-09-07修复: 半全场兼容逗号表头格式——原仅支持 胜胜= 格式致ht源未激活"""
    import re as _re
    try:
        s = open(txt_path, encoding='utf-8').read()
    except Exception:
        return None, None
    cs = {}
    for m in _re.finditer(r'(\d+:\d+)=([\d.]+)', s):
        cs[m.group(1)] = float(m.group(2))
    # CS 补齐逗号表头格式(格式B)——原仅支持 `1:0=` 等号格式，
    # 致逗号表头txt 的 cs={} → live引擎丢失CS源(0.20权重)·Elche vs 皇马实测复现
    if not cs:
        mhc = _re.search(r'发布时间,1:0,2:0', s)
        if mhc:
            _hseg = s[mhc.start():]
            _hnext = _hseg.find('【', 5)
            if _hnext > 0: _hseg = _hseg[:_hnext]
            _hkeys = _hseg.split('\n', 1)[0].split(',')[1:]  # 去掉"发布时间"表头列
            _crows = _re.findall(r'^(\d{4}-\d{2}-\d{2} [\d:]+),(.+)$', _hseg, _re.M)
            if _crows and _hkeys:
                _last = _crows[-1][1].split(',')
                for _i, _k in enumerate(_hkeys):
                    if _i < len(_last) and _re.match(r'^\d+:\d+$', _k.strip()):
                        try: cs[_k.strip()] = float(_last[_i])
                        except Exception: pass
    # 半全场: 优先 胜胜= 格式·否则逗号表头格式(取末数据行)
    bq = {}
    for m in _re.finditer(r'(胜胜|胜平|胜负|平胜|平平|平负|负胜|负平|负负)=([\d.]+)', s):
        bq[m.group(1)] = float(m.group(2))
    if not bq:
        mh = _re.search(r'发布时间,胜胜,胜平,胜负,平胜,平平,平负,负胜,负平,负负', s)
        if mh:
            keys = ['胜胜', '胜平', '胜负', '平胜', '平平', '平负', '负胜', '负平', '负负']
            seg = s[mh.start():]
            # 原 seg 未截断到下一节 → seg_rows[-1] 取到【比分固定奖金】段末行
            # → bq 全错(实测 Elche vs 皇马 bq = CS值 50/90/35/300/100/70/500/300/300)·污染 live引擎 ht源(0.24权重)
            _nxt = seg.find('【', 5)
            if _nxt > 0: seg = seg[:_nxt]
            seg_rows = _re.findall(r'^(\d{4}-\d{2}-\d{2} [\d:]+),(.+)$', seg, _re.M)
            if seg_rows:
                last = seg_rows[-1][1].split(',')
                if len(last) >= 9:
                    for i, k in enumerate(keys):
                        try: bq[k] = float(last[i])
                        except Exception: pass
    # 格式C: 纯逗号无表头数据行(原始粘贴竞彩txt·【半全场】段后时间行直接9值)·映射按固定顺序
    if not bq:
        keys = ['胜胜', '胜平', '胜负', '平胜', '平平', '平负', '负胜', '负平', '负负']
        segm = _re.search(r'【半全场胜平负固定奖金】\s*\n', s)
        if segm:
            _seg_rest = s[segm.end():]
            _nseg = _seg_rest.find('【')
            if _nseg > 0: _seg_rest = _seg_rest[:_nseg]
            seg_lines = [l for l in _seg_rest.split('\n') if l.strip() and _re.match(r'^\d{4}-\d{2}-\d{2}', l)]
            if seg_lines:
                last = seg_lines[-1].split(',')
                if len(last) >= 10:  # 时间+9值
                    for i, k in enumerate(keys):
                        try: bq[k] = float(last[i + 1])
                        except Exception: pass
    cs_s = ','.join('%s=%.2f' % (k, v) for k, v in cs.items()) if cs else None
    bq_s = ','.join('%s=%.2f' % (k, v) for k, v in bq.items()) if bq else None
    return cs_s, bq_s


def _merge_score_candidates(live_cands, handi_cands, handi_weight=0.40):
    """融合live引擎top10与让球分层候选池(2026-09-10·错误5·深盘场候选消费)"""
    if not handi_cands: return live_cands or []
    if not live_cands: return handi_cands
    merged = {}
    for c in live_cands:
        sc = c.get('score', c.get('s', ''))
        p = c.get('prob', c.get('p', c.get('weight', 0))) or 0
        merged[sc] = merged.get(sc, 0) + p * (1 - handi_weight)
    for c in handi_cands:
        sc = c.get('score', '')
        w = c.get('weight', 0) or 0
        merged[sc] = merged.get(sc, 0) + w * handi_weight
    res = [{'score': k, 'weight': v} for k, v in sorted(merged.items(), key=lambda x: -x[1])]
    tot = sum(c['weight'] for c in res)
    if tot > 0:
        for c in res: c['weight'] = round(c['weight'] / tot, 3)
    return res[:5]


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    txt_path = sys.argv[1]
    league = sys.argv[2] if len(sys.argv) > 2 else None
    # 🔴2026-09-15: 第2位若是 '--xxx' 则说明调用方省略了联赛名 → 曾被当作联赛名吞掉(L1 n=40 无保护)
    if league and league.startswith('--'):
        league = None
    try:
        _lf = _tp.find_table('learned_rules.json')   # 🔴2026-09-15: 表在 data/tmp/(原指向 scripts/tmp/ 恒不存在)
        if _lf:
            import json as _lj
            _lr = _lj.load(open(_lf, encoding='utf-8'))
            _hints = [(t, e.get('rule', '')) for t, e in _lr.items() if e.get('status') in ('提示', '待回测验证', '已固化')]
            if _hints:
                print('=' * 70)
                print('⚡ 学习成果提示(历史复盘自动累积·仅提示·判定权在模型)')
                for _t, _r in _hints:
                    print('  [%s] %s' % (_t, _r))
                print('  → 状态: 提示级=复发累积; 待批量回测验证=达门槛; 已固化=回测验证通过')
    except Exception as _le:
        print('  ⚠️学习提示读取失败:', str(_le)[:60])
    # ⚡ L3 误差规则 + L4 CBR + L1 观察（接线·原本定义未调用=存在≠活跃修复）
    try:
        _old2 = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'online_learning')
        if os.path.isdir(_old2):
            import sys as _s3
            _s3.path.insert(0, _old2)
            import json as _jh
            _tf2 = None
            try:
                import txt_features as _tf2m
                _tf2 = _tf2m
            except Exception:
                pass
            _feat2 = {}
            if _tf2:
                try:
                    _feat2, _ = _tf2.extract(txt_path)
                except Exception:
                    _feat2 = {}
            if _feat2:
                try:
                    import error_miner as _em
                    _rs = _em.rules_for(_feat2)
                    if _rs:
                        print('  ⚡ L3 误差规则命中(%d 条·仅提示): %s' % (
                            len(_rs), '; '.join('%s %s mag=%.2f conf=%.2f' % (
                                r['type'], r['action'], r['magnitude'], r['confidence']) for r in _rs[:3])))
                    _cbr = _em.cbr_predict(_feat2)
                    if _cbr.get('enabled'):
                        _p = _cbr.get('direction_probs') or {}
                        print('  ⚡ L4 CBR 案例辅助(%d 例·权重%.0f%%·仅提示): 主%.0f%% 平%.0f%% 客%.0f%%%s' % (
                            _cbr['n_cases'], _cbr['weight'] * 100,
                            (_p.get(1, 0)) * 100, (_p.get(0, 0)) * 100, (_p.get(2, 0)) * 100,
                            ' ⚠️相似案例常高估主胜' if _cbr.get('error_warning') else ''))
                    else:
                        print('  ⚡ L4 CBR 未启用(案例 %d < 10·冷启动)' % _cbr.get('n_cases', 0))
                except Exception as _em2:
                    print('  ⚠️L3/L4 提示失败:', str(_em2)[:60])
                try:
                    import river_models as _rm
                    _m2 = _rm.load_models()
                    _pv = _rm.predict(_m2, _feat2)
                    if _pv.get('direction_probs'):
                        _dp = _pv['direction_probs']
                        print('  ⚡ L1 在线ML(第6源): 主%.0f%% 平%.0f%% 客%.0f%% | 进球λ≈%s' % (
                            _dp.get(1, 0) * 100, _dp.get(0, 0) * 100, _dp.get(2, 0) * 100, _pv.get('goals')))
                        # 学习结果接入预测
                        _l1_degen = False
                        try:
                            _gate = {}
                            _gp = os.path.join(_old2, 'state', 'gate.json')
                            if os.path.exists(_gp):
                                _gate = json.load(open(_gp, encoding='utf-8')).get('L1_online_ml', {})
                            _w = float(_gate.get('weight', 0.10)) if _gate.get('enabled', True) else 0.0
                            if _gate.get('status') == 'degraded':
                                _w = 0.0
                            # 全面审计(L1 退化守卫·P1): 在线ML 实测饱和退化
                            # (max>0.95 / min<1e-6 / 平局恒 0) → 强制权重 0·不参与融合
                            # 否则饱和输出会按权重 0.10 混入 → 把弱共识场硬推成强方向
                            if (max(_dp.values()) > 0.95) or (min(_dp.values()) < 1e-6):
                                print('  🔴L1 退化守卫: 输出饱和(max=%.3f/min=%.6f) → 权重强制 0·不参与融合'
                                      % (max(_dp.values()), min(_dp.values())))
                                _w = 0.0
                                _l1_degen = True
                            _mk = None
                            _mk_src = ''
                            _eu_arg = sys.argv[sys.argv.index('--eu') + 1] if '--eu' in sys.argv else None
                            if _eu_arg:
                                try:
                                    _e3 = [float(x) for x in _eu_arg.split(',')]
                                    _inv = {1: 1 / _e3[0], 0: 1 / _e3[1], 2: 1 / _e3[2]}
                                    _tt = sum(_inv.values())
                                    _mk = {k: v / _tt for k, v in _inv.items()}
                                    _mk_src = '欧盘--eu'
                                except Exception:
                                    _mk = None
                            # 修复(P1-2): 未传 --eu 时用竞彩 txt 末盘去水（自动·不依赖参数）
                            if _mk is None:
                                _oh5, _od5, _oa5 = (_feat2.get('home_odds'), _feat2.get('draw_odds'), _feat2.get('away_odds'))
                                if _oh5 and _od5 and _oa5:
                                    try:
                                        _inv = {1: 1 / float(_oh5), 0: 1 / float(_od5), 2: 1 / float(_oa5)}
                                        _tt = sum(_inv.values())
                                        _mk = {k: v / _tt for k, v in _inv.items()}
                                        _mk_src = '竞彩txt去水'
                                    except Exception:
                                        _mk = None
                            if _mk and (_w > 0 or _l1_degen):
                                # 防过拟合/降噪: 融合「进入判定」需**独立门禁**(默认关·可回滚)
                                # 依据: 融合监测 n=22 → 融合命中8 = 基准命中8(**无增益**);
                                # 且 L1 已 degraded → 融合=市场·无新增信息 → 只提示不进入判定
                                try:
                                    _fdec_gate = json.load(open(os.path.join(_old2, 'state', 'gate.json'), encoding='utf-8')).get('L1_fusion_in_decision', {})
                                except Exception:
                                    _fdec_gate = {}
                                _fdec = bool(_fdec_gate.get('enabled')) and (_w > 0)
                                _fu = {k: _mk[k] * (1 - _w) + _dp.get(k, 0) * _w for k in (0, 1, 2)}
                                _fm = max(_fu, key=_fu.get)
                                _mm = max(_mk, key=_mk.get)
                                _lab = {0: '平', 1: '主胜', 2: '客胜'}
                                _dpp = (_fu[_fm] - _mk[_mm]) * 100
                                print('    🔴融合方向概率(市场%.2f+在线ML%.2f·门禁=%s): 主%.1f%% 平%.1f%% 客%.1f%% → 融合倾向 %s' % (
                                    1 - _w, _w, ('L1退化·权重0(仅记录)' if _l1_degen else _gate.get('status', 'active')),
                                    _fu[1] * 100, _fu[0] * 100, _fu[2] * 100, _lab[_fm]))
                                _mk_gap = (_mk[_mm] - sorted(_mk.values())[-2]) * 100 if len(_mk) == 3 else 0
                                _mk_top = _mk[_mm] * 100
                                if not _fdec:
                                    _why = ('L1 未参与(权重0·退化/降级)' if _w <= 0
                                            else '门禁 L1_fusion_in_decision=关闭(未通过独立回测门禁)')
                                    print('    → 🔴融合**仅提示·不进入判定**: %s → 判定权归【市场+盘口+基本面】(防过拟合/噪声·2026-09-16)' % _why)
                                elif _fm == _mm:
                                    print('    → 融合与市场同向(差%+.1fpp·源=%s)·不改方向建议' % (_dpp, _mk_src))
                                elif abs(_dpp) > 5:
                                    if _mk_top < 45:
                                        print('    → 🔴🔴学习成果进入判定: 市场弱方向(最高%.1f%%<45%%)且融合异向差%.1fpp>5pp → **「%s」进入主方向判定（列为并列主方向）**（门禁已开·弱档+0.99~2.43pp）' % (
                                            _mk_top, abs(_dpp), _lab[_fm]))
                                    else:
                                        print('    → ⚠️融合与市场异向且差 %.1fpp>5pp·市场强方向(%.1f%%≥45%%): 仅置信度降1档(**不参与判定**·强档净优势=0)' % (
                                            abs(_dpp), _mk_top))
                                else:
                                    print('    → 融合与市场异向但差 %.1fpp≤5pp: 视作噪声·不调整' % abs(_dpp))
                                if _fdec and _fm == _mm and _mk_top < 45:
                                    print('    → 🔴学习成果进入判定: 市场弱方向(%.1f%%<45%%)·融合同向强化 → **采纳融合概率作为方向判定依据之一**（门禁已开·弱档优势+0.99~2.43pp）' % _mk_top)
                            elif _w == 0:
                                print('    → 门禁未启用/已降级(权重0)·仅记录不参与融合')
                            else:
                                print('    → 无欧盘去水概率·未做融合(需 --eu 参数)')
                        except Exception as _fe:
                            print('    ⚠️融合计算失败:', str(_fe)[:60])
                except Exception:
                    pass
    except Exception as _l3:
        print('  ⚠️L3/L4/L1 接线失败:', str(_l3)[:60])
    # 📄 预测日志
    try:
        import sys as _sys2
        _oldir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'online_learning')
        if os.path.isdir(_oldir):
            _sys2.path.insert(0, _oldir)
            try:
                import data_bridge as _db
                # 🔴2026-10-18 联网策略（用户指令·唯一真源 net_policy）:
                #   **分析/预测比赛 → 绝对禁止联网**。
                #   原实现留了 --net 开关（默认关但可开）→ 分析期间联网成为可能。
                #   现改为无条件 for_analysis()：恒返回全关，且不接受任何绕过参数。
                #   与 AGENTS.md §0「离线优先」一致；伤停维度按三态标注
                #   「无数据(离线模式·分析禁止联网)」，不再作为联网例外。
                try:
                    if _oldir not in _sys2.path:
                        _sys2.path.insert(0, _oldir)
                    import net_policy as _np
                    _netkw = _np.for_analysis()
                except Exception:
                    _netkw = {'net_injury': False, 'net_odds': False, 'net_form': False}
                # 修复: 原用 _league_cn（392行才定义）→ UnboundLocalError → 每次静默降级 txt(1/8源)
                _lcn = norm_league(league)
                _br = _db.collect(txt_path, _lcn, net=False, **_netkw)
                _feat = _br.get('features') or {}
                _diag = {'detail': (_br.get('rich') or {}).get('txt_detail', {}),
                         'sources': _br.get('status', {}), 'completeness': _br.get('completeness')}
                if not _feat:
                    raise RuntimeError('bridge 无特征')
            except Exception:
                import txt_features as _tf
                _feat, _diag = _tf.extract(txt_path)
                _diag = {'detail': (_diag or {}).get('detail', {}),
                         'sources': {'txt': {'status': 'ok', 'note': 'bridge失败·txt直取', 'ms': 0}},
                         'completeness': '1/8 源可用(bridge降级)'}
            if _feat:
                _plog = os.path.join(_oldir, 'prediction_log')
                os.makedirs(_plog, exist_ok=True)
                import json as _pj
                _pname = _canonical_log_name(txt_path, league)
                _pj.dump({'txt': txt_path, 'features': _feat, 'detail': _diag.get('detail', {}),
                          'sources': _diag.get('sources', {}), 'completeness': _diag.get('completeness'),
                          'analyzed_at': __import__('time').strftime('%Y-%m-%d %H:%M')},
                         open(os.path.join(_plog, _pname), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
                print('  [预测日志] 特征已存: prediction_log/%s (赛果时 --from-log 自动回溯)' % _pname)
    except Exception as _pe:
        print('  ⚠️预测日志写入失败:', str(_pe)[:60])
    # 🧠 在线学习系统状态
    try:
        _ol = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'online_learning', 'state', 'river', 'n.json')
        import json as _oj
        if os.path.exists(_ol):
            _n = _oj.load(open(_ol, encoding='utf-8'))
            print('  [在线学习] L1样本=%s (🔴特征增强后融合验证+0.68pp·z=2.12→权重0.10启用·仅第6源不覆盖判定) L2/L3/L4累积中' % _n.get('direction', 0))
    except Exception:
        pass
    # 解析可选参数
    # 合并(): 原实现 `--eu --handi` 会把 '--handi' 当成 eu 的值 →
    # eu.split(',') 长度≠3 → 现场引擎 ls 未赋值 → 掩盖真实原因。现改为仅当下一个 token 非 '--' 开头才取值。
    eu = handi = o25 = u25 = home_water = elo = inj_h = inj_a = off = None
    # 🔴2026-09-15 修复(Bug1): 加入 '--water' —— calc_v3572 帮助(L70)/README/案例文档全仓只用 --water,
    # calc_all 原先只认 --home_water → 用户按文档传 --water 时被【静默丢弃】, 水位信号恒缺失且零提示
    # (实测 --water 1.84 → 诱阻分类总分1/置信33%; --home_water 1.84 → 总分2/置信67%)。
    # 🔴2026-10-17(P1-4): 纳入 --max_h/--max_d/--max_a —— SKILL 长期宣称「必传」，
    #   但脚本从未识别（传了只得到「未知参数(已忽略)」）。现正式接收：
    #   跨机构分歧**默认从输入头自动解析**，显式传参时以其覆盖。
    _OVFLAGS = ('--eu', '--handi', '--o25', '--u25', '--home_water', '--water', '--elo',
                '--inj_h', '--inj_a', '--off', '--max_h', '--max_d', '--max_a')
    # 🔴2026-10-18: '--net' 已从 --bool 白名单移除 —— 分析阶段禁止联网,
    #   该参数**不再有任何效果**。若用户仍传入, 会被下面的 _unknown 分支显式告警
    #   (而不是静默接收后无效), 避免"传了以为能联网"的误解。
    _BOOLFLAGS = ()
    _ov = {}
    for i, a in enumerate(sys.argv):
        if a in _OVFLAGS:
            _ov[a] = sys.argv[i + 1] if (i + 1 < len(sys.argv) and not sys.argv[i + 1].startswith('--')) else ''
    # 未知参数显式告警(Bug1): 拼错/误用时原先零提示, 计算照跑 → 结论静默降级
    _unknown = [a for a in sys.argv[3:] if a.startswith('--') and a not in _OVFLAGS and a not in _BOOLFLAGS]
    if _unknown:
        print('  ⚠️未知参数(已忽略·不参与计算): %s —— 已知: %s'
              % (' '.join(_unknown), ' '.join(_OVFLAGS + _BOOLFLAGS)))
        if '--net' in _unknown:
            print('  🔴 --net 已废弃: **分析阶段禁止联网**(net_policy.for_analysis 恒全关)。')
            print('     联网策略见 AGENTS.md §0; 复盘需用户明确要求才可联网。')
    # 🔴2026-10-17(P0·不变量)：--eu 必须与输入文件**声明的基线**一致。
    #   历史做法是用同一份 txt 跑澳门与 Pinnacle 两遍（只换 --eu），
    #   于是 txt 里的「机构通道统一基线」与真正参与计算的定价分叉 →
    #   下游任何「基线性质(soft/sharp)」「序列是否=基线」的判断都会失效。
    if eu:
        try:
            _decl = re.search(r'机构通道统一基线\s*=\s*\S*?胜平负即盘[:：]\s*'
                              r'([\d.]+)\s*/\s*([\d.]+)\s*/\s*([\d.]+)', open(txt_path, encoding='utf-8').read())
            if _decl:
                _dv = [float(x) for x in _decl.groups()]
                _ev = [float(x) for x in eu.split(',')]
                if any(abs(a - b) > 0.005 for a, b in zip(_dv, _ev)):
                    print('  🔴基线不一致: --eu %s ≠ 输入声明基线 %s → '
                          '阈值/形态学/L1融合均按 --eu 计算，但 txt 内时序与标签按声明基线'
                          % ('/'.join('%.2f' % x for x in _ev), '/'.join('%.2f' % x for x in _dv)))
                    print('     ↳ 应改为: 每份 txt 只承载一个基线（澳门 / Pinnacle 各生成一份）')
        except Exception:
            pass
    _missing = [_k for _k in ('--eu', '--handi', '--o25', '--water', '--home_water') if _k in _ov and _ov[_k] == '']
    if _missing:
        print('  ⚠️参数无值(被跳过): %s —— 用法: --eu 主,平,客 --handi <让球值> --o25 <O2.5赔率> [--u25 <U2.5赔率>] [--water <主水位1.8-2.1>]'
              % ' '.join(_missing))
    eu = _ov.get('--eu') or None
    handi = _ov.get('--handi') or None
    o25 = _ov.get('--o25') or None
    u25 = _ov.get('--u25') or None
    # --water 为主水位别名(与 --home_water 等价·同 1.8-2.1 欧式标度)
    home_water = _ov.get('--home_water') or _ov.get('--water') or None
    elo = _ov.get('--elo') or None
    inj_h = _ov.get('--inj_h') or None
    inj_a = _ov.get('--inj_a') or None
    off = _ov.get('--off') or None
    print('=' * 70)
    print('calc_all.py — 全覆盖预计算(2026-09-02·步骤遗失结构性根除)')
    # 🔴 2026-10-18：回显输入文件的三条头部信息
    #   实测问题：v259_ingest 写入的「联赛基准键 / 基线性质 / 多机构合并去水」三行
    #   **完全没有进入 calc_all 输出** → 下游代理根本看不到。
    #   这里只做回显（不重算），来源仍是输入文件。
    try:
        _hd = open(txt_path, encoding='utf-8').read()
        for _key in ('🔴联赛基准键', '🔴基线性质', '🔴多机构合并去水'):
            for _ln in _hd.split(chr(10)):
                if _ln.strip().startswith(_key):
                    print('  [输入] ' + _ln.strip())
                    break
    except Exception:
        pass

    print('=' * 70)
    # ① 跑 calc_match 全管道(含修正的run_extensions·净胜档/总进球档已接入)
    # 🔴2026-10-17 修复(P0-1): **参数必须透传**。
    #   原实现只拼 txt_path + league → calc_match 子进程里 --eu/--handi/--o25/--u25/--water
    #   全部缺失 → 依赖欧盘的模块恒走降级分支:
    #     · V5 跨市场分歧 / 有效凯利 → 恒打印「未提供欧盘」(实测 22/22 场)
    #     · 净胜档 margin_candidates → 退回体彩让球L 粒度(见 P0-3)
    #     · 诱阻分类 → 无欧盘参数不触发(见 P0-2)
    # 🔴2026-10-17(P0·反抽水基准)：calc_match 用 argv[2] 去查 LEAGUE_VIG（英文 slug）。
    #   原实现传中文「英超」→ 恒 miss → 落缺省 6.9%（实测 26/26 场）。
    #   现在优先传 vig slug；认不出时退回原名，由 calc_match 显式标「未登记」。
    _vig_key = lg_vig_key(league)
    cmd = [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'calc_match.py'), txt_path]
    if league: cmd.append(_vig_key or league)
    for _flag, _val in (('--eu', eu), ('--handi', handi), ('--o25', o25), ('--u25', u25),
                        ('--water', home_water), ('--elo', elo),
                        ('--inj_h', inj_h), ('--inj_a', inj_a)):
        if _val is not None and str(_val).strip() != '':
            cmd.extend([_flag, str(_val)])
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', timeout=60)
        out = r.stdout
        # 链路优化: calc_match内部从竞彩盘反推O2.5常失败(竞彩txt无大小球盘段)→输出"O2.5未识别"会误导LLM跳过C17档位查表
        # 当调用方显式提供 --o25 时, 用真实档位分布替换该误导行(与calc_match同款格式·消除calc_match段与②量级段的矛盾观感)
        if o25 and out and 'O2.5未识别' in out:
            try:
                sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
                from calc_v3572 import goal_bin_probs as _gbp
                _g = _gbp(float(o25))
                if _g:
                    _tp2 = ''
                    if _g.get('top'):
                        _tp2 = ' | 典型比分:' + ' '.join('%s(%.1f%%)' % (s, pc) for s, pc in _g['top'])
                    _rep = ('  [goalbins] O2.5=%s 总进球档 0-1:%d%% 2球:%d%% 3球:%d%% 4+:%d%% 净3+:%d%%%s (Step6/7量级依据·calc_all注入)' % (
                        o25, round(_g['prob_01']*100), round(_g['prob_2']*100),
                        round(_g['prob_3']*100), round(_g['prob_4']*100), round(_g['net3']*100), _tp2))
                    out = out.replace('  [goalbins] O2.5未识别->不触发', _rep)
            except Exception:
                pass
        print(out)
        if r.stderr: print('⚠️calc_match stderr:', r.stderr[:200])
    except Exception as e:
        print('⚠️calc_match运行失败:', e)
    # ② 附加参数驱动的计算(欧亚综合·诱阻分类·量级)
    print('=' * 70)
    print('【欧亚综合+诱阻识别+量级(2026-09-02·direction_full新机制)】')
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from calc_v3572 import direction_full, match_classifier, handicap_intent_analyzer, goal_bin_probs
        if eu:
            parts = eu.split(',')
            if len(parts) == 3:
                oh, od, oa = map(float, parts)
                hs = float(handi) if handi else None
                hw = float(home_water) if home_water else None
                # 修复(P1·参数缺失致功能静默降级·与 F3/F5 同类):
                # ① draw_group_score: 修正53 分组分(组A-D 去相关后总分) → direction_full 内部
                # 「平局并列/唯一」判定（>=4 唯一 / >=2.5 并列 / >=1.5 / >=1.0 加权）。
                # 原恒用默认 0.0 → **内部并列判定恒不触发**，与 calc_match 段输出的并列建议口径不一致。
                # ② true_handi: 真实实力盘 → match_classifier 的「盘口背离」异常指标（|handi-true|>0.25）。
                # 原恒 None → 该指标恒不参与 → 诱阻分类 total_score 少一维(可能漏判庄家主导盘)。
                _draw_score = 0.0
                try:
                    _mds = re.search(r'总分(\d+(?:\.\d+)?)\s*→', out)
                    if _mds:
                        _draw_score = float(_mds.group(1))
                except Exception:
                    _draw_score = 0.0
                _true_handi = None
                try:
                    from calc_v3572 import true_handicap_calculator as _thc
                    _th, _ = _thc(elo_diff=float(elo) if elo else None, home_adv=0.25,
                                  inj_h=float(inj_h) if inj_h else 0, inj_a=float(inj_a) if inj_a else 0)
                    if _th is not None:
                        _true_handi = -_th   # 符号与 handi 一致(负=主让)·函数返回"正=主让"
                except Exception:
                    _true_handi = None
                dr = direction_full(oh, od, oa, float(o25) if o25 else None, league_div=league, handi=hs, home_water=hw,
                    draw_group_score=_draw_score,
                    inj_score_h=int(inj_h) if inj_h else 0, inj_score_a=int(inj_a) if inj_a else 0,
                    official_dc=float(off) if off else None)
                print('  方向(欧亚综合): %s(%s) | 并列:%s | 诱盘:%s | 提示:%s | 修正53分组分%.1f' % (
                    dr['主方向'], dr['置信度'], dr['并列建议'], dr.get('诱盘信号') or '无', dr.get('执行提示') or '无', _draw_score))
                # 🔴铁胆档（2026-10-18·用户指令）——独立于 conf 的「硬度」标签
                if dr.get('铁胆'):
                    print('  🔴🔴铁胆档: %s' % dr.get('铁胆标签'))
                    print('     ↓ 口径：skew=%s（最高隐含/次高隐含）≥ %g；与信心档(%s)是两个维度' % (
                          dr.get('skew'), __import__('calc_v3572').TIEDAN_SKEW_MIN, dr.get('置信度')))
                    print('     ↓ 实证：439 场实测命中 85.7%（n=49）·阈值已校正（400→450）·分档:400→82.2% / 450→85.7% / 800→90.9%')
                    print('     🔴 铁胆 ≠ 100%：约每 7 场错 1 场，错误绝大多数是「平局」')
                else:
                    print('  铁胆档: %s' % dr.get('铁胆标签'))
                print('  ' + str(dr.get('小概率管理') or ''))
                if hs is not None:
                    cf = match_classifier(oh, od, oa, handi=hs, water=hw, true_handi=_true_handi)
                    if _true_handi is not None:
                        print('  真实实力盘(ELO/伤停推导·参考): 真实%+.2f vs 实盘%+.2f' % (_true_handi, hs))
                    print('  诱阻分类: %s(总分%d·置信%.0f%%)' % (cf['match_type'], cf['total_score'], cf['confidence']*100))
                    if cf['anomaly_details']: print('    异常:', '; '.join(cf['anomaly_details']))
                    try:
                        ia = handicap_intent_analyzer(cf, dr['主方向'], dr.get('诱盘信号'))
                        if ia: print('    意图: %s → %s' % (ia['intent_type'], ia['true_direction']))
                    except Exception:
                        pass  # ia异常不阻断量级/后续(2026-09-09批检修复)
                if o25:
                    gb = goal_bin_probs(float(o25))
                    if gb:
                        _t3 = gb['prob_3'] + gb['prob_4']
                        print('  量级(O25校准分布·148397场实际·🔴禁市场隐含直读): O2.5=%s档%s → 0-1球%.0f%%/2球%.0f%%/3球%.0f%%/4+球%.0f%% | 总3+球%.0f%% 净3+%.0f%%' % (
                            o25, gb['band'], gb['prob_01']*100, gb['prob_2']*100, gb['prob_3']*100, gb['prob_4']*100, _t3*100, gb['net3']*100))
                        if gb.get('top'):
                            print('    典型比分(该档实测top4·候选池优先): %s' % ' '.join('%s(%.1f%%)' % (s, pc) for s, pc in gb['top']))
                        _ps = [gb['prob_01']*100, gb['prob_2']*100, gb['prob_3']*100, gb['prob_4']*100]
                        _span = max(_ps) - min(_ps); _mx = max(_ps)
                        print('    分布跨度%.0fpp(众数%.0f%%): %s' % (_span, _mx,
                            '🔴量级不确定·宽候选池按分布比例覆盖0-1到4+全档·禁锁单中心(147型2:0独锁误判根因)' if _span < 20 else ('中等·锁中心±1档' if _span < 35 else '量级明确·锁中心档')))
                        # 🔴2026-10-17 调整(P1·441场盲测实测): 小球档判向不可用
                        #   ⚠️ 2026-10-18 改正(435场复核·docs/整改复核_2026-10-17_435场证据.md):
                        #     此处原先引用的是 **over_p 概率分类器**(over_p>=54→大 / <=46→小)
                        #     口径的实测数字; 而本函数下面的 _dir 用的是 **O2.5 赔率阈值**。
                        #     两套逻辑在 435 场里对 99 场(22.8%)给出不同判向 → 打印的依据
                        #     不描述实际执行的规则。现改为引用**本实现(赔率阈值)口径**的实测数字。
                        #   · 结论方向未变: 判小球仍不可用(赔率口径 55 场 56.4%，≈随机边缘)，
                        #     仍降级为「中性·不判」。
                        #   (改动落在③展示/判定层，不触碰①输入解析①②计算链)
                        _o = float(o25)
                        _dir = over_under_direction(_o)   # 🔴 单一真源
                        if SMALL_BALL_NEUTRAL and _dir == '小球':
                            print('    🔴大小球判向: **中性·不判**(O2.5=%.2f>%.2f 属小球档)'
                                  % (_o, OU_SMALL_ODDS_MIN))
                            print('       ↳ 依据: 435场实测·O2.5>%.2f 判小球仅 56.4%%(n=55·≈随机边缘)·不可利用'
                                  % OU_SMALL_ODDS_MIN)
                            print('       ↳ 仍然输出量级分布(上方)与总进球区间·供比分候选池使用; 仅**不给出大/小方向**')
                        elif SMALL_BALL_NEUTRAL and _dir == '中性':
                            print('    🔴大小球判向: **中性·不判**(O2.5=%.2f 落在 %.2f-%.2f 中性带)'
                                  % (_o, OU_BIG_ODDS_MAX, OU_SMALL_ODDS_MIN))
                        else:
                            print('    🔴大小球判向: **大球**(O2.5=%.2f<%.2f 属强/中信号档)'
                                  % (_o, OU_BIG_ODDS_MAX))
                            print('       ↳ 依据: 435场实测·O2.5<%.2f 判大球命中 64.9%%(n=316)·分档单调递减'
                                  % OU_BIG_ODDS_MAX)
                            print('         ' + ' / '.join(
                                '%.2f-%.2f→%.1f%%' % (lo, hi, pct) for lo, hi, pct, _ in OU_BAND_ACTUAL[:4]))
                        if float(o25) >= 2.3:
                            print('    🔴档≥2.3(总3+球%.0f%%≥1/3): 勿判强小球·对攻/防线伤停(影响分>=4)上场总进球中心上调1档·候选池强制含3:2/2:3对攻比分' % (_t3*100))
                        elif float(o25) <= 1.7:
                            print('    🔴档≤1.7(4+球%.0f%%): 大球强·但对手摆大巴/降级死守+主队控场→中心下调(保留0:0/1:0小球出口·case134教训)' % (gb['prob_4']*100))
    except Exception as e:
        print('  ⚠️欧亚综合计算失败:', e)
    # ③ 必核清单(脚本生成)
    _league_cn = norm_league(league)
    is_eu = _league_cn in ('欧冠', '欧联', '欧协联')
    is_top5 = _league_cn in ('英超', '西甲', '意甲', '德甲', '法甲')
    # 审计修复(P1-4·审计): 联赛基准自动输出(league_table.json·大球率/平局率/本场档位H-D-A) — 原靠人工记→易漏「Step0-6 联赛校准缺基准」→ 脚本化零遗漏(审计项0-6·硬核④平局基准自动满足)
    if is_top5:
        try:
            _ltp = _tp.find_table('league_table.json')   # 🔴2026-09-15: 表在 data/tmp/(原指向 scripts/tmp/ → 恒"读取失败·降级人工查表")
            if not _ltp:
                raise FileNotFoundError('league_table.json 未找到 — 应位于 data/tmp/')
            _lt = json.load(open(_ltp, encoding='utf-8'))
            _lk = next((k for k in _lt if k.startswith(_league_cn)), None)
            if _lk:
                _lv = _lt[_lk]
                print('  🔴联赛基准(%s·league_table.json): 大球率 %.1f%% · 平局率 %.1f%%' % (_league_cn, _lv.get('大球率', 0), _lv.get('平局率', 0)))
                if eu:
                    _euh = float(eu.split(',')[0])
                    _bd = '<1.3' if _euh < 1.3 else ('1.3-1.5' if _euh < 1.5 else ('1.5-1.8' if _euh < 1.8 else ('1.8-2.1' if _euh < 2.1 else ('2.1-2.5' if _euh < 2.5 else ('2.5-3.0' if _euh < 3.0 else '3.0-3.5')))))
                    _pp = (_lv.get('主胜档→H/D/A') or {}).get(_bd)
                    if _pp:
                        print('    本场主胜档 %s → H %.1f%% / D %.1f%% / A %.1f%%(查表禁凭记忆)' % (_bd, _pp[0], _pp[1], _pp[2]))
                _ct = _lv.get('比分Top5')
                if _ct:
                    print('    联赛比分Top5: %s' % (_ct if isinstance(_ct, str) else ' '.join(map(str, _ct))))
        except Exception as _e:
            print('  (联赛基准读取失败: %s·降级人工查表)' % _e)
    # 🔴2026-10-17 修复(P2-1): C13/C26/C27 先行层三态统一声明（恒出现·缺失写原因）
    try:
        for _ln in _layer_state_lines(txt_path, _league_cn, eu=eu, o25=o25, handi=handi):
            print(_ln)
    except Exception as _ls_err:
        print('  🔴先行层三态: ⚠️ 声明生成失败(%s)' % str(_ls_err)[:60])
    # 🔴2026-10-17 修复(P1-4): 跨机构分歧（修正35）自动解析输入头·无需 --max_*
    try:
        for _ln in cross_book_divergence(txt_path, eu=eu,
                                         explicit_max=(_ov.get('--max_h') and None)):
            print(_ln)
    except Exception as _cb_err:
        print('  🔴跨机构分歧: ⚠️解析失败(%s) → 修正35 不触发' % str(_cb_err)[:60])
    # 🔴2026-10-17 修复(P1-2): 伤停维度**三态强制留痕**。
    #   SKILL 要求伤停缺失时输出「🔴伤停影响分(判定铁依据·缺失)」，但脚本层从无落点
    #   → 实测 0/23 场有该行 → 违反「禁止静默跳过」/「没做也不说」。
    #   分析阶段禁止联网（AGENTS.md §0），故缺失原因恒为「分析禁止联网」。
    _inj_given = (inj_h is not None and str(inj_h).strip() != '') or \
                 (inj_a is not None and str(inj_a).strip() != '')
    if _inj_given:
        print('  🔴伤停影响分(判定铁依据·已提供): H=%s / A=%s → 置信度合成**含**伤停维度' % (
            inj_h or '0', inj_a or '0'))
    else:
        print('  🔴伤停影响分(判定铁依据·缺失·原因:分析禁止联网·net_policy.for_analysis 恒全关) '
              '→ 伤停维度不可用·置信度合成**不含**伤停维度·铁则32/修正58 不触发')
    # 🔴 V6 硬门：从输入文件的「时点新鲜度」行取真值，不得默认「必做」
    _v6_status = None
    try:
        _fmk = re.search(r'距开赛\s*([\d.]+)\s*分钟', open(txt_path, encoding='utf-8').read())
        if _fmk:
            _m6 = float(_fmk.group(1))
            # 三档必须与 calc_match 一致：LIVE ≤90 / SEMI 90-180 / STALE >180
            if _m6 <= 90:
                _v6_status = '✅ 临场·可判定(距开赛 %.0f 分钟)' % _m6
            elif _m6 <= 180:
                _v6_status = '❓ 弱门·仅弱参考(距开赛 %.0f 分钟)' % _m6
            else:
                _v6_status = '❌ 硬门拒绝(距开赛 %.0f 分钟·非临场·禁引用)' % _m6
        else:
            _v6_status = '❌ 不适用(输入未声明新鲜度)'
    except Exception:
        _v6_status = None
    print(gen_checklist(league, is_europe=is_eu, is_top5=is_top5, v6_status=_v6_status))
    print('=' * 70)
    # ④ 现场比分引擎(评审P0修复半场反推/CS深度/5源融合实际接入·脚本计算LLM消费)
    if eu:
        print('=' * 70)
        print('🔴现场比分引擎(live_score_engine·多源动态融合·主锚建议=脚本Top1·LLM确认):')
        ls = None  # 🔴2026-09-15合并(源自workbuddy): 欧盘参数异常时下游 ls 引用防 UnboundLocalError
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from live_score_engine import analyze_live
            _p3 = eu.split(',')
            if len(_p3) == 3:
                _oh, _od, _oa = map(float, _p3)
                _o25v = float(o25) if o25 else None
                if not u25: print('  ⚠️未传 --u25 → 大小球约束为单侧(O25)·建议补传 Under2.5 赔率')
                _hsv = float(handi) if handi else None
                _cs, _bq = _extract_cs_bqc(txt_path)
                # 🔴2026-10-17(第二轮): 把方向引擎结论传给现场引擎，使「锚 vs 方向」可被脚本自查
                _dirv = (dr or {}).get('主方向') if isinstance(locals().get('dr'), dict) else None
                ls = analyze_live(_oh, _od, _oa, _o25v, u25=(float(u25) if u25 else None), handi=_hsv,
                                  cs_odds=_cs, bqc_odds=_bq, direction=_dirv)
                if ls.get('status') == 'ok':
                    print('  λ: 主%s 客%s 总%s | 数据源: %s' % (
                        ls['lambda']['home'], ls['lambda']['away'], ls['lambda']['total'], ls['sources_used']))
                    print('  动态权重: %s' % ls['dynamic_weights'])
                    print('  Top5比分: %s' % ' | '.join('%s(%.1f%%)' % (x['score'], x['prob']) for x in ls['top10'][:5]))
                    # 🔴🔴 2026-10-18 【裁决规则已撤销】
                    #   原规则（用户指令 2026-10-17）：两引擎冲突时以多源聚合为准。
                    #   撤销依据：**439 场实测**（batch_{2_5_8,74,140,203}）
                    #     · 裁决生效 34 场 → 改对 11 / 改错 16 / 都错 7 → **净 -5 场**
                    #     · 方向命中：裁决后 59.0% vs 价格引擎 59.9%  → **-0.9pp**
                    #     · 分 gap 看：gap 3-5pt 聚合对 9/价格对 12；gap 5-10pt 聚合 2/价格 4
                    #       → **每个区间价格引擎都更准**，加严门槛也救不回来
                    #   结论：该规则已被数据证伪 → 回退到「方向铁依据 = direction_full」（AGENTS §5.5）。
                    #   🔴 聚合仍作**对照信号**输出（不影响方向），冲突时标注「仅供参考」。
                    try:
                        _agr = ls.get('聚合') or ls.get('aggregated') or {}
                        _av = [_agr.get('home_win'), _agr.get('draw'), _agr.get('away_win')]
                        _pv = [float(str(x).replace('%', '')) for x in _av if x is not None]
                        if len(_pv) == 3:
                            _ORDER = ['主胜', '平局', '客胜']
                            _i_top = max(range(3), key=lambda i: _pv[i])
                            _agg_dir = _ORDER[_i_top]
                            _gap = _pv[_i_top] - sorted(_pv)[-2]
                            _price_dir = _dirv
                            print('─' * 70)
                            print('🔴多源聚合对照（方向仍以 direction_full 为准）')
                            print('  价格引擎(direction_full): %s  ↔  多源聚合: %s(%.1f%%)' % (
                                _price_dir, _agg_dir, _pv[_i_top]))
                            print('  聚合分布: 主 %.1f%% / 平 %.1f%% / 客 %.1f%%  ·  首两向 gap %.1fpt  ·  数据源: %s' % (
                                _pv[0], _pv[1], _pv[2], _gap, ls.get('sources_used')))
                            if _agg_dir == _price_dir:
                                print('  → 两引擎一致')
                            else:
                                print('  → ⚠️ 两引擎分歧（gap %.1fpt）——**仅供参考，不改方向**' % _gap)
                                print('     依据：439 场实测证明「以聚合为准」净收益 -5 场（59.0%% vs 59.9%%）→ 规则已撤销')
                                print('     保留：若你有独立证据证明本场聚合更可信，可人工覆盖并标注理由')
                            print('─' * 70)
                    except Exception as _arb_e:
                        print('  ⚠️聚合对照段异常: %s' % str(_arb_e)[:80])
                    print('  🔴主锚建议: %s | 次锚建议: %s(比分锚定起点·LLM综合本场基本面确认·禁机械照搬)' % (
                        ls['top10'][0]['score'], ls['top10'][1]['score']))
                # 市场净胜期望档（用户建议"按市场信号查表"·回测: 市场定净胜档±1球68.3%）
            try:
                _eu_f = [float(x) for x in (eu if isinstance(eu, (list, tuple)) else str(eu).split(','))]
                _inv = {'H': 1/_eu_f[0], 'D': 1/_eu_f[1], 'A': 1/_eu_f[2]}
                _t = sum(_inv.values())
                _p = {k: v/_t for k, v in _inv.items()}
                _en = _p['H']*1.35 + _p['A']*(-1.35) + _p['D']*(-0.05)
                _band = ('H3+' if _en >= 1.8 else 'H2' if _en >= 0.9 else 'H1' if _en >= 0.35
                         else 'D0' if _en >= -0.35 else 'A1' if _en >= -0.9 else 'A2' if _en >= -1.8 else 'A3+')
                print('  🔴市场净胜期望档: %s (期望净胜 %+.2f球) → 查表/净胜档应以本档为基准(与方向判定交叉核对)'
                      % (_band, _en))
            except Exception:
                pass
        # 锚-量级一致性告警消费（用户指出"判大球却锚1:1"）
            if ls and ls.get('status') == 'ok':
                for _w in (ls.get('warnings') or []):
                    if '锚-量级矛盾' in _w:
                        print('  ' + _w)
                        print('  → 🔴执行要求: 在下方市场约束内自行定锚（禁机械照搬 Top1）·并回查方向/净胜档/BTTS 一致性')
                if ls.get('magnitude_rerank'):
                    print('  [量级重排] %s' % ls['magnitude_rerank'])
                if ls.get('market_anchor_check'):
                    _amc = ls['market_anchor_check']
                    # 🔴2026-10-17(P1-1 消费端同步): 措辞由「建议锚」改为「约束 + 违反项」。
                    #   脚本只给约束事实，取哪个锚由 LLM 决定（SKILL 禁机械照搬）。
                    if _amc['ok']:
                        print('  🔴锚-市场一致性: ✅ 当前锚均落在市场约束内 | 市场净胜期望档 %s(净胜%+.2f球)'
                              % (_amc['band'], _amc['exp_net'] or 0))
                    else:
                        print('  🔴锚-市场一致性: ⚠️ 有锚越界 | 市场净胜期望档 %s(净胜%+.2f球)'
                              % (_amc['band'], _amc['exp_net'] or 0))
                        _ct = _amc.get('constraints') or {}
                        if _ct:
                            print('     约束: 净胜档∈%s | 总进球%s | %s' % (
                                _ct.get('net_range'),
                                ('≥%s' % _ct['min_total']) if _ct.get('min_total')
                                else (('≤%s' % _ct['max_total']) if _ct.get('max_total') else '不限'),
                                ('禁主胜锚' if _ct.get('forbid_home_anchor')
                                 else ('禁客胜锚' if _ct.get('forbid_away_anchor') else '盘口方向不限'))))
                        for _v in (_amc.get('violations') or []):
                            print('     ❌ %s %s: %s' % (_v.get('slot'), _v.get('score'), _v.get('rule')))
                        if _amc['suggestion']:
                            print('     ↳ 约束内候选**参考**(非必须采用·LLM 自行定锚): %s'
                                  % ' / '.join(_amc['suggestion']))
                    # 🔴方向-锚硬冲突单独高亮（D4 互证失败，不只是单锚越界）
                    for _c in (_amc.get('conflicts') or []):
                        if '方向-锚硬冲突' in _c:
                            print('     🔴 %s' % _c)
                            print('        → 执行要求: 主锚/次锚至少一个须落在「%s」方向内，否则方向与锚无法互证(D4)'
                                  % (_amc.get('constraints', {}).get('direction') or '判定'))
                    if _amc.get('unvalidated'):
                        print('     ⚠️ 净胜期望档来源: %s —— 仅作约束提示·禁与「V6 四象限 22.7 万场」同档引用'
                              % _amc.get('band_note', '未回测经验公式'))
                # 锚可信度分级（案例库157场回测固化·用户要求"运用到模型主体"·output_checker N08）
                try:
                    from prestep_dual import anchor_trust as _at
                    _atv, _atr = _at(_o25v, _hsv)
                    print('  🔴锚可信度(2026-09-13·157场回测): %s — %s' % (_atv, _atr))
                    if _atv.startswith('🔴'):
                        print('     → 🔴执行要求: 仅**比分层**降级(禁把主锚/次锚当高置信输出·改「宽候选池」)'
              '  ―― **方向层不受影响**：439 场实测「比分不可预测」类场次方向命中 **87.1%**(反而最高)')
                except Exception as _e_at:
                    print('  ⚠️锚可信度未计算:', str(_e_at)[:50])
                print('  聚合: 主%s 平%s 客%s | O2.5%s | 置信%s | 不确定: %s' % (
                    ls['aggregated']['home_win'], ls['aggregated']['draw'], ls['aggregated']['away_win'],
                    ls['aggregated']['over25'], ls['confidence'], ls['uncertainty']))
                if ls.get('prior_bin'): print('  先验格: %s(弱平滑≤10%%)' % ls['prior_bin'])
            else:
                print('  ⚠️现场引擎:', (ls.get('message') if ls else '欧盘参数缺失/未启用(见上方提示)'))
        except Exception as e:
            print('  ⚠️现场引擎未执行(降级泊松+查表):', str(e)[:120])
        # 半场推断量级(V3.0方案F1瘦身版·上限验证43.8% vs O25 26.9%·+16.9pp):
        # 9格半全场→半场进球分布→ht_ft_cond 175476场→全场5层(0-1/2/3/4/5+球)·与goal_bin校准分布并列第三源
        try:
            _bq5 = _extract_cs_bqc(txt_path)[1] if eu else None
            if _bq5:
                if isinstance(_bq5, dict):
                    _bq5 = ','.join('%s=%.2f' % (k, v) for k, v in _bq5.items())
                from live_score_engine import extract_ht_goals_layer as _htgl
                _hg = _htgl(_bq5)
                if _hg:
                    _L = _hg['layers']; _hgstr = {k: '%.0f%%' % (v * 100) for k, v in _hg['ht_goals'].items()}
                    _row = '  半场推断量级(9格半全场->5层·上限43.8%%vsO25 26.9%%·置信%s): 半场进球%s -> 全场 0-1球%.0f%%%%/2球%.0f%%%%/3球%.0f%%%%/4球%.0f%%%%/5+球%.0f%%%% | 期望%.2f球' % (
                        _hg['confidence'], _hgstr, _L[0] * 100, _L[1] * 100, _L[2] * 100, _L[3] * 100, _L[4] * 100, _hg['mean_ft'])
                    print(_row.replace('%%%%', '%%').replace('%%', '%'))
                    if _hg['ht_goals']['0'] > 0.5:
                        print('    🔴推断半场0球>50%%: 全场小量级约束(0-1球>=约58%%·禁4+球主锚)')
                    elif _hg['ht_goals']['3'] > 0.25:
                        print('    🔴推断半场3+球>25%%: 大球约束(候选必含4:1/5:0类)')
                    if _hg['confidence'] < 0.5:
                        print('    (半全场分散·推断置信低·仅参考·主判以O25校准分布为准)')
        except Exception:
            pass
        # 让球动态量级(V2.0·9层先验->因子->贝叶斯->动态候选池·禁机械锚·评审标注独立增益待P2回测)
        try:
            _hd = float(handi) if handi else None
            if _hd is not None and abs(_hd) >= 1.5 and eu:
                from handicap_dynamic_magnitude import analyze as _dyn_an
                _eu3 = eu.split(',')
                if len(_eu3) == 3:
                    _dr = '主胜' if float(_eu3[0]) < float(_eu3[2]) else ('客胜' if float(_eu3[0]) > float(_eu3[2]) else '平局')
                    _csd, _bqd = _extract_cs_bqc(txt_path)
                    _bqs = ','.join('%s=%.2f' % (k, v) for k, v in _bqd.items()) if isinstance(_bqd, dict) and _bqd else (_bqd if _bqd else None)
                    _css = ','.join('%s=%.2f' % (k, v) for k, v in _csd.items()) if isinstance(_csd, dict) and _csd else (_csd if _csd else None)
                    _tgs = None
                    _tgtxt = open(txt_path, encoding='utf-8').read()
                    # 审计修复(V3.0·数据格式不匹配): 原只认 '发布时间,0,1,2,...'(无后缀) → 真实竞彩 txt 全部为 '发布时间,0球,1球,2球,...' → F8_总进球盘因子**恒静默失效**（存在≠活跃）→ 已兼容 球 后缀
                    _mh8 = re.search(r'发布时间,0(?:球)?,1(?:球)?,2(?:球)?', _tgtxt)
                    if _mh8:
                        _rows8 = re.findall(r'^(\d{4}-\d{2}-\d{2} [\d:]+),(.+)$', _tgtxt[_mh8.start():], re.M)
                        if _rows8:
                            _vals8 = _rows8[-1][1].split(',')
                            _prs = ['%d=%.2f' % (i, float(_vals8[i])) for i in range(min(8, len(_vals8)))]
                            if len(_prs) >= 5: _tgs = ','.join(_prs)
                    _dyn = _dyn_an(_hd, league=_league_cn, o25=float(o25) if o25 else None,
                                   oh=float(_eu3[0]), od=float(_eu3[1]), oa=float(_eu3[2]),
                                   elo=float(elo) if elo else None,
                                   inj_h=float(inj_h) if inj_h else None,
                                   inj_a=float(inj_a) if inj_a else None,
                                   bqc=_bqs, cs=_css, tg=_tgs, direction=_dr)
                    if _dyn.get('status') == 'no_prior':
                        print('  让球动态量级: 层%s 样本不足无先验(受让3等·降级·由O25校准+live覆盖)' % _dyn.get('layer'))
                    elif _dyn.get('status') == 'ok':
                        _p = _dyn['posterior']
                        print('  让球动态量级(9层先验->因子->贝叶斯): 层%s 先验%.2f->后验%.2f(置信%.2f) 因子: %s' % (
                            _dyn['layer'], _dyn['prior'], _p['magnitude_center'], _p['confidence'],
                            ' '.join('%s:%+.2f' % (k, v) for k, v in _p['factor_contrib'].items())))
                        print('    动态候选池: %s' % ' | '.join('%s(%.0f%%)' % (c['score'], c['weight'] * 100) for c in _dyn['candidates'][:5]))
                    if _dyn.get('status') == 'ok' and abs(_hd) >= 1.5 and ls and ls.get('top10'):
                        _hw = 0.50 if abs(_hd) >= 2.5 else 0.40
                        _mc = _merge_score_candidates(ls.get('top10', []), _dyn['candidates'], _hw)
                        print('    🔴深盘融合候选池(让球分层%.0f%%+live%.0f%%): %s' % (
                            _hw * 100, (1 - _hw) * 100,
                            ' | '.join('%s(%.0f%%)' % (c['score'], c['weight'] * 100) for c in _mc)))
        except Exception as _de:
            print('  让球动态量级未执行:', str(_de)[:80])
    else:
        print('=' * 70)
        print('  ⚠️未传 --eu 主,平,客 → 现场比分引擎不触发: 比分锚定降级纯LLM/查表(非5源融合)·🔴调用必带 --eu 主,平,客(--o25/--handi 同步传)防引擎静默缺')
    # ⑤ 欧战三层校准(P0修复europe_two_leg/group_stage实际接入·subprocess调用非仅文档)
    if _league_cn in ('欧冠', '欧联', '欧协联') and eu:
        print('=' * 70)
        print('🔴欧战三层校准(europe_two_leg/group_stage·赛事分层+赛程阶段+赔率档):')
        try:
            import re as _re5
            _p5 = eu.split(',')
            if len(_p5) == 3:
                _oh5, _od5, _oa5 = float(_p5[0]), float(_p5[1]), float(_p5[2])
                _rnd5 = league
                try:
                    _rm5 = _re5.search(r'(1/8决赛|1/4决赛|半决赛|决赛|资格赛\d|附加赛|联赛阶段|小组赛)', open(txt_path, encoding='utf-8').read())
                    if _rm5: _rnd5 = _rm5.group(1)
                except Exception: pass
                _eu_dir = os.path.dirname(os.path.abspath(__file__))
                if '联赛' in _rnd5 or '小组' in _rnd5:
                    import re as _re5md
                    _md = 4
                    _mmd = _re5md.search(r'第\s*(\d+)\s*轮', open(txt_path, encoding='utf-8').read())
                    if _mmd: _md = int(_mmd.group(1))
                    # 积分txt提取
                    _hp5, _ap5 = 9, 3
                    _ct5 = open(txt_path, encoding='utf-8').read()
                    _hpm5 = re.search(r'主队[^：:\n]{0,6}(?:积分|排名)?[：:]\s*(\d+)', _ct5)
                    _apm5 = re.search(r'客队[^：:\n]{0,6}(?:积分|排名)?[：:]\s*(\d+)', _ct5)
                    if _hpm5: _hp5 = int(_hpm5.group(1))
                    if _apm5: _ap5 = int(_apm5.group(1))
                    _cmd5 = [sys.executable, os.path.join(_eu_dir, 'europe_group_stage.py'), '--home_points', str(_hp5),
                             '--away_points', str(_ap5), '--matchday', str(_md), '--league', _league_cn,
                             '--home_odds', str(_oh5), '--away_odds', str(_oa5)]
                    if handi: _cmd5 += ['--handi', handi]
                    _g5 = json.loads(subprocess.run(_cmd5, capture_output=True, text=True, encoding='utf-8', timeout=30).stdout)
                    print('  类型: 小组赛/瑞士轮 | 战意: 主%s 客%s | 差:%s | 欧战校准主%s 赛事(%s)%s' % (
                        _g5['home_motivation']['level'], _g5['away_motivation']['level'],
                        _g5['motivation_gap']['level'],
                        _g5.get('europe_calibration', {}).get('home_win_adjust', '-'),
                        _g5.get('league_calibration', {}).get('league', '-'),
                        _g5.get('league_calibration', {}).get('home_win_adjust', '')))
                    for _t5 in _g5.get('trap_detection', []):
                        if _t5['severity'] in ('HIGH', 'MEDIUM'):
                            print('  ⚠️诱盘: %s(%s) → %s' % (_t5['type'], _t5['severity'], _t5['action']))
                else:
                    _is_leg2 = '次回合' in open(txt_path, encoding='utf-8').read()
                    _legv = '2' if _is_leg2 else '1'
                    _cmd5 = [sys.executable, os.path.join(_eu_dir, 'europe_two_leg.py'), '--leg', _legv,
                             '--league', _league_cn, '--round', _rnd5]
                    _t5 = json.loads(subprocess.run(_cmd5, capture_output=True, text=True, encoding='utf-8', timeout=30).stdout)
                    _d5 = _t5['direction_adjustment']
                    print('  类型: %s | 校准主%s 平%s 球%s%s | 关键: %s' % (
                        '决赛(中立)' if _t5.get('is_final') else '两回合首回合(%s)' % _rnd5,
                        _d5.get('home_win', _d5.get('home_win(次回合主队)', '-')), _d5['draw'], _d5['goals'],
                        ' | 赛事(%s)%s' % (_t5.get('league_calibration', {}).get('league', '-'), _t5.get('league_calibration', {}).get('note', ''))[:60] if _t5.get('league_calibration') else '',
                        '/'.join(_t5['score_tendency']['key_scores'][:3])))
        except Exception as e:
            print('  ⚠️欧战校准未执行(默认主回合·次回合需手动--first_leg):', str(e)[:100])
    print('🔴LLM执行流程(篇幅过载解药·2026-09-02·分5批聚焦·每批独立完成防过载):')
    print('  批次1 数据批: C01-C03(去水/档位/凯利)+外部源(fetch_all三态) → 输出数据证据')
    print('  批次2 方向批: C04-C16(变动/诱阻/方向/欧亚/诱阻分类/修正53) → 输出方向+置信度+诱盘')
    print('  批次3 比分批: C17-C22(量级/泊松/净胜档/查表/锚定/总进球) → 输出主锚次锚+停止分支')
    print('  批次4 输出批: C28-C29(口径标注+自检22项) → 组装完整输出')
    print('  批次5 落盘批: C30(case_write+raw+check_luopan) + output_checker校验 → 落盘完成')
    print('  🔴每批独立输出·完成一批再下一批·禁跳批·禁一批内赶完(防篇幅过载导致尾部弱化)')
    print('  🔴output_checker.py校验输出完整性·缺失=补齐重跑至全过')

if __name__ == '__main__':
    main()
