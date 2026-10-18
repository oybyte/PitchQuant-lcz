# -*- coding: utf-8 -*-
"""锚可信度标签语义回归（2026-10-18·439 场实测驱动）

缺陷：原标签只写「锚不可信/锚可信」，读起来像「这场整体别信模型」。
439 场实测发现它**只描述比分锚，不描述方向**：

  🔴不可信  n= 31  方向命中 87.1%  实际场均 4.52 球
  ⚠️弱      n=116  方向命中 64.7%  实际场均 3.38 球
  ✅可信    n=292  方向命中 55.1%  实际场均 3.00 球

→ 标「不可信」的场次方向反而最准（强弱悬殊·进球多·好猜）。

🔴 一律用 subprocess 探测——prestep_dual 导入时会重绑 sys.stdout，
   在测试进程内直接 import 会污染 pytest 捕获流，导致全文件 teardown 失败。
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(ROOT, 'scripts', 'tmp')

_PROBE = """
import json, sys
sys.path.insert(0, %r)
from prestep_dual import anchor_trust
out = []
for o25, handi in [(1.40, None), (1.55, None), (1.80, None), (1.80, -2.5), (None, None)]:
    tag, reason = anchor_trust(o25, handi)
    out.append({'o25': o25, 'handi': handi, 'tag': tag, 'reason': reason})
print(json.dumps(out, ensure_ascii=False))
"""


def _probe():
    code = _PROBE % TMP
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=ROOT, timeout=120)
    assert r.returncode == 0, r.stderr[-500:]
    return json.loads(r.stdout)


def _by(o25, handi):
    for x in _probe():
        if x['o25'] == o25 and x['handi'] == handi:
            return x['tag'], x['reason']
    raise AssertionError('未找到 o25=%r handi=%r' % (o25, handi))


def test_high_goal_match_says_score_unpredictable_direction_usable():
    """大球场（O2.5<1.50）→ 比分不可预测，但必须明说方向仍可用"""
    tag, reason = _by(1.40, None)
    assert '比分' in tag and '方向' in tag and '不可预测' in tag, tag
    assert '方向仍可用' in tag, tag
    assert '87.1%' in reason, reason


def test_mid_goal_match_distinguishes_both_dimensions():
    tag, reason = _by(1.55, None)
    assert '比分' in tag and '方向' in tag, tag
    assert '64.7%' in reason, reason


def test_low_goal_match_says_score_predictable():
    tag, reason = _by(1.80, None)
    assert '比分可预测' in tag, tag
    assert '方向可用' in tag, tag
    assert '55.1%' in reason, reason


def test_deep_handicap_flagged_as_score_only():
    tag, _ = _by(1.80, -2.5)
    assert '比分不可预测' in tag, tag
    assert '方向' in tag, tag


def test_unknown_when_no_o25():
    tag, _ = _by(None, None)
    assert tag == '未知'


def test_old_ambiguous_label_is_gone():
    """旧标签「🔴不可信」「✅可信」不得再出现（防回潮·只查代码行不查注释）"""
    src = open(os.path.join(TMP, 'prestep_dual.py'), encoding='utf-8').read()
    code_lines = [l for l in src.split(chr(10))
                  if l.strip() and not l.strip().startswith('#')]
    code = chr(10).join(code_lines)
    assert "return '🔴不可信'" not in code, '旧标签「🔴不可信」仍在代码中'
    assert "return '✅可信'" not in code, '旧标签「✅可信」仍在代码中'


def test_red_prefix_still_detectable_by_downstream():
    """下游用 startswith(🔴) 判断，新标签必须保留该前缀"""
    tag, _ = _by(1.40, None)
    assert tag.startswith('🔴'), '下游 prestep_dual:173 依赖 🔴 前缀'
    tag2, _ = _by(1.80, -2.5)
    assert tag2.startswith('🔴'), tag2