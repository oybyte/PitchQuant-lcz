# -*- coding: utf-8 -*-
"""防回退（anti-regression）断言 —— 2026-10-17 修复批次的「接线存在性」校验。

check_sync.py 是完整版自检工具（依赖 .reasonix/ 等，公开版跑不了），
故把本轮修复最容易被后续改动**悄悄退回**的接线点，固化成可运行的断言。

每条对应一个曾经的复发点（「存在≠活跃」）。
"""
import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(ROOT, 'scripts', 'tmp')


def src(name):
    return open(os.path.join(TMP, name), encoding='utf-8').read()


def code_only(name):
    """只保留**可执行代码**（剔除注释与文档字符串）——历史说明里提到旧实现是允许的。"""
    import io
    import tokenize
    path = os.path.join(TMP, name)
    parts = []
    with open(path, 'rb') as f:
        for tok in tokenize.tokenize(f.readline):
            if tok.type == tokenize.COMMENT:
                continue
            if tok.type == tokenize.STRING:
                continue          # docstring 与普通字符串里的历史说明都剔除
            if tok.type in (tokenize.NL, tokenize.NEWLINE):
                parts.append(chr(10))
            else:
                parts.append(tok.string)
    return ''.join(parts)


# ══════════ P0-1: 参数透传不得回退 ══════════
def test_calc_all_still_forwards_eu_to_calc_match():
    s = src('calc_all.py')
    assert "'--eu', eu" in s or '("--eu", eu)' in s, (
        "calc_all 不再向 calc_match 透传 --eu（V5 跨市场/V5+ 会再次恒空）")


def test_calc_all_forwards_handi_and_water():
    s = src('calc_all.py')
    assert "'--handi', handi" in s or '("--handi", handi)' in s, "不再透传 --handi"
    assert "'--water', home_water" in s or '("--water", home_water)' in s, "不再透传 --water"


# ══════════ P0-2: 诱阻分类不得变回孤儿函数 ══════════
def test_trap_classify_not_orphan():
    s = src('calc_match.py')
    assert s.count('trap_classify_output(') >= 2, (
        "trap_classify_output 又变回孤儿函数（只有 def·零调用点）")


def test_trap_delegates_to_single_implementation():
    s = src('calc_match.py')
    body = s.split('def trap_classify_output')[1].split('\ndef ')[0]
    assert 'match_classifier' in body, "trap_classify_output 未委托 calc_v3572.match_classifier（双实现风险）"
    for hard in ('water < 1.85', 'water > 2.05'):
        assert hard not in body, "trap_classify_output 内又出现独立打水分支（双实现漂移）: " + hard


# ══════════ P0-3: 亚盘线必须是净胜档唯一依据 ══════════
def test_margin_pool_prefers_asia_handi():
    s = src('calc_match.py')
    body = s.split('def margin_candidates_pool')[1].split('\ndef ')[0]
    assert 'asia_handi' in body, "margin_candidates_pool 又丢了 asia_handi 形参"
    # 亚盘线必须**先于**体彩L被采用
    i_asia = body.find('asia_handi')
    i_lot = body.find('_rq_handicap')
    assert i_asia != -1 and (i_lot == -1 or i_asia < i_lot), (
        "亚盘线未优先于体彩L（净胜档会再次退回 1 球粒度）")


def test_margin_pool_emits_dual_track_line():
    s = src('calc_match.py')
    assert 'netmargin-handi' in s, "缺少亚盘线/体彩L 双轨对照行"


# ══════════ P0-4: O2.5 折算模块必须在位且可导入 ══════════
def test_ou_from_asia_module_exists_and_importable():
    p = os.path.join(TMP, 'ou_from_asia.py')
    assert os.path.exists(p), "ou_from_asia.py 缺失（又将退回手工推导 O2.5）"
    r = subprocess.run([sys.executable, '-c',
                        'import sys; sys.path.insert(0, %r); import ou_from_asia as M; '
                        'print("OK", hasattr(M, "solve_total_lambda"), hasattr(M, "convert"))' % TMP],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    assert 'OK True True' in r.stdout, r.stdout + r.stderr


# ══════════ P1-1: 锚检查必须给约束，不得只给建议锚 ══════════
def test_anchor_check_exposes_constraints():
    s = src('live_score_engine.py')
    assert "'constraints'" in s, "anchor_market_check 不再返回 constraints"
    assert "'violations'" in s, "anchor_market_check 不再返回 violations"
    assert 'MARKET_NET_BAND_UNVALIDATED' in s, "market_net_band 的未回测标注被删除"


def test_anchor_check_no_must_use_wording():
    """「LLM 必须按建议取锚」的措辞不得回归（与 SKILL 禁机械照搬冲突）。

    🔴 查**活代码**（注释/docstring 里复盘历史是允许的）。
    """
    c = code_only('live_score_engine.py')
    assert '必须按建议取锚' not in c, "活代码里又出现「必须按建议取锚」措辞"


# ══════════ P1-2: 伤停留痕不得消失 ══════════
def test_injury_trace_line_present_in_calc_all():
    s = src('calc_all.py')
    assert '伤停影响分(判定铁依据' in s, "calc_all 又丢了伤停三态留痕行"


# ══════════ P1-3: 日志命名不得回退 ══════════
def test_canonical_log_name_in_use():
    s = src('calc_all.py')
    assert '_canonical_log_name' in s, "日志文件名规范化函数被删除"
    assert "os.path.splitext(os.path.basename(txt_path))[0] + '.json'" not in s, (
        "日志命名又退回「直接沿用输入基名」（会产生同场双份）")


# ══════════ P1-4: 跨机构分歧自动解析不得回退 ══════════
def test_cross_book_autoparse_wired():
    s = src('calc_all.py')
    assert 'cross_book_divergence' in s, "跨机构分歧模块被删除"
    assert '_parse_cross_book' in s
    assert "'--max_h'" in s, "--max_h 又变回未知参数"


# ══════════ P2-1: 三层三态统一出口不得回退 ══════════
def test_layer_state_lines_wired():
    s = src('calc_all.py')
    assert '_layer_state_lines' in s, "三层三态统一出口被删除"
    for k in ('HAF(Step4.6)', 'ELO(修正41)', 'xG(SK-xg-depth)'):
        assert k in s, "缺三态行: " + k


# ══════════ P2-2: HAF 乘性耦合不得回退 ══════════
def test_haf_uses_multiplicative_coupling():
    s = src('calc_homeaway.py')
    assert 'def haf_couple(' in s and 'def haf_couple_checked(' in s, "HAF 可导入耦合函数被删除"
    # 🔴 查活代码：旧三项平均的指纹是「三项求和后 /3」（注释里复盘历史允许保留）
    c = code_only('calc_homeaway.py')
    for bad in ('/ 3', '/3'):
        assert bad not in c, (
            "HAF 活代码里又出现「/3」三项平均（对强客队 vs 弱主队系统性低估）")
    assert 'HAF_GUARD_DELTA' in s, "HAF 守卫阈值被删除"


def test_haf_importable_without_matches_csv():
    """公开版无 data/Matches.csv 时，import calc_homeaway 必须成功（否则 HAF 层彻底不可用）。"""
    r = subprocess.run([sys.executable, '-c',
                        'import sys; sys.path.insert(0, %r); import calc_homeaway as H; '
                        'print("IMPORTED", H.haf_couple("Strasbourg","Paris SG","法甲"))' % TMP],
                       capture_output=True, text=True, encoding='utf-8', errors='replace',
                       cwd=ROOT)
    assert 'IMPORTED' in r.stdout, "import calc_homeaway 失败（顶层又读了 Matches.csv）: " + r.stderr[-400:]


# ══════════ P2-3: 弱共识门限单一真源不得回退 ══════════
def test_weak_skew_constant_single_source():
    s = src('calc_match.py')
    assert 'WEAK_SKEW_PCT' in s
    assert re.search(r'WEAK_SKEW_PCT\s*=\s*150', s), "WEAK_SKEW_PCT 值被改动（应保持 150）"
    assert 'STRONG_SKEW_PCT' in s
