# -*- coding: utf-8 -*-
"""修正53 接线回归（2026-10-18）

修复的两个真实代码缺陷（非数据不足）：
  ① S9/S10/S11 原为**硬编码 0**（未接线）→ 组B「盘口结构」恒为 0，
     而组B 所需数据（亚盘浅让 / 主赔档 / 总进球盘）本数据结构下可用。
  ② 组合器参数 `pd if "pd" in dir() else 0` —— dir() 无参返回**当前作用域**，
     而 pd 是主函数局部变量 → 本函数内恒不存在 → 恒传 0
     → `sole`（平局唯一：总分≥4 且 P_平≥25%）条件**永远不成立**。
"""
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(ROOT, 'scripts', 'tmp')
sys.path.insert(0, TMP)

BATCH = os.path.join(ROOT, 'data', 'tmp', 'batch_v259R')


def test_s9_s10_s11_are_not_hardcoded_zero():
    """防回归：S9/S10/S11 不得再被硬编码为 0"""
    src = open(os.path.join(TMP, 'calc_match.py'), encoding='utf-8').read()
    assert "'S9': 0, 'S10': 0, 'S11': 0" not in src, "S9/S10/S11 又被硬编码回 0"
    assert "s9 = s10 = s11 = '0'" in src, "S9/S10/S11 初始化缺失"


def test_pd_is_passed_explicitly_not_via_dir():
    """防回归：调用点不得再用 "pd" in dir() 这种恒假写法（docstring 里提及不算）"""
    src = open(os.path.join(TMP, 'calc_match.py'), encoding='utf-8').read()
    calls = [l for l in src.split(chr(10))
             if 'draw_signal_aggregator(signals' in l and not l.strip().startswith('#')]
    assert calls, '未找到组合器调用点'
    for l in calls:
        assert "'pd' in dir()" not in l, '调用点仍使用 pd in dir(): %s' % l.strip()
        assert 'p_draw' in l, '调用点未显式传 p_draw: %s' % l.strip()


def test_x53_predict_accepts_explicit_params():
    """x53_predict 必须显式接收 p_draw/oh/handi，而非从环境猜"""
    src = open(os.path.join(TMP, 'calc_match.py'), encoding='utf-8').read()
    m = re.search(r'def x53_predict\(([^)]*)\)', src)
    assert m, '未找到 x53_predict'
    for k in ('p_draw', 'oh', 'handi'):
        assert k in m.group(1), "缺少参数 %s: %s" % (k, m.group(1))


# 🔴 calc_match 导入时会执行 sys.stdout = io.TextIOWrapper(...)，破坏 pytest 捕获流
#   → 一律用 subprocess 调，不在测试进程内直接 import
_PROBE = '''
import sys
sys.path.insert(0, %r)
import calc_match as M
sections = {'spf': [('2026-01-01 12:00:00', {'胜': 2.8, '平': 3.3, '负': 2.2})]}
print(M.x53_predict(sections, {}, p_draw=0.25, oh=2.8, handi=0.25))
'''


def _probe_x53():
    import subprocess
    code = _PROBE % TMP
    r = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                       encoding='utf-8', errors='replace', cwd=ROOT, timeout=120)
    assert r.returncode == 0, r.stderr[-500:]
    return r.stdout


def test_group_b_can_be_nonzero():
    """组B 必须可能 >0（用浅让 + 中盘主赔构造）"""
    out = _probe_x53()
    assert 'S10✓' in out, out
    assert 'S11✓' in out, out


def test_s9_three_state_when_no_goals_market():
    """无总进球/大小球盘时，S9 必须标三态「无数据」，不得静默写 0"""
    out = _probe_x53()
    assert 'S9⚠️无数据' in out, out


def test_sole_trigger_reachable_with_high_p_draw():
    """sole（平局唯一）必须可达：总分≥4 且 P_平≥25%"""
    from draw_signal_aggregator import draw_signal_aggregator as D_fn
    sig = {'S1': 1, 'S2': 1, 'S9': 1, 'S10': 1, 'S11': 1,
           'S4': 1, 'S6': 1, 'S12': 1, 'S3': 1}
    score, trig, _ = D_fn(sig, 0.30)
    assert score >= 4, score
    assert trig == 'sole', (score, trig)
    _, trig2, _ = D_fn(sig, 0.10)
    assert trig2 != 'sole', trig2


@pytest.mark.skipif(not os.path.isdir(BATCH), reason="需 data/tmp/batch_v259R")
def test_batch_group_b_actually_fires():
    """真实批次上组B 必须至少在一部分场次 >0（证明接线生效）"""
    out_dir = os.path.join(BATCH, 'out')
    if not os.path.isdir(out_dir):
        pytest.skip('缺 out 目录')
    n = 0
    tot = 0
    for fn in os.listdir(out_dir):
        if not fn.endswith('.txt'):
            continue
        t = open(os.path.join(out_dir, fn), encoding='utf-8').read()
        if '组B盘口' not in t:
            continue
        tot += 1
        if "'组B盘口': 0" not in t:
            n += 1
    assert tot > 0
    assert n > 0, '组B 在 %d 份输出里全为 0 —— 接线未生效' % tot