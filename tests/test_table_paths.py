# -*- coding: utf-8 -*-
"""Bug6 回归测试: 数据表路径解析。
根因: 脚本用 os.path.dirname(__file__) 拼表名, 表实际在 data/tmp/,
      加载失败被 return {}/except: pass/os.path.exists 静默吞掉 → 规则引擎空转。
判据: 解析必须是绝对路径且与工作目录无关; 找不到要显式暴露而非静默降级。
"""
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(ROOT, 'scripts', 'tmp')
DATA_TMP = os.path.join(ROOT, 'data', 'tmp')
OUTSIDE = os.path.dirname(ROOT)   # 仓库之外(父目录)仍存在 → 用于验证 CWD 无关性

REQUIRED_TABLES = [
    'league_table.json', 'team_profiles.json', 'water_table.json', 'odds_table.json',
    'score_depth_table.json', 'goal_bins_table.json', 'team_attack_defense.json',
    'ht_ft_cond.json', 'deep_anchor_table.json', 'draw_table.json',
    'handicap_prior_table.json', 'homeaway_table.json', 'odds_score_prior.json',
    'learned_rules.json',
]


def run_snippet(code, cwd=ROOT):
    env = dict(os.environ, PYTHONPATH=TMP, PYTHONIOENCODING='utf-8')
    return subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                          encoding='utf-8', errors='replace', cwd=cwd, env=env, timeout=120)


# ── ① 表本体在位 ────────────────────────────────────────────────
@pytest.mark.parametrize('name', REQUIRED_TABLES)
def test_required_table_exists(name):
    assert os.path.exists(os.path.join(DATA_TMP, name)), name + ' 应存在于 data/tmp/'


# ── ② 解析器能找到全部表, 且返回绝对路径 ────────────────────────
@pytest.mark.parametrize('name', REQUIRED_TABLES)
def test_resolver_finds_table(name):
    code = ('import table_paths, os, sys;'
            'p = table_paths.find_table(' + repr(name) + ');'
            'ok = bool(p) and os.path.isabs(p) and os.path.exists(p);'
            'print(p); sys.exit(0 if ok else 3)')
    r = run_snippet(code)
    assert r.returncode == 0, name + ' 无法解析: ' + (r.stderr or '')[-300:]


# ── ③ 解析结果与工作目录无关 ────────────────────────────────────
@pytest.mark.parametrize('name', ['league_table.json', 'score_depth_table.json', 'ht_ft_cond.json'])
def test_resolver_is_cwd_independent(name):
    code = ('import table_paths; print(table_paths.find_table(' + repr(name) + '))')
    a = run_snippet(code, cwd=ROOT).stdout.strip()
    b = run_snippet(code, cwd=OUTSIDE).stdout.strip()
    assert a and a == b, '不同工作目录解析结果不一致: ' + a + ' vs ' + b


# ── ④ calc_v3572 的四张表必须非空 (当前: 全部空字典) ────────────
def test_calc_v3572_tables_load_nonempty():
    code = ('import calc_v3572 as c;'
            'print(len(c.LEAGUE), len(c.TEAM), len(c.WATER), len(c.ODDS))')
    r = run_snippet(code)
    assert r.returncode == 0, r.stderr[-400:]
    sizes = [int(x) for x in r.stdout.split()]
    assert sizes[0] > 0, 'LEAGUE(league_table) 为空 → R12 档位查表静默失效'
    assert sizes[1] > 0, 'TEAM(team_profiles) 为空 → R13 球队特异性静默失效'
    assert sizes[2] > 0, 'WATER(water_table) 为空 → 水位意图静默失效'
    assert sizes[3] > 0, 'ODDS(odds_table) 为空 → 档位校准静默失效'


# ── ⑤ 比分深度查表 (当前: FileNotFoundError 硬崩) ───────────────
def test_score_depth_lookup_works():
    code = ('from calc_v3572 import score_depth_lookup;'
            'print(score_depth_lookup(1, 2.05) is not None)')
    r = run_snippet(code)
    assert 'FileNotFoundError' not in (r.stderr or ''), 'score_depth_table.json 未解析: ' + r.stderr[-300:]
    assert r.stdout.strip() == 'True', '净胜1+O2.5=2.05 应能查到比分深度数据'


# ── ⑥ goal_bin_probs (当前: except 静默 → None) ─────────────────
def test_goal_bin_probs_returns_data():
    code = ('from calc_v3572 import goal_bin_probs;'
            'g = goal_bin_probs(2.05); print(bool(g and g.get("top")))')
    r = run_snippet(code)
    assert r.stdout.strip() == 'True', 'goal_bins_table.json 未解析 → 总进球档静默 None'


# ── ⑦ 半场条件矩阵 (当前: os.path.exists False → 静默 None) ─────
def test_halftime_inference_cache_loads():
    code = ('import halftime_inference as h;'
            'm = h._load_cache(); print(m is not None and len(m) > 0)')
    r = run_snippet(code)
    assert r.stdout.strip() == 'True', 'ht_ft_cond.json 未解析 → 半场反推静默失效'


# ── ⑧ calc_all 联赛基准 (当前: 降级人工查表) ────────────────────
def test_calc_all_emits_league_baseline():
    txt = os.path.join(ROOT, 'tests', 'fixtures', 'lemans-toulouse-F1.txt')
    r = subprocess.run([sys.executable, os.path.join(TMP, 'calc_all.py'), txt,
                        'F1', '--eu', '2.97,3.48,1.98'],
                       capture_output=True, text=True, encoding='utf-8',
                       errors='replace', cwd=OUTSIDE, timeout=240)
    assert '联赛基准读取失败' not in r.stdout, 'league_table.json 未解析 → 联赛基准降级人工查表'
    assert '联赛基准(法甲' in r.stdout, '应输出 法甲 联赛基准(league_table.json)'
    # 🔴原实现此处必现"(联赛基准读取失败: ...)·降级人工查表"
    assert '降级人工查表' not in r.stdout


# ── ⑨ calc_match 不得硬崩 (当前 rc=1 score_depth_table) ─────────
def test_calc_match_does_not_crash():
    r = subprocess.run([sys.executable, os.path.join(TMP, 'calc_match.py'),
                        os.path.join(ROOT, 'tests', 'fixtures', 'lemans-toulouse-F1.txt')],
                       capture_output=True, text=True, encoding='utf-8',
                       errors='replace', cwd=OUTSIDE, timeout=180)
    assert r.returncode == 0, 'calc_match 崩溃: ' + (r.stderr or '')[-300:]


# ── ⑩ 未知表必须显式 None, 不得抛异常 ───────────────────────────
# ── ⑪ 泊松反推遇 o25=None 必须显式报错, 不得 TypeError 崩栈 ──────
def test_solve_lambda_o25_none_is_explicit():
    """🔴2026-09-15 发现: solve_lambda_live 文档承诺 u25=None 时由 o25 反推,
    但当 o25=None 时裸算 1/o25 → TypeError: unsupported operand int/NoneType,
    从 calc_all 主流程冒泡为"现场引擎未执行(降级泊松+查表)" → 整个现场比分引擎静默失效。
    契约: 无效输入返回 (None, None)(与 L35 min(...)<=1.01 分支一致), 由调用方显式降级。"""
    code = (
        'import sys; sys.path.insert(0, r"%s")\n'
        'from live_score_engine import solve_lambda_live, poisson_matrix\n'
        'r = solve_lambda_live(2.97, 3.48, 1.98, None, None)\n'
        'print("SOLVE", r)\n'
        'print("MATRIX", poisson_matrix(2.97, 3.48, 1.98, None, None))\n'
    ) % TMP
    r = run_snippet(code)
    assert 'TypeError' not in (r.stdout + r.stderr), 'o25=None 不得 TypeError 崩栈: ' + r.stderr[-400:]
    assert r.returncode == 0, r.stderr[-400:]
    assert 'SOLVE (None, None)' in r.stdout, '应显式返回 (None, None): ' + r.stdout


def test_analyze_live_degrades_cleanly_without_o25():
    """o25 缺失时分析入口应返回 status=error + 可读 message(而非异常冒泡)。"""
    code = (
        'import sys; sys.path.insert(0, r"%s")\n'
        'from live_score_engine import analyze_live\n'
        'try:\n'
        '    r = analyze_live(2.97, 3.48, 1.98, None, u25=None, handi=0.25)\n'
        '    print("RESULT", r.get("status"), r.get("message"))\n'
        'except Exception as e:\n'
        '    print("RAISED", type(e).__name__, e)\n'
    ) % TMP
    r = run_snippet(code)
    out = r.stdout + r.stderr
    assert 'RAISED' not in out, '不应异常冒泡: ' + out[-400:]
    assert 'RESULT error' in out, out[-400:]


def test_resolver_returns_none_for_unknown():
    code = 'import table_paths; print(table_paths.find_table("__no_such_table__.json"))'
    r = run_snippet(code)
    assert r.returncode == 0, r.stderr[-300:]
    assert r.stdout.strip() == 'None'
