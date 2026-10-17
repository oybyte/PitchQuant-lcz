# -*- coding: utf-8 -*-
"""跨机构分歧 / 弱共识门限 / HAF修正 回归测试（2026-10-17 修复批次）。

已复现缺陷:
  D7  SKILL 宣称 calc_all「必传 --max_h/--max_d/--max_a（跨机构最高价·打通 P0-1 升权）」，
      但 calc_all 回「未知参数(已忽略)」→ 修正35 机构Max分歧**从未被消费**。
      而本次真实输入文件头**已带**「跨机构即盘：N 家 · 最高价 a/b/c · 最低价 …」，
      完全可以自动解析，不需要人工传参。
  D8  弱共识门限两处不一致: calc_match 用 skew<150%，学习成果提示用 skew<130%
      → 130-150% 区间同场可能「须平局并列」却「不必三向覆盖」。
  D9  HAF(calc_homeaway) 对抗耦合公式对「强客队 vs 弱主队」系统性低估客队:
      三项平均里 (基准 - 主队场均失球) 可为负，把 λa 硬拽下来
      （实测 斯特拉斯堡 vs PSG: 市场客胜 68.3% → HAF 39.6%；威尼斯 vs 那不勒斯 56.8% → 33.1%）。
"""
import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(ROOT, 'scripts', 'tmp')
OUTSIDE = os.path.dirname(ROOT)
EPL = os.path.join(ROOT, 'tests', 'fixtures', 'everton-chelsea-EPL.txt')
EU = '3.17,3.70,2.23'


def run_all(extra, txt=None, timeout=300):
    return subprocess.run(
        [sys.executable, os.path.join(TMP, 'calc_all.py'), txt or EPL, '英超'] + extra,
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        cwd=OUTSIDE, timeout=timeout)


def snippet(code, timeout=180):
    env = dict(os.environ, PYTHONPATH=TMP, PYTHONIOENCODING='utf-8')
    return subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                          encoding='utf-8', errors='replace', cwd=ROOT, env=env,
                          timeout=timeout)


# ══════════ D7: 跨机构分歧自动解析输入头 ══════════
def test_cross_book_max_parsed_from_header():
    """输入头含「最高价 a/b/c」时，calc_all 必须自动解析并消费（无需手传 --max_*）。"""
    r = run_all(['--eu', EU, '--o25', '1.67', '--handi', '0.25'])
    hits = [l.strip() for l in r.stdout.splitlines() if '跨机构' in l and ('最高价' in l or 'Max' in l)]
    assert hits, "未输出跨机构最高价/分歧行:\n" + r.stdout[-900:]
    # 必须给出可用的分歧数值，而不是只有原始读数
    assert any(('%' in h) or ('分歧' in h) for h in hits), "未给出分歧百分比: " + str(hits)


def test_cross_book_max_not_required_flag():
    """--max_h 不再出现在「未知参数」告警里（要么被接受，要么根本不需要）。"""
    r = run_all(['--eu', EU, '--o25', '1.67', '--handi', '0.25',
                 '--max_h', '3.30', '--max_d', '4.00', '--max_a', '3.80'])
    unknown = [l for l in r.stdout.splitlines() if '未知参数' in l]
    assert not unknown or '--max_h' not in unknown[0], (
        "SKILL 宣称必传的 --max_h 仍被当成未知参数: " + str(unknown))


def test_missing_header_is_three_state_labelled():
    """输入头无最高价 → 必须三态标注「无数据(原因)」，不得静默留空。"""
    fx = os.path.join(ROOT, 'tests', 'fixtures', '_nohdr.txt')
    src = open(EPL, encoding='utf-8').read()
    src = '\n'.join(l for l in src.splitlines() if '最高价' not in l)
    try:
        with open(fx, 'w', encoding='utf-8') as f:
            f.write(src)
        r = run_all(['--eu', EU, '--o25', '1.67', '--handi', '0.25'], txt=fx)
        hits = [l.strip() for l in r.stdout.splitlines() if '跨机构' in l]
        assert hits, "跨机构分歧模块完全无声（应三态标注）"
        assert any(('无数据' in h) or ('未提供' in h) or ('missing' in h) for h in hits), (
            "缺失时应标「无数据(原因)」: " + str(hits))
    finally:
        if os.path.exists(fx):
            os.remove(fx)


# ══════════ D8: 弱共识门限单一真源 ══════════
def test_weak_skew_threshold_single_source():
    """弱共识门限必须常量单一真源，不得硬编码在**活代码**里。

    🔴 只看代码行（剔除注释/文档串）——历史说明里出现 "skew<130" 是允许的，
       违规的是把它写进可执行分支或打印串。
    """
    import io
    import tokenize
    path = os.path.join(TMP, 'calc_match.py')
    src = open(path, encoding='utf-8').read()
    assert 'WEAK_SKEW_PCT' in src, "缺 WEAK_SKEW_PCT 单一真源常量"

    code_lines = []
    with open(path, 'rb') as f:
        for tok in tokenize.tokenize(f.readline):
            if tok.type == tokenize.COMMENT:
                continue
            if tok.type == tokenize.STRING and tok.line.lstrip().startswith(('"""', "'''")):
                continue
            if tok.type in (tokenize.NL, tokenize.NEWLINE):
                code_lines.append(chr(10))
            else:
                code_lines.append(tok.string)
    code = ''.join(code_lines)

    for bad in ('skew<130', 'skew < 130', 'skew<=130', '"130%"'):
        assert bad not in code, (
            "calc_match 活代码里仍有 130%% 门限（与 %g%% 冲突）: %s" % (150, bad))


def test_weak_skew_threshold_value_is_150():
    r = snippet(
        "import sys; sys.path.insert(0, %r)\n"
        "import calc_match as M\n"
        "print('TH', M.WEAK_SKEW_PCT)\n" % TMP)
    assert 'TH 150' in r.stdout, "弱共识门限应为 150（441 场盲测支撑）: " + r.stdout


def test_learned_rules_hint_uses_same_threshold():
    """学习成果提示若提到弱共识，门限须与常量一致（不得写 130%）。"""
    src = open(os.path.join(TMP, 'calc_all.py'), encoding='utf-8').read()
    bad = re.findall(r'弱共识[^\n]{0,40}?(1[0-9]0)%', src)
    if bad:
        pytest.fail("calc_all 内弱共识门限写法不一致: %s" % bad)


# ══════════ D9: HAF 强客 vs 弱主 ══════════
def test_haf_does_not_crush_strong_away_lambda():
    """PSG 客场 2.35 球/场，HAF 不得把它压到市场隐含以下 0.5 球以上。"""
    r = snippet(
        "import sys; sys.path.insert(0, %r)\n"
        "sys.path.insert(0, %r)\n"
        "import calc_homeaway as H\n"
        "lh, la = H.haf_couple('Strasbourg', 'Paris SG', '法甲')\n"
        "print('LAM', round(lh,3), round(la,3))\n" % (TMP, TMP))
    assert 'LAM' in r.stdout, "未产出 HAF λ: " + (r.stdout + r.stderr)[-500:]
    parts = r.stdout.split('LAM')[-1].split()
    la = float(parts[1])
    assert la >= 1.6, (
        "HAF 把 PSG 客场 λ 压到 %.2f（其客场场均 2.35 球）——"
        "「基准−主队失球」为负时把强客队硬拽下来，属已知公式缺陷" % la)


def test_haf_guard_flags_strong_disagreement():
    """HAF 与市场偏差过大时须返回守卫标记，供上层只标注不喂判定。"""
    r = snippet(
        "import sys; sys.path.insert(0, %r)\n"
        "sys.path.insert(0, %r)\n"
        "import calc_homeaway as H\n"
        "res = H.haf_couple_checked('Strasbourg', 'Paris SG', '法甲', market_lambda_a=2.71)\n"
        "print('GUARD', res.get('guard'))\n" % (TMP, TMP))
    assert 'GUARD' in r.stdout, "未产出守卫字段: " + (r.stdout + r.stderr)[-500:]
    assert 'GUARD None' not in r.stdout, "强分歧未触发守卫: " + r.stdout

# ══════════ P2-3 数据面: learned_rules.json 门限不得与常量分叉 ══════════
def test_learned_rules_threshold_matches_constant():
    """learned_rules.json 是 calc_all「学习成果提示」的数据源。

    历史缺陷: calc_match 用 150%，而这里写 130% → 同一屏出现两个门限。
    """
    import json as _j
    p = os.path.join(ROOT, 'data', 'tmp', 'learned_rules.json')
    if not os.path.exists(p):
        pytest.skip('learned_rules.json 未分发')
    text = open(p, encoding='utf-8').read()
    # 任何形如 skew<NNN% 的门限都必须等于 150
    found = set(re.findall(r'skew\s*<\s*(\d+)\s*%', text))
    assert found <= {'150'}, (
        'learned_rules.json 里弱共识门限与 WEAK_SKEW_PCT=150 分叉: %s' % sorted(found))
