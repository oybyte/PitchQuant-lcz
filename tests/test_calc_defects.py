# -*- coding: utf-8 -*-
"""Bug1-Bug5 回归测试 (2026-09-15 修复批次)。

每个测试对应一个已复现缺陷, 修复前必须 RED:
  Bug1 calc_all.py 不识别 --water(静默丢弃) 且未知参数无告警
  Bug2 match_classifier 水位标度用 0.7-1.1(澳门体系), 与全仓 1.8-2.1 冲突
  Bug3 match_classifier handi 符号 与 calc_v3572 --handi(负=主让) 相反
  Bug4 skew<150 铁律在 150.0000000000002 浮点噪声下不触发
  Bug5 calc_match skew 只吃竞彩 txt, 忽略 --eu 欧盘来源
"""
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(ROOT, 'scripts', 'tmp')
TXT = os.path.join(ROOT, 'tests', 'fixtures', 'lemans-toulouse-F1.txt')   # 法甲 勒芒 vs 图卢兹 竞彩末盘 2.97/3.48/1.98
OUTSIDE = os.path.dirname(ROOT)
BASE = ['--eu', '2.97,3.48,1.98', '--o25', '2.05', '--handi', '0.25']


def run_ca(extra, timeout=300):
    return subprocess.run([sys.executable, os.path.join(TMP, 'calc_all.py'), TXT, 'F1'] + extra,
                          capture_output=True, text=True, encoding='utf-8',
                          errors='replace', cwd=OUTSIDE, timeout=timeout)


def run_cm(args, timeout=180):
    return subprocess.run([sys.executable, os.path.join(TMP, 'calc_match.py'), TXT] + args,
                          capture_output=True, text=True, encoding='utf-8',
                          errors='replace', cwd=OUTSIDE, timeout=timeout)


def snippet(code, timeout=120):
    env = dict(os.environ, PYTHONPATH=TMP, PYTHONIOENCODING='utf-8')
    return subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                          encoding='utf-8', errors='replace', cwd=ROOT, env=env, timeout=timeout)


def lines_with(out, key):
    return [l.strip() for l in out.splitlines() if key in l]


# ── Bug1: --water 别名 + 未知参数告警 ────────────────────────────
def test_calc_all_water_alias_equivalent_to_home_water():
    """--water 必须等价 --home_water(calc_v3572/README 全仓只用 --water)。"""
    a = run_ca(BASE + ['--water', '1.84'])
    b = run_ca(BASE + ['--home_water', '1.84'])
    la, lb = lines_with(a.stdout, '诱阻分类:'), lines_with(b.stdout, '诱阻分类:')
    assert la and lb, 'calc_all 未输出诱阻分类行'
    assert la == lb, '--water 未生效(静默丢弃): --water=%s vs --home_water=%s' % (la, lb)
    assert '低水1.84' in a.stdout, '--water 水位信号未到达 match_classifier'


def test_calc_all_warns_unknown_flag():
    """未知参数必须显式告警, 不得静默丢弃(误用 --water 时曾零提示)。"""
    r = run_ca(BASE + ['--bogus', '9.9'])
    assert '--bogus' in r.stdout, '未知参数 --bogus 未告警: ' + r.stdout[-400:]


# ── Bug2: 水位标度统一为欧式 1.8-2.1 ────────────────────────────
@pytest.mark.parametrize('water,expect_score,expect_word', [
    (0.80, 0, '标度'),    # 澳门标度值 → 不参与, 且显式标注 (原: 静默算中性)
    (0.90, 0, '标度'),
    (1.84, 1, '低水'),    # 欧式低水 (原: 误判高水·诱盘)
    (1.86, 0, ''),        # 中性区 (原: 误判高水·诱盘)
    (2.05, 0, ''),        # 中性区边界 (原: 误判高水·诱盘)
    (2.10, 1, '高水'),    # 欧式高水 (两版一致·保护回归)
])
def test_match_classifier_water_scale_is_european(water, expect_score, expect_word):
    """单一标度(与 direction_full/calc_v3572 --water 一致): 低水<1.85, 高水>2.05。
    原实现用澳门标度(>0.95高水/<0.75低水) → 1.00~2.05 全判高水 → 每场白送1分。"""
    code = ('from calc_v3572 import match_classifier as m;'
            'cf=m(2.97,3.48,1.98,handi=0.25,water=%r);'
            'print(cf["anomaly_scores"].get("water"));'
            'print([d for d in cf["anomaly_details"] if "水" in d and "背离" not in d])' % water)
    r = snippet(code)
    out = r.stdout.splitlines()
    assert out and out[0].strip() == str(expect_score), (
        'water=%s 期望水位分%s 实得%s | %s' % (water, expect_score, (out or [''])[0].strip(), r.stderr[-200:]))
    if expect_word:
        assert expect_word in r.stdout, 'water=%s 期望标注「%s」实得 %s' % (water, expect_word, r.stdout.strip())


# ── Bug3: handi 符号(负=主让)与 CLI 一致 ───────────────────────
@pytest.mark.parametrize('handi,expect_home', [
    (-1.0, 0.66), (-0.75, 0.61), (-0.5, 0.56), (-0.25, 0.48),
    (0.0, 0.55),                       # 平手盘·不分主客让
    (0.25, 0.52), (0.5, 0.44), (1.0, 0.34),   # 正=主受让 → 主胜概率取补
])
def test_match_classifier_handi_sign_matches_cli(handi, expect_home):
    """文档口径 --handi 负=主让(calc_v3572 L70)。主让越深 → 亚盘主胜隐含越高。
    原实现把主让当主受让(取反) → 深浅方向完全反向。"""
    code = ('from calc_v3572 import match_classifier as m;'
            'cf=m(2.97,3.48,1.98,handi=%r);'
            'print(cf.get("handi_implied_home"))' % handi)
    r = snippet(code)
    got = r.stdout.strip()
    assert got == str(expect_home), (
        'handi=%+.2f 亚盘主胜隐含应%.2f(负=主让) 实得%s | %s' % (handi, expect_home, got, r.stderr[-200:]))


# ── Bug4: skew 150% 边界归保护侧(弱共识) ───────────────────────
def test_calc_match_skew_boundary_150_is_weak_consensus():
    """2.97/1.98 精确=1.5000000000000002 → 显示 150%; 浮点噪声不得翻转保护性铁律。"""
    r = run_cm(['F1'])
    line = lines_with(r.stdout, 'skew精确计算')
    assert line, 'calc_match 未输出 skew 精确计算行'
    assert not any('高共识' in l for l in line), '150% 被判为高共识(可单押): ' + line[0]
    assert '弱共识场' in r.stdout, '150% 未触发弱共识并列铁律: ' + line[0]


# ── Bug5: skew 取 --eu 欧盘来源 ────────────────────────────────
def test_calc_match_skew_uses_eu_odds_source():
    """传 --eu 时 skew 必须取欧盘 3.08/3.69/2.31(去水后 42.1/31.6=133%)。"""
    r = run_cm(['F1', '--eu', '3.08,3.69,2.31'])
    line = lines_with(r.stdout, 'skew精确计算')
    assert line, 'calc_match 未输出 skew 精确计算行'
    assert '133' in line[0], '未按欧盘 3.08/2.31=133.3% 计算(仍用竞彩 txt): ' + line[0]
    assert '弱共识场' in r.stdout, '133% 应触发弱共识并列铁律'
