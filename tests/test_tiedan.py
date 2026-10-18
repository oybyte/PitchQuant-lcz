# -*- coding: utf-8 -*-
"""铁胆档回归（2026-10-18·用户指令）"""
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(ROOT, 'scripts', 'tmp')
sys.path.insert(0, TMP)

BATCH = os.path.join(ROOT, 'data', 'tmp', 'batch_v259V')


def _has_batch():
    return os.path.isdir(BATCH)


def test_threshold_is_single_source():
    import importlib
    M = importlib.import_module('calc_v3572')
    assert M.TIEDAN_SKEW_MIN == 450.0
    assert M.TIEDAN_HIT_RATE == 85.7
    assert M.TIEDAN_N == 49
    assert M.TIEDAN_COVERAGE == 11.2


def test_direction_full_marks_tiedan_by_skew():
    import importlib
    M = importlib.import_module('calc_v3572')
    r1 = M.direction_full(1.11, 8.60, 11.00, None)
    assert r1['铁胆'] is True, r1
    assert r1['skew'] >= 450
    r2 = M.direction_full(2.55, 3.73, 2.20, None)
    assert r2['铁胆'] is False, r2
    assert r2['skew'] < 450


def test_tiedan_label_carries_evidence():
    import importlib
    M = importlib.import_module('calc_v3572')
    r = M.direction_full(1.11, 8.60, 11.00, None)
    assert '85.7%' in r['铁胆标签']
    assert 'n=49' in r['铁胆标签']


def test_tiedan_does_not_change_direction():
    import importlib
    M = importlib.import_module('calc_v3572')
    assert M.direction_full(1.11, 8.60, 11.00, None)['主方向'] == '主胜'
    r2 = M.direction_full(11.00, 8.60, 1.11, None)
    assert r2['主方向'] == '客胜'
    assert r2['铁胆'] is True


def test_draw_risk_hint_always_present_for_tiedan():
    """🔴防死分支回归：平局风险提示必须对**每个**铁胆场触发

    历史 bug（2026-10-18 复跑发现）：该提示原先只在 parallel=='yes' 时追加，
    但铁胆必然是强共识场 → parallel 恒为 'no' → 6/6 场全部不执行（死分支）。
    """
    import importlib
    M = importlib.import_module('calc_v3572')
    r = M.direction_full(1.11, 8.60, 11.00, None)   # 强共识·parallel 必为 no
    assert r['铁胆'] is True
    assert r['并列建议'] == 'no', '前提：铁胆场并列应为 no'
    joined = ' '.join(r['执行提示'])
    assert '平局风险' in joined, '铁胆场缺平局风险提示（死分支回归）'
    assert '模型自估平局' in joined, '提示须带模型自估平局概率，不能只有定性'


def test_draw_risk_hint_absent_for_non_tiedan():
    """非铁胆场不得出现该提示（防噪音）"""
    import importlib
    M = importlib.import_module('calc_v3572')
    r = M.direction_full(2.55, 3.73, 2.20, None)
    assert r['铁胆'] is False
    assert '平局风险' not in ' '.join(r['执行提示'])


def test_tiedan_label_absent_when_below_threshold():
    import importlib
    M = importlib.import_module('calc_v3572')
    r = M.direction_full(2.55, 3.73, 2.20, None)
    assert r['铁胆'] is False
    assert r['铁胆标签'].startswith('—')


@pytest.mark.skipif(not _has_batch(), reason='需 data/tmp/batch_v259V')
def test_calc_all_prints_never_100_notice():
    p = os.path.join(BATCH, '10-18_00_30_德甲_拜仁慕尼黑_vs_RB莱比锡.txt')
    if not os.path.exists(p):
        pytest.skip('缺样场')
    r = subprocess.run([sys.executable, os.path.join(TMP, 'calc_all.py'), p, 'bundesliga',
                        '--eu', '1.11,8.60,11.00', '--handi', '-2.25',
                        '--o25', '1.140', '--u25', '8.127', '--water', '1.82'],
                       capture_output=True, text=True, encoding='utf-8',
                       errors='replace', cwd=ROOT, timeout=300)
    out = r.stdout
    assert '铁胆档' in out
    assert '铁胆 ≠ 100%' in out, '缺「铁胆≠100%」声明'
    assert '85.7%' in out
    assert 'n=49' in out


@pytest.mark.skipif(not _has_batch(), reason='需 data/tmp/batch_v259V')
def test_calc_all_marks_non_tiedan_match():
    p = os.path.join(BATCH, '10-17_19_30_英超_埃弗顿_vs_切尔西.txt')
    if not os.path.exists(p):
        pytest.skip('缺样场')
    r = subprocess.run([sys.executable, os.path.join(TMP, 'calc_all.py'), p, 'epl',
                        '--eu', '2.55,3.73,2.20', '--handi', '0.25',
                        '--o25', '1.623', '--u25', '2.606', '--water', '1.84'],
                       capture_output=True, text=True, encoding='utf-8',
                       errors='replace', cwd=ROOT, timeout=300)
    assert '铁胆档: —' in r.stdout
    assert '铁胆 ≠ 100%' not in r.stdout
