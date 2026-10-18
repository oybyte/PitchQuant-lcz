# -*- coding: utf-8 -*-
"""
calc_match.py — V3.5.58 计算脚本（方案1+4：负载超载缓解·计算脚本化）
用途：解析竞彩txt → 一次性算完全部确定性计算，模型只消费结果做判断。
用法：PYTHONIOENCODING=utf-8 python scripts/tmp/calc_match.py <txt路径>
输出：各盘去抽水/隐含概率/凯利/CS-P_i排序/半场三元+45A推导/总进球分布/O2.5映射/方向差距分级
"""
import re, sys, io, os, json

# 2026-09-15 修复(P1): 数据表统一路径解析(真源 data/tmp/) —— 原按 dirname(__file__) 拼表名
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from table_paths import find_table  # noqa: E402

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8') if hasattr(sys.stdout, 'buffer') else sys.stdout

def parse_txt(text):
    """解析竞彩txt各盘，返回 {盘名: [(时间戳, {选项:赔率})]}
    用户txt格式：表头"发布时间,胜,平,负" + 数据行"2026-08-20 09:20:59,1.40,4.15,5.75"（逗号分隔·按表头对齐）"""

    text = re.sub(r'=====([^=]+?)=====', r'【\1】', text)  # 2026-08-31兼容=====盘标题格式(raw防\1八进制)
    lines = text.splitlines()
    sections = {}
    current = None
    headers = None
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # 盘标题（【】包裹）
        m = re.match(r'【([^】]+)】', line)
        if m:
            name = m.group(1)
            if '胜平负' in name and '让球' not in name and '半全场' not in name:
                current = 'spf'
            elif '让球' in name:
                current = 'rq'
                # 审计修复: 保留竞彩让球数/方向(标题"让球:+1"主受让1=客让1·"-1"主让1)——margin候选方向依据
                _mh = re.search(r'让球[:：]?\s*([+-]\d+(?:\.\d+)?)', name)  # 🔴2026-09-11修复: 兼容'让球-1'(无冒号·要求符号)
                sections['_rq_handicap'] = float(_mh.group(1)) if _mh else None
            elif '总进球' in name:
                current = 'zjq'
            elif '半全场' in name:
                current = 'bqc'
            elif '比分' in name:
                current = 'bf'
            else:
                current = None
            sections.setdefault(current, [])
            headers = None
            continue
        # 表头行（发布时间开头 → 定义列名）
        if current and line.startswith('发布时间'):
            parts = [p.strip() for p in line.split(',')]
            headers = parts[1:]  # 去掉"发布时间"
            # 比分盘的表头是"比分固定奖金 时间"标题行（无发布时间表头·用标题时间）
            continue
        # 数据行（时间戳开头）
        ts_match = re.match(r'(\d{4}-\d{2}-\d{2}[ \d:]+)[,\t]?(.*)', line)
        if ts_match and current:
            ts = ts_match.group(1).strip()
            rest = ts_match.group(2).strip()
            if current == 'bf':
                # 比分盘两种格式:
                # ①旧格式: 胜方比分:1:0=10.00,2:0=7.50 或 胜方比分 1:0=10.00(含"胜其它/胜其他"档)
                # ②表头对齐格式(实际主流): 表头"发布时间,1:0,2:0,...,胜其它" + 数据行"09:55:11,18.00,..."
                if '=' in rest and ('比分' in rest or '其他' in rest or '其它' in rest):
                    odds = {}
                    for kv in re.finditer(r'(\d+:\d+)=([\d.]+)', rest):
                        odds[kv.group(1)] = float(kv.group(2))
                    for kv in re.finditer(r'(胜其他|平其他|负其他|胜其它|平其它|负其它)=([\d.]+)', rest):
                        odds[kv.group(1)] = float(kv.group(2))
                    if odds:
                        sections.setdefault(current, []).append((ts, odds))
                elif '=' in rest:
                    odds = {}
                    for kv in re.finditer(r'(\d+:\d+)=([\d.]+)', rest):
                        odds[kv.group(1)] = float(kv.group(2))
                    for kv in re.finditer(r'(胜其他|平其他|负其他|胜其它|平其它|负其它)=([\d.]+)', rest):
                        odds[kv.group(1)] = float(kv.group(2))
                    if odds:
                        sections.setdefault(current, []).append((ts, odds))
                elif headers and len([p for p in rest.split(',') if p.strip()]) >= len(headers):
                    # ②表头对齐格式: rest = "18.00,35.00,..." 按 headers(含1:0/胜其它)对齐
                    vals = [p.strip() for p in rest.split(',')]
                    odds = {}
                    for h, v in zip(headers, vals):
                        try:
                            odds[h] = float(v)
                        except ValueError:
                            pass
                    if odds:
                        sections.setdefault(current, []).append((ts, odds))
                continue
            # 非比分盘：逗号分隔数值·按表头对齐
            if not headers:  # 🔴容错(2026-08-29): 无表头txt→自动用标准列名(用户粘贴常无表头)
                std = {'spf': ['胜','平','负'], 'rq': ['胜','平','负'],
                       'zjq': ['0','1','2','3','4','5','6','7+'],
                       'bqc': ['胜胜','胜平','胜负','平胜','平平','平负','负胜','负平','负负']}
                headers = std.get(current)
            if headers:
                vals = [p.strip() for p in rest.split(',')]
                if len(vals) >= len(headers):
                    odds = {}
                    for h, v in zip(headers, vals):
                        try:
                            odds[h] = float(v)
                        except ValueError:
                            pass
                    if odds:
                        sections.setdefault(current, []).append((ts, odds))
    # 比分盘：合并多行（胜方/平局/负方）为一次快照
    if 'bf' in sections and sections['bf']:
        # 按时间戳分组
        by_ts = {}
        for ts, odds in sections['bf']:
            by_ts.setdefault(ts, {}).update(odds)
        sections['bf'] = sorted([(ts, o) for ts, o in by_ts.items()])
    return sections

# 🔴2026-10-17 修复(P2-3): 弱共识门限**单一真源**。
#   历史上两处写法不一致: calc_match 用 skew<150%，学习成果提示写 skew<130%
#   → 130–150% 区间同场可能「须平局并列」却「不必三向覆盖」，换人执行出两种结论。
#   保留 150%：有 441 场盲测支撑（市场首选仅 36.4–43.0%≈随机）。
#   任何新增规则引用本常量，禁再硬编码 130/150。
WEAK_SKEW_PCT = 150.0
STRONG_SKEW_PCT = 200.0


def dejuice(odds):
    """去抽水：返回 (抽水率, 隐含概率dict)"""
    inv = {k: 1/v for k, v in odds.items()}
    total = sum(inv.values())
    return total - 1, {k: v/total for k, v in inv.items()}

def kelly(odds, prob):
    """凯利指数：赔率 × 隐含概率（>1 有价值）
    🔴注意: 若 prob 来自同一赔率源去水 → odds×p = 1/Σ(1/o) < 1 恒成立（单源凯利恒<1·仅相对排序参考）
    🔴有效凯利 = 竞彩赔率 × 独立源概率(欧盘去水/模型概率·跨市场价值)·需传 external_prob"""
    return {k: odds[k] * prob.get(k, 0) for k in odds}

def main():
    if len(sys.argv) < 2:
        print("用法: python calc_match.py <竞彩txt路径>")
        return
    text = open(sys.argv[1], encoding='utf-8').read()
    secs = parse_txt(text)
    # --eu 欧盘赔率(🔴2026-09-15 上移解析: 胜平负段的 skew 取值来源需先判定。
    # 原在文末 L296 才解析 → skew 恒用竞彩 txt → 同一场竞彩 150% 高共识(可单押)、
    # 欧盘 133% 弱共识(必须并列), 分档随来源翻转, 与模型实际消费的欧盘不一致)
    eu_odds = None
    if '--eu' in sys.argv:
        try:
            eu_odds = sys.argv[sys.argv.index('--eu') + 1]
        except IndexError:
            pass
    # 🔴2026-10-17(P0-3/P0-2): --handi(亚盘线·净胜档唯一依据) 与 --water(水位)
    # 也需在 main 早期取到，供 run_extensions 的净胜档/诱阻分类消费。
    # 原实现只有 calc_all 在自身上下文里用这两个值 → calc_match 子进程里恒为 None。
    def _argval(flag):
        if flag not in sys.argv:
            return None
        i = sys.argv.index(flag)
        if i + 1 >= len(sys.argv) or sys.argv[i + 1].startswith('--'):
            return None
        return sys.argv[i + 1]

    asia_handi = None
    _hv = _argval('--handi')
    if _hv is not None:
        try:
            asia_handi = float(_hv)
        except ValueError:
            asia_handi = None
    water_arg = None
    _wv = _argval('--water') or _argval('--home_water')
    if _wv is not None:
        try:
            water_arg = float(_wv)
        except ValueError:
            water_arg = None
    print("=" * 70)
    print("calc_match.py — V3.5.58 计算脚本（确定性计算·模型只判断）")
    print("=" * 70)

    # 1. 胜平负
    if 'spf' in secs and secs['spf']:
        ts, odds = secs['spf'][-1]
        vig, prob = dejuice(odds)
        # 🔴2026-10-17 修复(第二轮复跑发现·P0): 去水/隐含那一行**必须跟随 --eu**。
        #   原实现恒用竞彩 txt（澳门），传 --eu 时也只打印竞彩口径；
        #   而下方 skew 已按 --eu 取数 → 同一段里「隐含」与「skew」来自两个不同源。
        #   实测布伦特福德 vs 利物浦：澳门基线显示 41.1/23.5/35.4(抽水11.58%)、
        #   Pinnacle 基线也逐字显示 41.1/23.5/35.4，但 skew 却是 39.1/34.4。
        _dv_odds, _dv_src = odds, '竞彩txt'
        if eu_odds:
            try:
                _eo_dv = [float(x) for x in eu_odds.split(',')]
                if len(_eo_dv) == 3 and all(o > 1 for o in _eo_dv):
                    _dv_odds = {'胜': _eo_dv[0], '平': _eo_dv[1], '负': _eo_dv[2]}
                    _dv_src = '欧盘--eu'
            except Exception:
                pass
        vig, prob = dejuice(_dv_odds)
        print(f"\n【胜平负】末盘({ts}): {odds}"
              + (f" | 去水口径={_dv_src}" if _dv_src != '竞彩txt' else ""))
        print(f"  去抽水率: {vig*100:.2f}% → 隐含: 主{prob.get('胜',0)*100:.1f}%/平{prob.get('平',0)*100:.1f}%/客{prob.get('负',0)*100:.1f}%  (源:{_dv_src})")
        # 评审固化·P0-1: 校准后概率（prob_calibration.json·热门低估偏差·禁仅等比例去水）
        try:
            # 2026-09-15 修复(P1): 表真源在 data/tmp/(SKILL.md L18 自述「按 data/tmp/prob_calibration.json 校准」),
            # 原按 dirname(__file__) 拼接 → 表在文档位置时恒读失败 → 被 except 静默吞成"提示"分支, 校准永不生效。
            _cp = find_table('prob_calibration.json')
            if not _cp:
                raise FileNotFoundError('prob_calibration.json 未找到 — 应位于 data/tmp/')
            calib = json.load(open(_cp, encoding='utf-8'))
            # 🔴 2026-10-18 修正（两层问题）：
            #   ① 原实现只对「主胜」查表 → 客胜为热门时校准对象错位；
            #   ② 计算出的 adj 从未真正应用（原代码 ph = _ph 原样赋值）
            #      → 校准行只是显示，概率链/凯利/λ 全部未受影响。
            #   现同时修正：作用于最高隐含方向，且真正写入 prob。
            _prob_raw = dict(prob)  # U0001f534 未校准副本：skew 必须用原始去水比（实测 150%% 边界用例被污染成 176%%）
            _top_dir = max(prob, key=prob.get)
            _top_p = prob[_top_dir]
            adj = 0
            for k, v in calib.items():
                lo, hi = float(k.split('-')[0]), float(k.split('-')[1])
                if lo <= _top_p < hi:
                    adj = v['bias_pp'] / 100
                    break
            _p_before = _top_p
            if adj:
                prob = dict(prob)
                prob[_top_dir] = max(_top_p + adj, 0.01)
                _t = sum(prob.values())
                prob = {k: v / _t for k, v in prob.items()}
            print(f"  🔴校准后热门方向({_top_dir})概率: {_p_before*100:.1f}% + {adj*100:+.1f}pp = "
                  f"{(_p_before+adj)*100:.1f}% → 归一后 {prob[_top_dir]*100:.1f}% "
                  f"(prob_calibration.json·热门低估·已写入去水概率·供凯利/λ反推)")
        except Exception:
            print(f"  🔴提示: 等比例去抽水未校准「赔率理解修正」(深盘热门隐含55-85%实际命中率+2.4~3.3pp·市场低估热门)·方向判定以联赛档位实际概率为主·隐含仅作资金流/背离参考")
        # 方向差距分级（最大两方向差距）+ 🔴skew精确计算
        # 🔴2026-09-15 修复(Bug5): skew 取「实际消费的赔率来源」——传 --eu 时以欧盘为准, 否则竞彩 txt。
        # 原实现恒用竞彩 → 同一场 竞彩 150%(判高共识·可单押) vs 欧盘 133%(弱共识·必须并列),
        # 分档随来源翻转, 与 Step5 实际消费的欧盘不一致。
        _sk_prob, _sk_src = _prob_raw, '竞彩txt'
        if eu_odds:
            try:
                _eo = [float(x) for x in eu_odds.split(',')]
                if len(_eo) == 3 and all(o > 1 for o in _eo):
                    _iv = {'胜': 1 / _eo[0], '平': 1 / _eo[1], '负': 1 / _eo[2]}
                    _tt = sum(_iv.values())
                    _sk_prob, _sk_src = {k: v / _tt for k, v in _iv.items()}, '欧盘--eu'
            except Exception:
                    _sk_prob, _sk_src = _prob_raw, '竞彩txt'
        probs_sorted = sorted(_sk_prob.values(), reverse=True)
        if len(probs_sorted) >= 2:
            gap = (probs_sorted[0] - probs_sorted[1]) * 100
            level = '明确区(>15pt)' if gap > 15 else ('倾向区(10-15pt)' if gap >= 10 else ('微弱区(5-10pt)' if gap >= 5 else '均衡区(<5pt)'))
            top2 = sorted(_sk_prob.items(), key=lambda x: -x[1])[:2]
            print(f"  方向差距(前两方向): {gap:.1f}pt ({top2[0][0]}vs{top2[1][0]}) → {level}")
            # skew = 最高隐含/次高隐含(精确·禁手算): <100%无共识/100-150%温和/150-200%高/≥200%极端
            # 🔴2026-09-15 修复(Bug4): 边界比较加 1e-6 容差 —— 2.97/1.98=1.5000000000000002 曾使
            # 「skew<150」判假 → 弱共识并列铁律失效(该铁律是保护性的·禁单押)。
            # 容差方向: 边界值(±1e-6 内)一律归【保护侧】—— <150 归弱共识, ≥200 归强共识。
            skew = probs_sorted[0] / probs_sorted[1] * 100
            _weak = skew <= WEAK_SKEW_PCT + 1e-6
            _strong = skew >= STRONG_SKEW_PCT - 1e-6
            sklvl = ('无共识(<100%)' if skew <= 100 + 1e-6 else
                     '温和共识(100-%g%%)' % WEAK_SKEW_PCT if _weak else
                     '高共识(%g-%g%%)' % (WEAK_SKEW_PCT, STRONG_SKEW_PCT) if not _strong
                     else '极端(≥%g%%)' % STRONG_SKEW_PCT)
            # 🔴 2026-10-18 口径澄清：本行 skew 是**未校准的去水比**（反映市场原始共识度）。
            #   铁胆档的 skew 来自 direction_full，那里**已过 prob_calibration**（热门低估修正）。
            #   两者都对，但同名不同口径 → 实测拜仁 775% vs 805%，读者会以为有一个错了。
            #   现同行标注两个口径。
            _cal_skew = None
            try:
                _names = list(_sk_prob.keys())
                _vals = list(_sk_prob.values())
                _ih = _vals.index(max(_vals))
                _adjv = locals().get('adj', 0) or 0
                if _names[_ih] in ('胜', '主', 'H') and _adjv:
                    _pv = list(_vals)
                    _pv[_ih] = _pv[_ih] + _adjv
                    _t2 = sum(_pv)
                    _pv = [x / _t2 for x in _pv]
                    _ps = sorted(_pv, reverse=True)
                    _cal_skew = _ps[0] / _ps[1] * 100
            except Exception:
                _cal_skew = None
            _cal_note = ('  （校准后 %.0f%%·铁胆口径）' % _cal_skew) if _cal_skew else ''
            print(f"  🔴skew精确计算(未校准): {probs_sorted[0]*100:.1f}/{probs_sorted[1]*100:.1f} = {skew:.0f}% → {sklvl} (来源:{_sk_src}·修正32判定依据·禁手算){_cal_note}")
            # 弱共识场平局并列铁律（22.7万场回测: skew<150%→市场首选仅36.4-43.0%≈随机）
            if _weak:
                print(f"  🔴🔴弱共识场(skew={skew:.1f}%<{WEAK_SKEW_PCT:g}%) → 市场首选方向命中率仅 36.4-43.0%(≈随机) → "
                      f"**平局必须与市场首选并列（禁单押市场首选）**·置信度按原档降1档"
                      f"·🔴弱共识(门限 {WEAK_SKEW_PCT:g}%·单一真源 WEAK_SKEW_PCT)须三向覆盖")
            elif _strong:
                print(f"  ✅强共识场(skew={skew:.1f}%≥{STRONG_SKEW_PCT:g}%) → 市场首选命中 64.6% → 可单押")
        # 凯利
        k = kelly(odds, prob)
        print(f"  凯利指数(单源·恒<1·仅相对排序): " + " ".join(f"{kk}={vv:.3f}" for kk, vv in k.items()) + " 🔴单源凯利=1/Σ(1/o) 恒<1 无价值判断·有效凯利需跨市场(竞彩赔率×欧盘概率)")
        # 反抽水（欧盘抽水基准·🔴修复: 原固定3.1%错误→16联赛查表(与SL-jc-reverse基准表一致·Matches.csv 10万+场)·缺省6.9%）
        LEAGUE_VIG = {'epl':0.0561,'championship':0.0652,'league1':0.0685,'league2':0.0667,
                      'bundesliga':0.0689,'bundesliga2':0.0784,'seriea':0.0675,'laliga':0.0684,
                      'ligue1':0.0710,'eredivisie':0.0799,'portugal':0.0814,'finland':0.0703,
                      'norway':0.0645,'japan':0.0704,'china':0.0792,'ec':0.0729}
        league = None
        if len(sys.argv) > 2:
            league = sys.argv[2]
        # 🔴2026-10-17(P0·口径分叉): LEAGUE_VIG 的键是英文 slug（epl/bundesliga/seriea…），
        #   历史调用方一律传中文「英超」→ 查表恒 miss → 26/26 场落「缺省6.9%」而无人察觉。
        #   现做 slug/中文双向归一；仍认不出时**显式标「无数据(该联赛未登记基准)」**，
        #   不再让缺省值冒充查表结果。
        _SLUG_ALIAS = {'英超': 'epl', '英冠': 'championship', '英甲': 'league1', '英乙': 'league2',
                       '德甲': 'bundesliga', '德乙': 'bundesliga2', '意甲': 'seriea',
                       '西甲': 'laliga', '法甲': 'ligue1', '荷甲': 'eredivisie',
                       '葡超': 'portugal', '芬超': 'finland', '芬超冠': 'finland',
                       '挪超': 'norway', '日职联': 'japan', '日职乙': 'japan',
                       '韩K联': 'china', '中超': 'china', '欧冠': 'ec', '欧联': 'ec', '欧协联': 'ec'}
        _lk = (league or '').strip()
        _lk = _SLUG_ALIAS.get(_lk, _lk.lower().replace(' ', '').replace('-', ''))
        if _lk in LEAGUE_VIG:
            eu_vig = LEAGUE_VIG[_lk]
            _basis = f'联赛查表({_lk})'
        else:
            eu_vig = None
            _basis = ('无数据(该联赛未登记基准·原联赛名 %r)' % (league or ''))
        # 🔴抽水标签: 序列若不独立于基线，则 vig 不是竞彩价 → 禁称「竞彩抽水」
        _series_is_base = False
        _baseline_sharp = False
        _fresh_mins = None
        _fresh_band = None
        try:
            _txt_all = open(sys.argv[1], encoding='utf-8').read()
            _series_is_base = '反抽水比(F1) **不适用' in _txt_all
            _baseline_sharp = '🔴基线性质：sharp' in _txt_all
            _fm = re.search(r'距开赛\s*([\d.]+)\s*分钟\s*→\s*\S+?\s*｜\s*盘口联动\(V6\)[：:]\s*(\S+)', _txt_all)
            if _fm:
                _fresh_mins = float(_fm.group(1))
                _fresh_band = ('LIVE' if _fresh_mins <= 90 else
                               'SEMI' if _fresh_mins <= 180 else 'STALE')
        except Exception:
            pass
        # 🔴2026-10-17(P1·V6 硬门): 盘口联动(V6) 的条文前提是「赛前 60-90 分钟临场」。
        #   历史做法：无论数据多旧都照常给出 V6 相关字段/清单项，执行者在报告里
        #   引用「V6 四象限 22.7 万场」时无从判断它到底成立与否。
        #   现在改为硬门——新鲜度不足时**拒绝**产出 V6 结论，只输出三态行。
        if _fresh_band is None:
            print("  🔴盘口联动(V6): ⏭️ 不触发(原因: 输入未声明时点新鲜度·无临场证据)")
        elif _fresh_band == 'STALE':
            print("  🔴盘口联动(V6): 🚫 硬门拒绝 — 末点距开赛 %.0f 分钟(>180) → 非临场·"
                  "V6 判定前提不成立" % _fresh_mins)
            print("     ↳ 结论: V6 四象限/剪刀差/卡位/退盘 **一律不得引用**（不是「算了但不显著」，是「不成立」）")
            print("     ↳ 若确需 V6，须重取赛前 60-90 分钟数据后重跑")
        elif _fresh_band == 'SEMI':
            print("  🔴盘口联动(V6): ⚠️ 弱门 — 末点距开赛 %.0f 分钟(90-180) → 次临场·"
                  "仅可作弱参考·禁当强信号" % _fresh_mins)
        else:
            print("  🔴盘口联动(V6): ✅ 可判定 — 末点距开赛 %.0f 分钟(≤90) → 临场窗口成立"
                  % _fresh_mins)
        _vig_label = '基准价抽水(源:机构基线)' if _series_is_base else '竞彩抽水'
        if eu_vig is None:
            print(f"  {_vig_label} {vig*100:.2f}% · 欧盘基准{_basis} → 反抽水比 不适用(无基准)")
        elif _baseline_sharp:
            # 🔴LEAGUE_VIG 记的是**软盘**（竞彩/亚洲庄）基准抽水；
            #   分子若是 Pinnacle 这类锐盘（实测 2.7-4.4%），两者不同源，
            #   比值会稳定落在 0.4-0.7x 的假区间 —— 与「基线价分母」是同一类错误。
            print(f"  {_vig_label} {vig*100:.2f}% · 欧盘基准联赛查表({_lk}) {eu_vig*100:.2f}% → "
                  f"反抽水比 不适用(原因:分子=锐盘·分母=软盘基准·不同源)")
        else:
            _r = vig / eu_vig
            _f1 = '' if _series_is_base else (" 🔴触发反抽水(>1.30)" if _r > 1.30 else "")
            print(f"  {_vig_label} {vig*100:.2f}% · 欧盘基准{_basis} {eu_vig*100:.2f}% → 反抽水比 {_r:.2f}x{_f1}")
            if _series_is_base:
                print("     ↳ 🔴本文件无独立竞彩采价（序列=机构基线）→ 反抽水比(F1) **不适用**·"
                      "上列比值仅作「基线价 / 联赛基准」参考·禁读作竞彩抽水")
        # 变动序列（逐T）
        if len(secs['spf']) > 1:
            first_ts, first_odds = secs['spf'][0]
            print(f"  变动: 初({first_ts}) {first_odds} → 末 {odds}")
            for k in ('胜','平','负'):
                if k in first_odds and k in odds:
                    chg = (odds[k] - first_odds[k]) / first_odds[k] * 100
                    print(f"    {k}: {first_odds[k]}→{odds[k]} ({chg:+.1f}% {'流入' if chg < 0 else '流出'})")

    # 2. 让球
    if 'rq' in secs and secs['rq']:
        ts, odds = secs['rq'][-1]
        vig, prob = dejuice(odds)
        # 让球盘键映射（胜→让胜 等）
        kmap = {'胜': '让胜', '平': '让平', '负': '让负'}
        disp = {kmap.get(k, k): v for k, v in prob.items()}
        print(f"\n【让球】末盘({ts}): {odds}")
        print(f"  去抽水率: {vig*100:.2f}% → " + " ".join(f"{k}{v*100:.1f}%" for k, v in disp.items()))

    # 3. 总进球
    if 'zjq' in secs and secs['zjq']:
        ts, odds = secs['zjq'][-1]
        vig, prob = dejuice(odds)
        # fix: key with '球' char (0球/7+球) -> normalize
        prob = {k.replace('球', ''): v for k, v in prob.items()}
        keys = sorted([k for k in prob if re.match(r'^\d+(\+?)$', k)], key=lambda x: int(x.rstrip('+')))
        print(f"\n【总进球】末盘({ts}): {odds}")
        print(f"  去抽水率: {vig*100:.2f}%")
        cum = 0
        for k in keys:
            cum += prob.get(k, 0) * 100
            print(f"    {k}球: {prob.get(k,0)*100:.1f}% (≤{k} 累计{cum:.1f}%)")
        p2 = sum(prob.get(k, 0) for k in keys if k in ('0','1','2'))
        p3 = sum(prob.get(k, 0) for k in keys if k in ('0','1','2','3'))
        p4 = sum(prob.get(k, 0) for k in keys if int(k.rstrip('+')) >= 4) if keys else 0
        print(f"  ≤2球 {p2*100:.1f}% · ≤3球 {p3*100:.1f}% · ≥4球 {p4*100:.1f}%")
        o25 = 1 - p2
        print(f"  O2.5 ≈ {1/o25:.2f} (over {o25*100:.0f}%)" if o25 > 0 else "  O2.5 极端")
        o35 = 1 - p3
        print(f"  O3.5 ≈ {1/o35:.2f} (over {o35*100:.0f}%)" if o35 > 0 else "  O3.5 极端")
        # 竞彩总进球赔率反推增强(goal_odds_analyzer·方案阈值优化版)——大小球五级倾向+比分量级
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from goal_odds_analyzer import analyze_goal_odds
            _o8 = []
            for _k in ('0', '1', '2', '3', '4', '5', '6', '7+'):
                _v = odds.get(_k)
                if _v is None: _v = odds.get(_k + '球')   # 🔴兼容'球'后缀表头(0球/7+球)
                _o8.append(float(_v) if _v else 0.0)
            _ga = analyze_goal_odds(_o8)
            if 'error' in _ga:
                print('  ⚠️goal_odds未执行(赔率解析异常):', _ga['error'])
            else:
                print('🔴进球数赔率反推(goal_odds_analyzer): 返奖%.1f%%(倒数和%.4f) | mean=%.2f球 | 量级: %s' % (
                    _ga['返奖率'], _ga['倒数和'], _ga['mean'], _ga['量级']))
                print('    大小球: over1.5=%.1f%% over2.5=%.1f%% over3.5=%.1f%% | %s | 倾向: %s' % (
                    _ga['over1.5'], _ga['over2.5'], _ga['over3.5'], _ga['大小球单调'], _ga['大小球倾向']))
                if _ga.get('信号强度'):
                    print('    🔴信号强度: %s' % _ga['信号强度'])
                if _ga.get('极端档提示'):
                    print('    ⚠️%s' % _ga['极端档提示'])
                if 0.47 <= _ga['over2.5'] / 100 <= 0.53:
                    print('    ⚫中性区(over2.5=%.1f%%·47-53%%): 不判大小方向（V3.5.74 已将原「44-48%%边缘带」并入信号强度分层：42-45%%=中信号/45-47%%=弱信号）' % _ga['over2.5'])
                if _ga['异常'] != '无':
                    print('    校验提示: %s' % ('; '.join(_ga['异常'][:6]) + ('...' if len(_ga['异常']) > 6 else '')))
                if '一致度' in _ga:
                    print('    与泊松: KL=%.3f %s | α=%.2f | 偏差: %s' % (_ga['KL'], _ga['一致度'], _ga['α'],
                          _ga['偏差信号'] if _ga['偏差信号'] != '无' else '无'))
        except Exception as _e:
            print('  ⚠️goal_odds_analyzer未执行:', _e)

    # 4. 半全场 → 半场三元 + 45A推导
    if 'bqc' in secs and secs['bqc']:
        ts, odds = secs['bqc'][-1]
        vig, prob = dejuice(odds)
        ht_home = prob.get('胜胜', 0) + prob.get('胜平', 0) + prob.get('胜负', 0)
        ht_draw = prob.get('平胜', 0) + prob.get('平平', 0) + prob.get('平负', 0)
        ht_away = prob.get('负胜', 0) + prob.get('负平', 0) + prob.get('负负', 0)
        print(f"\n【半全场】末盘({ts}): 半场主{ht_home*100:.1f}%/半场平{ht_draw*100:.1f}%/半场客{ht_away*100:.1f}% (抽水{vig*100:.1f}%)")
        if 'spf' in secs and secs['spf']:
            _, spo = secs['spf'][-1]
            _, sprob = dejuice(spo)
            pm = sprob.get('胜', 0); pd = sprob.get('平', 0); pa = sprob.get('负', 0)
            print(f"  vs 胜平负市场: 主{pm*100:.1f}%/平{pd*100:.1f}%/客{pa*100:.1f}%")
            print(f"  🔴半场-全场对比: 半场平{ht_draw*100:.1f}% vs 全场平{pd*100:.1f}% → 半场平{'高于' if ht_draw > pd else '低于'}市场{' (首回合保守·修正53 S3参考)' if ht_draw >= 0.40 else ''}")
            print(f"  半场主{ht_home*100:.1f}% vs 全场主{pm*100:.1f}% → {'半场落后预期' if ht_home < pm else '半场领先预期'}")

    # 5. 比分 → CS去抽水 P_i 排序 + BTTS估算
    if 'bf' in secs and secs['bf']:
        ts, odds = secs['bf'][-1]
        vig, prob = dejuice(odds)
        print(f"\n【比分】末盘({ts}) CS去抽水(抽水{vig*100:.1f}%) P_i排序:")
        for k, v in sorted(prob.items(), key=lambda x: -x[1]):
            print(f"    {k}: {v*100:.1f}%")
        # BTTS估算
        btts = sum(v for k, v in prob.items() if k.count(':') == 1 and int(k.split(':')[0]) >= 1 and int(k.split(':')[1]) >= 1)
        print(f"  BTTS估算: {btts*100:.1f}%")
        # 主/平/客侧合计
        home = sum(v for k, v in prob.items() if k.count(':') == 1 and int(k.split(':')[0]) > int(k.split(':')[1]))
        draw = sum(v for k, v in prob.items() if k.count(':') == 1 and int(k.split(':')[0]) == int(k.split(':')[1]))
        away = sum(v for k, v in prob.items() if k.count(':') == 1 and int(k.split(':')[0]) < int(k.split(':')[1]))
        print(f"  CS侧: 主{home*100:.1f}%/平{draw*100:.1f}%/客{away*100:.1f}%")
        # 比分变动（初末对比）
        if len(secs['bf']) > 1:
            first_ts, first_odds = secs['bf'][0]
            print(f"  比分变动: 初({first_ts}) → 末")
            for k in odds:
                if k in first_odds and first_odds[k] != odds[k]:
                    chg = (odds[k] - first_odds[k]) / first_odds[k] * 100
                    print(f"    {k}: {first_odds[k]}→{odds[k]} ({chg:+.1f}% {'流入' if chg < 0 else '流出'})")

    # 扩展模块（防手算: D1背离/修正53预计算/V5跨市场·--eu 参数）
    # 🔴2026-09-15: --eu 解析已上移至 main() 开头(胜平负段 skew 来源需先知道 --eu)
    feat = parse_features(text)
    print(run_extensions(secs, feat, eu_odds, handi=asia_handi, water=water_arg))

    print("\n" + "=" * 70)
    print("提示: 模型消费以上结果做【判断】——资金流方向/诱阻识别/信号聚合/主锚次锚·计算不占推理")


# ============ 扩展模块（防手算错误·结构性机制） ============

def parse_features(text):
    """解析【特征分析】段 → {交锋平数, 主队近10平率, 客队客场平率, 主队近10战绩, 客队客场战绩}"""
    feat = {}
    m = re.search('近10场交锋[：:]\\s*([\u4e00-\u9fa5]+)(\\d+)[胜勝](\\d+)[平](\\d+)[负敗]', text)
    if m:
        feat['交锋平数'] = int(m.group(3))
    m = re.search('近10场战况[：:]\\s*([\u4e00-\u9fa5]+)(\\d+)[胜勝](\\d+)[平](\\d+)[负敗]', text)
    if m:
        feat['主队近10平率'] = int(m.group(3)) / 10
    m = re.search('同主客战况[：:]\\s*([\u4e00-\u9fa5]+)(\\d+)[胜勝](\\d+)[平](\\d+)[负敗]', text)
    if m:
        feat['客队客场平率'] = int(m.group(3)) / 10
    return feat


def x53_predict(sections, feat, p_draw=None, oh=None, handi=None):
    """修正53 S1-S12 预计算（防手算·输出信号计数+触发判定）

    🔴 2026-10-18 修复：
      ① S9/S10/S11 原为硬编码 0（未接线）→ 组B(盘口结构)恒为 0，而数据本批全可用
      ② 组合器参数 pd 原写作 pd if 'pd' in dir() else 0 —— dir() 无参返回**当前作用域**,
        pd 是主函数局部变量，在本函数内恒不存在 → 恒传 0
        → sole(平局唯一 ≥4 且 P_平≥25%) 永远不成立。现改为显式参数。
    """
    res = []
    # S1: CS平局比分池内P_i前排 或 资金流入≥3%（需比分盘多时点·单点标观察）
    s1 = '✗'
    if 'bf' in sections and sections['bf']:
        ts, odds = sections['bf'][-1]
        vig, prob = dejuice(odds)
        draw_cs = {k: v for k, v in prob.items() if k in ('0:0', '1:1', '2:2')}
        if draw_cs:
            top = sorted(prob.items(), key=lambda x: -x[1])[:3]
            top_keys = [k for k, _ in top]
            if any(k in top_keys for k in ('0:0', '1:1', '2:2')):
                s1 = '✓(平局比分P_i前排)'
            if len(sections['bf']) >= 2:  # 多时点→看资金流入(或条件·增强标注)
                t0, o0 = sections['bf'][0]
                flows = []
                for k in ('0:0', '1:1', '2:2'):
                    if k in o0 and k in odds:
                        chg = (odds[k] - o0[k]) / o0[k]
                        if chg < -0.03:
                            flows.append(f'{k}流入{-chg*100:.0f}%')
                if flows:
                    s1 = '✓(' + ','.join(flows) + (f'+P_i前排' if '✓' in s1 else '') + ')'
            # 单时点:P_i前排本身即S1充分条件(修正53: P_i前排 或 资金流入)·保留✓·标注单时点
    # S2: 平局降赔≥2%
    s2 = '✗'
    if 'spf' in sections and sections['spf'] and len(sections['spf']) >= 2:
        t0, o0 = sections['spf'][0]
        t1, o1 = sections['spf'][-1]
        if '平' in o0 and '平' in o1:
            chg = (o1['平'] - o0['平']) / o0['平']
            if chg <= -0.02:
                s2 = f'✓(平降{chg*100:.1f}%)'
    # S3: 半场平≥45%（半场平 = 平胜+平平+平负 组合隐含·与主输出一致）
    s3 = '✗'
    if 'bqc' in sections and sections['bqc']:
        ts, odds = sections['bqc'][-1]
        vig, prob = dejuice(odds)
        ht_draw = prob.get('平胜', 0) + prob.get('平平', 0) + prob.get('平负', 0)
        if ht_draw >= 0.45:
            s3 = f'✓(半场平{ht_draw*100:.1f}%)'
        else:
            s3 = f'✗(半场平{ht_draw*100:.1f}%<45%)'
    # S4: 主队近10平率≥30% 或 客队客场平率≥40%
    s4 = '✗'
    if feat.get('主队近10平率') is not None and feat['主队近10平率'] >= 0.30:
        s4 = f"✓(主平率{feat['主队近10平率']*100:.0f}%)"
    elif feat.get('客队客场平率') is not None and feat['客队客场平率'] >= 0.40:
        s4 = f"✓(客客场平率{feat['客队客场平率']*100:.0f}%)"
    # S5: |ELO差|<100 → 不计（无ELO数据源·标无数据）
    s5 = '不计(无ELO数据源)'
    # S6: 交锋近2场平≥1 或 近3场平≥2（txt仅汇总·标观察）
    s6 = '✗'
    if feat.get('交锋平数') is not None and feat['交锋平数'] >= 2:
        s6 = f"⚠️(交锋{feat['交锋平数']}平·位置不确定·观察)"
    # 🔴 2026-10-18 修复：S9/S10/S11 原为**硬编码 0**（未接线）→ 组B(盘口结构)恒为 0，
    #   而组B 所需数据本批全部可用。现按原定义接线（均为 '三态·缺数据不计）。
    #   S9  小球盘        ← 大小球盘隐含小球占优（P_小 > 0.55）
    #   S10 亚盘浅让      ← |handi| <= 0.25（平手盘→平局概率上升）
    #   S11 主胜 2.1-3.0 档  ← 主赔落在中盘模糊区
    s9 = s10 = s11 = '0'
    # S9 数据源：输入无独立【大小球】段→ 用【总进球盘 zjq】反推
    #   P(总进球≤2) = P(0)+P(1)+P(2)；>0.55 则小球盘占优。
    #   与 O2.5 判向同源但取反（小球占优 → 平局概率上升）。
    try:
        _zjq = sections.get('zjq') or []
        if _zjq:
            _ts, _o = _zjq[-1]
            _vig, _p = dejuice(_o)
            _ge3 = 0.0
            for _k, _v in _p.items():
                _kk = str(_k).replace('球', '')
                if _kk == '7+':
                    _ge3 += _v
                else:
                    try:
                        if int(_kk) >= 3:
                            _ge3 += _v
                    except ValueError:
                        pass
            _p_small = 1.0 - _ge3
            if _p_small > 0.55:
                s9 = '✓(小球盘%.1f%%)' % (_p_small * 100)
    except Exception:
        s9 = '⚠️无数据'
    # 🔴 三态纪律：若市场段整体缺失 → 标「无数据」而非 '0'（'0' 会被读成「有信号但未触发」）
    if s9 == '0' and not (sections.get('zjq') or sections.get('ou')):
        s9 = '⚠️无数据(无总进球/大小球盘)'
    try:
        _ou = sections.get('ou') or []
        if not _ou:
            for _k, _v in sections.items():
                if isinstance(_k, str) and ('大小' in _k or _k == 'total'):
                    _ou = _v; break
        if _ou:
            _ts, _o = _ou[-1]
            _vig, _p = dejuice(_o)
            _names = list(_p.keys())
            _small = None
            for _n in _names:
                if _n in ('小', '小球', '下盘'):
                    _small = _p[_n]
            if _small is not None and _small > 0.55:
                s9 = '✓(小球盘%.1f%%)' % (_small * 100)
    except Exception:
        s9 = '0'
    try:
        if handi is not None and abs(handi) <= 0.25:
            s10 = '✓(平手/浅让%+.2f)' % handi
    except Exception:
        s10 = '0'
    try:
        if oh is not None and 2.1 <= oh <= 3.0:
            s11 = '✓(主胜%.2f中盘模糊区)' % oh
    except Exception:
        s11 = '0'

    # S7: 两回合首回合（非欧战=0）
    s7 = '✗(非两回合)'
    # 评审固化·P0-2: 分组去相关（组A资金/S1+S2+S8·组B盘口/S9-S11·组C基本面/S4+S6+S12·组D赛事/S3+S7·组内最多计1/1.5分·禁重复计数）
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from draw_signal_aggregator import draw_signal_aggregator
        signals = {
            'S1': 1 if s1.startswith('✓') else 0, 'S2': 1 if s2.startswith('✓') else 0,
            'S3': 1 if s3.startswith('✓') else 0, 'S4': 1 if s4.startswith('✓') else 0,
            'S6': 1 if s6.startswith('✓') else 0, 'S8': 0,
            'S9': 1 if s9.startswith('✓') else 0,
            'S10': 1 if s10.startswith('✓') else 0,
            'S11': 1 if s11.startswith('✓') else 0, 'S12': 0,
        }
        score, trigger, detail = draw_signal_aggregator(signals, p_draw or 0.0)
        res.append(f"🔴修正53预计算: S1{s1} | S2{s2} | S3{s3} | S4{s4} | S5{s5} | S6{s6} | S7{s7}"
                   f" | S9{s9} | S10{s10} | S11{s11}")
        res.append(f"  🔴分组去相关(P0-2): {detail} → 总分{score} → " + ({'sole': '平局唯一(≥4+P_平≥25%)', 'parallel': '平局并列(≥2.5 或 D1背离+≥1.5)', 'none': '不并列'}[trigger]))
    except Exception:
        cnt = sum(1 for s in (s1, s2, s3, s4, s6) if s.startswith('✓'))
        res.append(f"🔴修正53预计算: S1{s1} | S2{s2} | S3{s3} | S4{s4} | S5{s5} | S6{s6} | S7{s7}"
                   f" | S9{s9} | S10{s10} | S11{s11}")
        res.append(f"  信号计数(不计S5): {cnt} → " + ("≥3触发平局并列" if cnt >= 3 else ("≥5触发平局唯一" if cnt >= 5 else "<3不并列")))
    return '\n'.join(res)





def margin_candidates_pool(sections, asia_handi=None):
    """净胜档多档候选(2026-08-29优化·margin_candidates执行入口): 亚盘盘口->净胜档主+相邻档->各档查表合并候选池
    替代泊松Top1单档(2万场: 21.1% vs 47.4% +26.3pp)

    🔴2026-10-17 修复(P0-3): 亚盘线 / 体彩让球L **双轨分离**
      · 亚盘线(asias_handi·走 --handi) = 净胜档的**唯一依据**（可 平手/受让0.25/让0.75·连续）
      · 体彩L(_rq_handicap·标题让球) = 仅用于让球盘去水·**固定 −1/0/+1 粒度**
      历史缺陷: 原实现拿 _rq_handicap 当唯一依据 → 平手场被硬抬成「主让1球」
                （实测 23/23 场两值不一致·宫崎/埃弗斯堡/布伦特福德均受影响）。
    """
    import sys as _s, os as _o, re as _re
    _s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__)))
    from calc_v3572 import margin_candidates, score_depth_lookup
    out = []
    lottery_h = sections.get('_rq_handicap')
    _lot_str = ('%+g' % lottery_h) if lottery_h is not None else '—'

    # ① 亚盘线优先（唯一依据）
    hs, src = None, None
    if asia_handi is not None:
        try:
            hs, src = float(asia_handi), '亚盘线(--handi)'
        except (TypeError, ValueError):
            hs = None
    # ② 无亚盘线 → 退回体彩L（降级·必须留痕）
    if hs is None and lottery_h is not None:
        hs, src = float(lottery_h), '体彩让球L(降级·非亚盘)'
    # ③ 两者皆无 → 让球盘行弱启发
    if hs is None and 'rq' in sections and sections['rq']:
        seq = sections['rq']
        last = seq[-1][1] if isinstance(seq[-1], tuple) else seq[-1]
        vals = last.values() if isinstance(last, dict) else [str(last)]
        for v in vals:
            m = _re.search(r'[-+]?[0-9]+\.?[0-9]*', str(v))
            if m:
                try:
                    n = float(m.group(0))
                    hs, src = (-n if n >= 1 else n), '让球盘赔率弱启发(方向未知)'
                except Exception:
                    pass
                break
    if hs is None:
        return "  [netmargin] 亚盘盘口未识别->[0]"

    # 🔴双轨对照留痕（不一致必须显式标出·禁静默）
    _consistent = (lottery_h is not None and abs(hs - float(lottery_h)) < 1e-9)
    out.append("  [netmargin-handi] 亚盘线 %+g / 体彩让球L %s / 一致: %s（净胜档依据=%s）" % (
        hs, _lot_str, '是' if _consistent else '否 🔴', src))

    cands = margin_candidates(hs)
    ov = 1.9
    pool = []
    for m in cands:
        lk = score_depth_lookup(m, ov, odd_draw=3.3 if m == 0 else None)
        if lk:
            pool.append(lk['anchor'])
            if lk.get('second'): pool.append(lk['second'])
    uniq = list(dict.fromkeys(pool))
    # 档位列表受亚盘线驱动·保留旧格式（下游 check_luopan/output_checker 依赖）并补来源
    out.append("  [netmargin] 亚盘" + str(hs) + " 档位" + str(cands) + " 候选池 " + '/'.join(uniq)
               + " （依据=" + (src or '?') + "）")
    return chr(10).join(out)



def trap_classify_output(sections, oh=None, od=None, oa=None, handi=None, water=None):
    """盘口诱阻识别预计算(2026-09-02·match_classifier执行入口): 输出比赛分类+异常指标·Step5消费
    需欧盘ML+亚盘盘口+水位·无→降级标注"""
    import sys as _s, os as _o
    _s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__)))
    from calc_v3572 import match_classifier
    if not (oh and od and oa):
        return "  [trap] 无欧盘ML->不触发(需欧盘+亚盘)"
    cf = match_classifier(oh, od, oa, handi=handi, water=water)
    if cf['total_score'] == 0:
        return "  [trap] 正常盘(总分0·70%正常·不硬套)"
    return "  [trap] %s(总分%d·置信%.0f%%): %s" % (cf['match_type'], cf['total_score'], cf['confidence']*100, '; '.join(cf['anomaly_details']) or '无明细')

def goal_bin_output(sections):
    """总进球档查表预计算(2026-09-02·goal_bin_probs执行入口): O2.5→总进球档概率+净3+·Step6/7消费"""
    import sys as _s, os as _o
    _s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__)))
    from calc_v3572 import goal_bin_probs
    ov = None
    for key in ('dq', 'size'):
        if key in sections and sections[key]:
            try:
                for tup in sections[key]:
                    row = tup[1] if isinstance(tup, tuple) else tup
                    for v in (row.values() if isinstance(row, dict) else []):
                        s = str(v)
                        import re
                        # 提取「2.5」后的赔率数字(如 '2.5 1.24' 或 '大于2.5球:1.24' → 1.24)
                        m = re.search(r'2\.5[^0-9]*([0-9]+\.[0-9]+)', s)
                        if m:
                            try: ov = float(m.group(1))
                            except: pass
            except: pass
    if ov is None: return "  [goalbins] O2.5未识别->不触发"
    g = goal_bin_probs(ov)
    if not g: return "  [goalbins] O2.5=" + str(ov) + " 档外->不触发"
    _tp = ''
    if g.get('top'):
        _tp = " | 典型比分:" + " ".join("%s(%.1f%%)" % (s, pc) for s, pc in g['top'])
    return "  [goalbins] O2.5=" + str(ov) + " 总进球档 0-1:" + str(round(g['prob_01']*100)) + "% 2球:" + str(round(g['prob_2']*100)) + "% 3球:" + str(round(g['prob_3']*100)) + "% 4+:" + str(round(g['prob_4']*100)) + "% 净3+:" + str(round(g['net3']*100)) + "%" + _tp + " (Step6/7量级依据)"

def d1_divergence(sections):
    """D1背离检测：主方向升赔≥2T累计>3%（防手算·case42/44教训）"""
    out = []
    if 'spf' in sections and sections['spf'] and len(sections['spf']) >= 2:
        seq = sections['spf']
        t0, o0 = seq[0]
        t1, o1 = seq[-1]
        n_times = len(seq)
        for k in ('胜', '平', '负'):
            if k in o0 and k in o1:
                chg = (o1[k] - o0[k]) / o0[k]
                rising_times = sum(1 for i in range(1, len(seq)) if seq[i][1].get(k, 0) > seq[i-1][1].get(k, 0))
                if chg > 0.03 and rising_times >= 2:
                    out.append(f"  🔴D1背离候选: {k}升赔{chg*100:.1f}%(累计·{rising_times}个时点上升) → 触发硬降级检查")
                else:
                    out.append(f"  D1检测: {k}变动{chg*100:+.1f}%({rising_times}时点上升) → {'不触发' if chg < 0.03 else '上升时点<2·观察'}")
    return '\n'.join(out) if out else '  D1检测: 胜平负数据不足'


def v5_divergence(jc_prob, eu_odds):
    """V5跨市场分歧：竞彩隐含 vs 欧盘隐含（需 --eu 主,平,客 参数）"""
    if not eu_odds:
        return '  V5跨市场: 未提供欧盘(--eu 主,平,客·跳过·模型判断时用Odds-API/api-football实测值)'
    try:
        eo = [float(x) for x in eu_odds.split(',')]
        if len(eo) != 3 or any(x <= 1 for x in eo):
            return '  V5跨市场: --eu 格式错误(需 主,平,客 三个>1的赔率)'
        inv = [1/x for x in eo]
        s = sum(inv)
        eu_p = [x/s for x in inv]
        diff = [(jc_prob.get('胜',0)-eu_p[0])*100, (jc_prob.get('平',0)-eu_p[1])*100, (jc_prob.get('负',0)-eu_p[2])*100]
        names = ['主', '平', '客']
        parts = [f"{names[i]}{diff[i]:+.1f}pp" for i in range(3) if abs(diff[i]) > 1]
        # 有效凯利 = 竞彩赔率×欧盘概率
        ek = []
        jc_odds_est = {k: 1/(p+1e-9) for k, p in jc_prob.items()}
        for i, k in enumerate(['胜', '平', '负']):
            ek.append(f"{k}{1/(jc_prob.get(k,0.01)+1e-9)*eu_p[i]:.2f}")
        return f"  V5跨市场分歧: {'·'.join(parts) if parts else '三向<1pp一致'} | 有效凯利(竞彩赔率×欧盘概率): {' '.join(ek)}"
    except Exception as e:
        return f'  V5跨市场: 解析失败({e})'


def run_extensions(sections, feat, eu_odds=None, handi=None, water=None):
    """运行全部扩展模块（D1背离+修正53+V5+净胜档+进球档+诱阻分类）·防手算

    🔴2026-10-17 修复(P0-2): trap_classify_output 原为**孤儿函数**（只有 def·零调用点）
      → calc_all 打印「诱阻分类预计算」标题后恒为空行 · C16 必核项脚本侧永久失效。
      现接线：欧盘三向齐备时调用（缺则三态标注·禁静默留空）。
    """
    out = []
    out.append('')
    out.append('【扩展·防手算（2026-08-24结构性机制）】')
    out.append('🔴D1背离检测:')
    out.append(d1_divergence(sections))
    if 'spf' in sections and sections['spf']:
        ts, odds = sections['spf'][-1]
        vig, prob = dejuice(odds)
        out.append(x53_predict(sections, feat, p_draw=prob.get('平', 0), oh=odds.get('胜'), handi=handi))
        out.append(v5_divergence(prob, eu_odds))
    # 结构性根除: 接入孤儿函数(防步骤遗失·曾main未调用)
    out.append('')
    out.append('🔴净胜档多档候选(margin_candidates_pool):')
    out.append(margin_candidates_pool(sections, asia_handi=handi))
    out.append('🔴总进球档查表(goal_bin_output):')
    out.append(goal_bin_output(sections))
    out.append('🔴诱阻分类预计算(trap_classify_output):')
    _oh = _od = _oa = None
    if eu_odds:
        try:
            _p = [float(x) for x in str(eu_odds).split(',')]
            if len(_p) == 3 and all(x > 1 for x in _p):
                _oh, _od, _oa = _p
        except Exception:
            _oh = _od = _oa = None
    out.append(trap_classify_output(sections, oh=_oh, od=_od, oa=_oa,
                                    handi=handi, water=water))
    return '\n'.join(out)

if __name__ == '__main__':
    main()