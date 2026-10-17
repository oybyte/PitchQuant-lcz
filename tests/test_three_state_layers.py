# -*- coding: utf-8 -*-
"""非五大联赛「先行层」三态统一声明 回归测试（2026-10-17 修复批次）。

已复现缺陷:
  D10  HAF / ELO / xG 三者都有「数据域覆盖」限制（仅五大联赛），但三态写法不统一：
       · ELO 有「无数据(原因)」规定
       · HAF 缺失时只 echo 一句 why，calc_all 侧**完全无声**
       · xG 缺失时同样无声
       实测本批 14/22 场 HAF 缺、10/22 ELO 缺、20/22 xG 缺，报告里只能手写声明。
  → 统一为 C13/C26/C27 三行三态，且在 calc_all 输出中**恒出现**（缺失也要出现）。
"""
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(ROOT, 'scripts', 'tmp')
OUTSIDE = os.path.dirname(ROOT)
EPL = os.path.join(ROOT, 'tests', 'fixtures', 'everton-chelsea-EPL.txt')
# 日职联 fixture（非五大·三者全缺的典型场次）
JLEAGUE = os.path.join(ROOT, 'tests', 'fixtures', 'kashima-vs-nagasaki-J1.txt')


def run_all(txt, league, extra, timeout=300):
    return subprocess.run(
        [sys.executable, os.path.join(TMP, 'calc_all.py'), txt, league] + extra,
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        cwd=OUTSIDE, timeout=timeout)


def layer_lines(out, key):
    return [l.strip() for l in out.splitlines() if key in l]


# ══════════ 三态行必须恒出现（有数据 / 无数据都出现）══════════
@pytest.mark.parametrize('key', ['HAF', 'ELO', 'xG'])
def test_three_state_lines_always_present_for_top5(key):
    """五大联赛：三行也必须出现（有/无数据都要有明确状态）。"""
    r = run_all(EPL, '英超', ['--eu', '3.17,3.70,2.23', '--o25', '1.67', '--handi', '0.25'])
    hits = layer_lines(r.stdout, key)
    assert hits, "缺先行层三态行: %s\n%s" % (key, r.stdout[-900:])


@pytest.mark.parametrize('key', ['HAF', 'ELO', 'xG'])
def test_three_state_lines_always_present_for_non_top5(key):
    """非五大联赛：同样必须出现，且标「不在覆盖域」+ 原因。"""
    assert os.path.exists(JLEAGUE), '缺日职联 fixture'
    r = run_all(JLEAGUE, '日职联', ['--eu', '1.42,4.35,5.60', '--o25', '1.73', '--handi', '-1'])
    hits = layer_lines(r.stdout, key)
    assert hits, "非五大场次缺先行层三态行: %s\n%s" % (key, r.stdout[-900:])
    assert any(('不在覆盖域' in h) or ('无数据' in h) or ('⏭️' in h) or ('不触发' in h)
               for h in hits), "%s 行未标三态: %s" % (key, hits)


def test_three_state_uses_unified_marker():
    """三态必须用统一标记（缺失=⏭️/⚠️·禁用笼统「无数据」而不写原因）。"""
    r = run_all(JLEAGUE, '日职联', ['--eu', '1.42,4.35,5.60', '--o25', '1.73', '--handi', '-1'])
    for key in ('HAF', 'ELO', 'xG'):
        hits = layer_lines(r.stdout, key)
        assert hits
        assert any('原因' in h or '覆盖' in h or '缺失' in h for h in hits), (
            "%s 缺失未写原因（禁止「无数据」笼统写法）: %s" % (key, hits))
