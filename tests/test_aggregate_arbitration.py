# -*- coding: utf-8 -*-
"""多源聚合【对照】回归（裁决规则已于 2026-10-18 撤销）

历史：2026-10-17 用户指令「冲突时以多源聚合为准」，当时仅 26 场样本（n=2）。
2026-10-18 在 439 场上验证：
  · 裁决生效 34 场 → 改对 11 / 改错 16 / 都错 7 → **净 -5 场**
  · 方向命中 59.0%（裁决后）vs 59.9%（价格引擎）
  · 分 gap 层：3-5pt 聚合 9/价格 12；5-10pt 聚合 2/价格 4
  → 规则撤销，回退至 direction_full。

现锁住：
  ① 方向一律取 direction_full，聚合不覆盖
  ② 两引擎分歧时显式标「仅作参考·不改方向」
  ③ 聚合仍作为对照信号输出（不删除证据）
  ④ 聚合权重表不得含 direction（防循环论证）
"""
import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(ROOT, 'scripts', 'tmp')
BATCH = os.path.join(ROOT, 'data', 'tmp', 'batch_v259V')


def _has_batch():
    return os.path.isdir(BATCH)


def _run(name, eu, handi, o25, u25, water, league):
    p = os.path.join(BATCH, name)
    if not os.path.exists(p):
        pytest.skip('缺样场 %s' % name)
    r = subprocess.run([sys.executable, os.path.join(TMP, 'calc_all.py'), p, league,
                        '--eu', eu, '--handi', handi, '--o25', o25,
                        '--u25', u25, '--water', water],
                       capture_output=True, text=True, encoding='utf-8',
                       errors='replace', cwd=ROOT, timeout=300)
    return r.stdout


def test_arbitration_rule_is_gone_from_code():
    """裁决规则必须已从代码移除（防回潮）

    🔴 只查**代码行**，不查注释——撤销说明本身会提到「裁决生效 34 场」。
    """
    src = open(os.path.join(TMP, 'calc_all.py'), encoding='utf-8').read()
    code_lines = [l for l in src.split(chr(10))
                  if l.strip() and not l.strip().startswith('#')]
    code = chr(10).join(code_lines)
    assert '裁决生效' not in code, '「裁决生效」仍在代码行中'
    assert '无共识·不裁决' not in code, '「无共识·不裁决」仍在代码行中'
    assert '多源聚合对照' in src, '缺少「多源聚合对照」段'


@pytest.mark.skipif(not _has_batch(), reason='需 data/tmp/batch_v259V')
def test_direction_always_from_price_engine():
    """方向必须取 direction_full，聚合不得覆盖"""
    out = _run('10-17_19_30_英超_埃弗顿_vs_切尔西.txt', '2.55,3.73,2.20',
               '0.25', '1.623', '2.606', '1.84', 'epl')
    d = re.search(r'方向\(欧亚综合\): (\S+?)\(', out)
    assert d, '缺方向行'
    assert '聚合对照' in out
    # 不得出现任何「方向 = 聚合向」的措辞
    assert '裁决生效' not in out
    assert '方向 = ' not in out or 'direction_full' in out


@pytest.mark.skipif(not _has_batch(), reason='需 data/tmp/batch_v259V')
def test_divergence_is_labelled_reference_only():
    """两引擎分歧时必须标「仅作参考·不改方向」"""
    import json
    man = json.load(open(os.path.join(BATCH, '_manifest.json'), encoding='utf-8'))
    found = False
    for m in man:
        base = m['name'].replace(' ', '_').replace('(', '').replace(')', '')
        p = os.path.join(BATCH, base + '.txt')
        if not os.path.exists(p) or not m['eu'] or not m.get('o25'):
            continue
        out = _run(base + '.txt', m['eu'], '%g' % m['handi'],
                   '%.3f' % m['o25'], '%.3f' % m['u25'], '%.3f' % m['water'],
                   m.get('lg_slug') or m['lg'])
        if '分歧' in out:
            found = True
            assert '仅供参考' in out or '不改方向' in out, out[-600:]
            break
    if not found:
        pytest.skip('本批无分歧场次')


@pytest.mark.skipif(not _has_batch(), reason='需 data/tmp/batch_v259V')
def test_aggregate_still_visible_as_reference():
    """聚合信号不得因撤销而删除（证据保留）"""
    out = _run('10-17_19_30_英超_埃弗顿_vs_切尔西.txt', '2.55,3.73,2.20',
               '0.25', '1.623', '2.606', '1.84', 'epl')
    assert '聚合分布' in out, '聚合分布被删'
    assert re.search(r'主 [\d.]+% / 平 [\d.]+% / 客 [\d.]+%', out), '聚合三元组缺失'


def test_aggregate_does_not_consume_direction_engine():
    """🔴防循环论证：聚合权重表不得含 direction"""
    src = open(os.path.join(TMP, 'live_score_engine.py'), encoding='utf-8').read()
    assert "matrices['direction']" not in src
    blk = re.search(r'def calculate_dynamic_weights.*?return', src, re.S)
    assert blk, '未找到 calculate_dynamic_weights'
    assert 'direction' not in blk.group(0), '方向引擎被计入聚合权重'
