# -*- coding: utf-8 -*-
"""弱共识「必须并列」铁律必须落到判定层（2026-10-19）。

🔴 根因（systematic-debugging Phase 1-3 实测）
  项目规则：skew < WEAK_SKEW_PCT(150) 的弱共识场「平局必须与市场首选并列（禁单押）」，
  依据是 22.7 万场回测——该档市场首选命中率仅 36.4-43.0%（≈随机）。

  但实测 5 个批次、72 场弱共识场，**100% 都是「并列:no」**：
      output 79场 → 33/33 ｜ 竞足 → 5/5 ｜ v259C → 8/8 ｜ v259V → 9/9 ｜ v259W → 17/17

  根因（三层）：
    ① `calc_v3572.direction_full` 形参**没有 skew**，结构上无法感知弱共识；
    ② 并列判定只看 `draw_signal`（修正53分组分≥1.5），与 skew 无关；
    ③ 弱共识规则在 `calc_match` 里**只是 print 一行提示**（L293-296），
       从未写入 `parallel`。`WEAK_SKEW_PCT` 只被显示层消费。

  L261-263 的注释显示曾修过「弱共识并列铁律失效」，但只加了 1e-6 边界容差，
  **没有把 `_weak` 连到 `parallel`** —— 修的是判断，不是执行。

🔴 修复方向的证据（520 场全量验证·2026-10-19）
  | 组 | n | top1(单押) | any(热门+平局) | 提升 |
  |:--|--:|--:|--:|--:|
  | 弱共识 skew<150 | 173 | 44.5% | 72.8% | +28.3pp |
  | 强共识 skew>=150 | 347 | 66.9% | 83.3% | +16.4pp |
  弱共识场真实平局率 28.3%（全样本 20.4%）→ 并列是保护性的，规则方向正确。
"""
import importlib
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(ROOT, 'scripts', 'tmp')
if TMP not in sys.path:
    sys.path.insert(0, TMP)


def _load(name):
    """导入模块，并保护 stdout。

    说明：calc_match 曾在**模块级**无条件替换 sys.stdout，会替换 pytest 的 capture
    对象，使测试以 ERROR（而非 FAIL）收场。该缺陷已于 2026-10-19 修为「仅脚本运行时生效」；
    此处保留还原逻辑作为防御，确保未来再出现同类副作用时断言仍能干净地失败。
    """
    if name in sys.modules:
        return sys.modules[name]
    saved = sys.stdout
    try:
        return importlib.import_module(name)
    finally:
        sys.stdout = saved


def test_weak_consensus_forces_parallel():
    """skew < 门限的弱共识场，并列建议必须被强制为 'yes'（禁单押市场首选）。"""
    import calc_v3572 as V

    assert V.weak_consensus_parallel(121.3, 'no') == 'yes', (
        '弱共识场(skew=121.3%%)仍返回 no —— 禁单押铁律未生效')


def test_strong_consensus_keeps_existing_advice():
    """强共识场（skew >= 门限）必须保持原有并列建议，不被误改。"""
    import calc_v3572 as V

    assert V.weak_consensus_parallel(306.9, 'no') == 'no'
    assert V.weak_consensus_parallel(278.3, 'no') == 'no'


def test_existing_yes_is_preserved_in_weak():
    """弱共识场原本已是 'yes' 时保持 'yes'（不得翻成 no）。"""
    import calc_v3572 as V

    assert V.weak_consensus_parallel(108.4, 'yes') == 'yes'


def test_boundary_belongs_to_protective_side():
    """边界值归保护侧：skew == 门限 视作弱共识（与 calc_match 的 1e-6 容差一致）。"""
    import calc_v3572 as V
    M = _load('calc_match')

    pct = M.WEAK_SKEW_PCT
    assert V.weak_consensus_parallel(pct, 'no') == 'yes', '边界值未归保护侧'
    assert V.weak_consensus_parallel(pct + 1.0, 'no') == 'no', '刚过门限不应判弱共识'


def test_threshold_comes_from_single_source():
    """门限必须是 calc_match.WEAK_SKEW_PCT（AGENTS §5.11 单一真源·禁硬编码）。"""
    import calc_v3572 as V
    M = _load('calc_match')

    assert V.WEAK_CONSENSUS_PCT == M.WEAK_SKEW_PCT, (
        '弱共识门限不是单一真源：%s vs %s' % (V.WEAK_CONSENSUS_PCT, M.WEAK_SKEW_PCT))


def test_none_parallel_is_treated_as_weak_when_skew_low():
    """parallel 为 None/空时，弱共识场也应给出 'yes'（防御性）。"""
    import calc_v3572 as V

    assert V.weak_consensus_parallel(116.4, None) == 'yes'
    assert V.weak_consensus_parallel(116.4, '') == 'yes'


def test_the_72_match_regression_is_closed():
    """回归守线（端到端）：真实跑一场弱共识场，'并列:' 必须是 yes。

    用本次竞足批的「蒙扎 vs 卡利亚里」(skew=121.3% < 150) 做验证。
    🔴 必须**重新执行 calc_all**——读旧输出文件无法证明修复生效。
    """
    import json
    import re
    import subprocess

    dest = os.path.join(ROOT, 'data', 'tmp', 'batch_1020')
    mp = os.path.join(dest, '_manifest.json')
    if not os.path.exists(mp):
        pytest.skip('需 data/tmp/batch_1020（本次竞足批次）')

    man = json.load(open(mp, encoding='utf-8'))
    target = next((m for m in man if '蒙扎' in m['name']), None)
    if not target:
        pytest.skip('批次内无蒙扎场，无法验证弱共识端到端')
    base = target['name'].replace(' ', '_')

    cmd = [sys.executable, os.path.join(ROOT, 'scripts', 'tmp', 'calc_all.py'),
           os.path.join(dest, base + '.txt'), target['lg'],
           '--eu', target['eu'], '--handi', '%.2f' % target['handi'],
           '--o25', '%.3f' % target['o25'], '--u25', '%.3f' % target['u25'],
           '--water', ('%.3f' % target['water']) if target.get('water') else '1.90']
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                       errors='replace', cwd=ROOT, timeout=300)
    out = r.stdout or ''

    assert '🔴🔴弱共识场' in out, '该场不再被判弱共识，测试前提失效'
    m = re.search(r'并列:(\S+?) \|', out)
    assert m, '未找到并列建议行'
    assert m.group(1) == 'yes', (
        '弱共识场仍单押：并列=%s（禁单押铁律未生效）' % m.group(1))
    assert '弱共识强制并列' in out, '并列被改但缺留痕（不可审计）'
