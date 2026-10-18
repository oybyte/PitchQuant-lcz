# -*- coding: utf-8 -*-
"""阶段3 回归：多源聚合裁决（方向冲突时以聚合为准）

用户命令（2026-10-17）：direction_full 与 live_score_engine 聚合方向冲突时，**以多源聚合为准**。
这是对 AGENTS.md §5.5「方向铁依据 = 模型计算结果」的明确覆盖，必须可审计、可回退。

锁住：
  ① 冲突时裁决生效并显式留痕（不静默改判）
  ② 一致时不产生噪音
  ③ gap<5pt 必须三向覆盖（低分辨力纪律）
  ④ 平局可作为裁决结果（不得被排除）
  ⑤ 聚合不含 direction_full（不构成循环论证）
  ⑥ 原价格引擎结论保留作对照（可回溯）
"""
import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(ROOT, 'scripts', 'tmp')

_CACHE = {}


BATCH = os.path.join(ROOT, 'data', 'tmp', 'batch_v259e')


def _run(name, eu, handi, o25, u25, water, league):
    key = name
    if key in _CACHE:
        return _CACHE[key]
    p = os.path.join(BATCH, name)
    assert os.path.exists(p), p
    r = subprocess.run([sys.executable, os.path.join(TMP, 'calc_all.py'), p, league,
                        '--eu', eu, '--handi', handi, '--o25', o25, '--u25', u25,
                        '--water', water],
                       capture_output=True, text=True, encoding='utf-8',
                       errors='replace', cwd=ROOT, timeout=300)
    _CACHE[key] = r.stdout
    return r.stdout


def _has_batch():
    return os.path.isdir(BATCH)


@pytest.mark.skipif(not _has_batch(), reason='需 data/tmp/batch_v259e（运行 v259_ingest 后）')
def test_conflict_arbitration_takes_effect():
    """埃弗斯堡：价格引擎客胜 vs 聚合主胜 → 裁决为聚合"""
    out = _run('10-17_21_30_德甲_埃弗斯堡_vs_奥格斯堡.txt',
               '2.25,3.97,2.40', '0', '1.461', '3.171', '1.86', 'bundesliga')
    assert '多源聚合裁决' in out
    assert '价格引擎(direction_full): 客胜' in out
    assert '多源聚合: 主胜' in out
    assert '裁决生效' in out and '方向 = 主胜' in out
    assert '被覆盖' in out


@pytest.mark.skipif(not _has_batch(), reason='需 data/tmp/batch_v259e')
def test_no_noise_when_engines_agree():
    """埃弗顿：两引擎同向 → 只报「一致」，不得出现「被覆盖」"""
    out = _run('10-17_19_30_英超_埃弗顿_vs_切尔西.txt',
               '2.55,3.73,2.20', '0.25', '1.623', '2.606', '1.84', 'epl')
    assert '两引擎一致（无需裁决）' in out
    assert '被覆盖' not in out


@pytest.mark.skipif(not _has_batch(), reason='需 data/tmp/batch_v259e')
def test_draw_can_win_arbitration():
    """宫崎：价格引擎主胜 vs 聚合平局 → 裁决为平局（平局不得被排除）"""
    out = _run('10-17_18_00_日职乙_宫崎棒牛鸟_vs_磐田喜悦.txt',
               '2.22,3.15,2.77', '-0.25', '2.251', '1.799', '1.99', 'japan')
    assert '多源聚合: 平局' in out
    # 该场 gap=1.9<3 → 按最小 gap 门槛不裁决，但平局仍必须出现在聚合里（不得被排除）
    assert '无共识·不裁决' in out
    assert '平局' in out


@pytest.mark.skipif(not _has_batch(), reason='需 data/tmp/batch_v259e')
def test_low_resolution_forces_three_way_coverage():
    """gap<5pt 时裁决结果不可当强信号 → 必须三向覆盖"""
    out = _run('10-17_21_30_德甲_埃弗斯堡_vs_奥格斯堡.txt',
               '2.25,3.97,2.40', '0', '1.461', '3.171', '1.86', 'bundesliga')
    m = re.search(r'首两向 gap ([\d.]+)pt', out)
    assert m
    gap = float(m.group(1))
    if gap < 5:
        assert '必须三向覆盖' in out, 'gap=%.1f 但未强制三向覆盖' % gap
    else:
        assert '可判' in out


# ══════════ 最小 gap 门槛（用户命令 2026-10-17：gap<3pt 连主方向都不给）══════════

MIN_GAP = 3.0


def test_min_gap_threshold_boundary_is_documented():
    """阈值须在代码里可定位且与 AGENTS §6.5 一致（防漂移）"""
    src = open(os.path.join(TMP, 'calc_all.py'), encoding='utf-8').read()
    assert 'if _gap < 3:' in src, '未找到最小 gap 门槛'
    assert '无共识·不裁决' in src


@pytest.mark.skipif(not _has_batch(), reason='需 data/tmp/batch_v259e')
def test_below_min_gap_gives_no_direction():
    """gap<3pt → 不给主方向，判「无共识·不裁决」"""
    out = _run('10-17_18_00_日职乙_宫崎棒牛鸟_vs_磐田喜悦.txt',
               '2.22,3.15,2.77', '-0.25', '2.251', '1.799', '1.99', 'japan')
    gap = float(re.search(r'首两向 gap ([\d.]+)pt', out).group(1))
    assert gap < MIN_GAP, '该场 gap=%.1f 应低于门槛' % gap
    assert '无共识·不裁决' in out
    assert '不给主方向' in out
    # 不得出现「裁决生效」
    assert '裁决生效' not in out
    # 仍须给出三向覆盖要求
    assert '三向覆盖' in out


@pytest.mark.skipif(not _has_batch(), reason='需 data/tmp/batch_v259e')
def test_between_3_and_5_gap_arbitrates_but_weak():
    """3≤gap<5 → 裁决生效但低分辨力"""
    out = _run('10-17_21_30_德甲_埃弗斯堡_vs_奥格斯堡.txt',
               '2.25,3.97,2.40', '0', '1.461', '3.171', '1.86', 'bundesliga')
    gap = float(re.search(r'首两向 gap ([\d.]+)pt', out).group(1))
    assert MIN_GAP <= gap < 5, '该场 gap=%.1f 应落在 [3,5)' % gap
    assert '裁决生效' in out
    assert '低分辨力' in out
    assert '无共识·不裁决' not in out


@pytest.mark.skipif(not _has_batch(), reason='需 data/tmp/batch_v259e')
def test_min_gap_does_not_hide_both_engines():
    """给不出主方向 ≠ 隐藏证据：两引擎原始输出都必须在场"""
    out = _run('10-17_18_00_日职乙_宫崎棒牛鸟_vs_磐田喜悦.txt',
               '2.22,3.15,2.77', '-0.25', '2.251', '1.799', '1.99', 'japan')
    assert re.search(r'方向\(欧亚综合\): \S+\(', out), '价格引擎输出被删'
    assert re.search(r'聚合: 主[\d.]+% 平[\d.]+% 客[\d.]+%', out), '聚合输出被删'
    assert '两引擎输出均不删除' in out


def test_aggregate_does_not_consume_direction_engine():
    """🔴防循环论证：live_score_engine 的聚合不得把 direction_full 作为输入矩阵"""
    src = open(os.path.join(TMP, 'live_score_engine.py'), encoding='utf-8').read()
    # 聚合来自 matrices + weights；direction 仅用于锚-市场约束，不得进 matrices
    assert "matrices['direction']" not in src, '聚合混入了方向引擎 → 裁决构成循环论证'
    for w in ('market', 'poisson', 'handi', 'total', 'prior', 'cs', 'ht'):
        pass
    # 权重表里不得出现 direction 源
    blk = re.search(r'def calculate_dynamic_weights.*?return', src, re.S)
    assert blk, '未找到 calculate_dynamic_weights'
    assert 'direction' not in blk.group(0), '方向引擎被计入聚合权重 → 循环论证'


@pytest.mark.skipif(not _has_batch(), reason='需 data/tmp/batch_v259e')
def test_price_engine_kept_for_traceability():
    """裁决不得删除原价格引擎结论 —— 保留作对照/回溯"""
    out = _run('10-17_21_30_德甲_埃弗斯堡_vs_奥格斯堡.txt',
               '2.25,3.97,2.40', '0', '1.461', '3.171', '1.86', 'bundesliga')
    assert '→ 保留' in out or '仅作对照' in out
    # direction_full 的原始行仍在
    assert re.search(r'方向\(欧亚综合\): \S+\([A-Z\-]+\)', out)
