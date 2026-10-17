# -*- coding: utf-8 -*-
"""留痕 / 锚约束 / 日志命名 回归测试（2026-10-17 修复批次）。

已复现缺陷:
  D4  SKILL 要求伤停缺失时 calc_all 必须输出「🔴伤停影响分(判定铁依据·缺失)」，
      实测 0/23 场有该行 → 脚本层无落点，"没做也不说"。
  D5  anchor_market_check 返回**建议锚**（用一条未回测的经验公式替 LLM 定锚），
      与 SKILL「禁机械照搬」相悖；且 market_net_band 的系数无出处、无限定标注。
      实测 15/22 场出「⚠矛盾→建议锚 X/Y/Z」，但既未说违反哪一条，也无唯一解。
  D6  prediction_log 文件名直接沿用输入 txt 名 → 同场不同分隔符产生重复文件，
      且 calc_all --help 也会落盘（实测 497 文件含 --help.json）。
"""
import json
import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(ROOT, 'scripts', 'tmp')
TXT = os.path.join(ROOT, 'tests', 'fixtures', 'lemans-toulouse-F1.txt')
OUTSIDE = os.path.dirname(ROOT)
EU = '2.97,3.48,1.98'


def run_all(extra, timeout=300):
    return subprocess.run(
        [sys.executable, os.path.join(TMP, 'calc_all.py'), TXT, 'F1'] + extra,
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        cwd=OUTSIDE, timeout=timeout)


# ══════════ D4: 伤停缺失必须显式留痕 ══════════
def test_injury_absence_is_explicitly_logged():
    """未传 --inj_h/--inj_a 时，必须输出伤停缺失留痕行（含原因·非空）。"""
    r = run_all(['--eu', EU, '--o25', '2.05', '--handi', '0.25'])
    hits = [l.strip() for l in r.stdout.splitlines() if '伤停影响分' in l]
    assert hits, "伤停维度缺失但无任何留痕行（SKILL 要求三态标注）:\n" + r.stdout[-800:]
    assert any('缺失' in h for h in hits), "留痕行未标「缺失」: " + str(hits)
    assert any('原因' in h for h in hits), "留痕行未写缺失原因（禁止「伤停：无数据」笼统写法）: " + str(hits)


def test_injury_present_suppresses_absence_line():
    """传了 --inj_h/--inj_a 时：仍须有留痕行，但标「已提供」而不是「缺失」。"""
    r = run_all(['--eu', EU, '--o25', '2.05', '--handi', '0.25',
                 '--inj_h', '1.5', '--inj_a', '0'])
    hits = [l.strip() for l in r.stdout.splitlines() if '伤停影响分' in l]
    assert hits, "提供伤停后反而完全没有伤停行（说明该行是靠缺失分支偶然产生）"
    assert not any('缺失' in h for h in hits), "已提供伤停仍报缺失: " + str(hits)
    assert any('已提供' in h for h in hits), "应标「已提供」: " + str(hits)


# ══════════ D5: 锚检查改「约束」而非「建议锚」 ══════════
def _snippet(code, timeout=180):
    env = dict(os.environ, PYTHONPATH=TMP, PYTHONIOENCODING='utf-8')
    return subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                          encoding='utf-8', errors='replace', cwd=ROOT, env=env,
                          timeout=timeout)


def test_market_net_band_is_labelled_uncalibrated():
    """经验公式必须自标「未回测」，不得冒充 22.7 万场结论。"""
    r = _snippet(
        "import sys; sys.path.insert(0, %r)\n"
        "import live_score_engine as L\n"
        "b, en, rng = L.market_net_band(2.97, 3.48, 1.98)\n"
        "src = open(L.__file__, encoding='utf-8').read()\n"
        "print('UNGA' if '未回测' in src else 'NOFLAG')\n"
        % TMP)
    assert 'UNGA' in r.stdout, (
        "market_net_band 的经验系数(1.35/-1.35/-0.05)与分档边界无出处，"
        "必须显式标注「未回测·经验公式」")
    assert 'NOFLAG' not in r.stdout


def test_anchor_check_returns_constraints_not_suggested_anchor():
    """返回值须含约束三元组（净胜档区间/总进球界/盘口方向），并逐条说明违反项。"""
    r = _snippet(
        "import sys, json; sys.path.insert(0, %r)\n"
        "import live_score_engine as L\n"
        "res = L.anchor_market_check(['1:1','0:1','2:0'], 4.45, 3.98, 1.57, o25=1.78, handi=0.75)\n"
        "print('KEYS', sorted(res.keys()))\n"
        "print('CONSTRAINTS', 'constraints' in res)\n"
        "print('VIOLATIONS', 'violations' in res)\n"
        % TMP)
    assert 'CONSTRAINTS True' in r.stdout, "缺 constraints（约束三元组）: " + r.stdout
    assert 'VIOLATIONS True' in r.stdout, "缺 violations（逐条违反说明）: " + r.stdout


def test_anchor_check_constraints_are_self_consistent():
    """受让场(handi>0) → 盘口方向约束必须禁止主胜锚。"""
    r = _snippet(
        "import sys, json; sys.path.insert(0, %r)\n"
        "import live_score_engine as L\n"
        "res = L.anchor_market_check(['1:0'], 4.45, 3.98, 1.57, o25=1.78, handi=0.75)\n"
        "c = res['constraints']\n"
        "print('FORBID', c.get('forbid_home_anchor'))\n"
        "print('VIO', len(res['violations']))\n"
        % TMP)
    assert 'FORBID True' in r.stdout, "受让场未设「禁主胜锚」约束: " + r.stdout
    assert 'VIO 0' not in r.stdout, "1:0 在受让场应被判违反约束"


# ══════════ D6: prediction_log 命名 & --help 不落盘 ══════════
def test_calc_all_help_does_not_write_prediction_log():
    """--help / 未知参数不得写 prediction_log。"""
    logdir = os.path.join(ROOT, 'scripts', 'online_learning', 'prediction_log')
    before = set(os.listdir(logdir)) if os.path.isdir(logdir) else set()
    subprocess.run([sys.executable, os.path.join(TMP, 'calc_all.py')],
                   capture_output=True, text=True, encoding='utf-8',
                   errors='replace', cwd=OUTSIDE, timeout=120)
    after = set(os.listdir(logdir)) if os.path.isdir(logdir) else set()
    new = after - before
    assert not any('help' in n.lower() or n == '.json' for n in new), (
        "无参数调用仍写日志: %s" % sorted(new))


EPL_TXT = os.path.join(ROOT, 'tests', 'fixtures', 'everton-chelsea-EPL.txt')


def _logged_name(stdout):
    """从 calc_all 的「[预测日志] 特征已存: prediction_log/XXX.json」行取出文件名。"""
    for l in stdout.splitlines():
        if '预测日志' in l and 'prediction_log/' in l:
            return l.split('prediction_log/')[-1].split(' ')[0].strip()
    return None


def test_prediction_log_filename_is_canonical():
    """落盘文件名须为 YYYY-MM-DD_HHMM_联赛_主队_vs_客队.json（同场恒同名）。

    🔴 判据取 stdout 里的实际落盘名，而不是「目录新增文件」——
       规范化后同一场恒同名，第二次运行目录不会新增，用 diff 会假阴性。
    """
    logdir = os.path.join(ROOT, 'scripts', 'online_learning', 'prediction_log')
    r = subprocess.run(
        [sys.executable, os.path.join(TMP, 'calc_all.py'), EPL_TXT, '英超',
         '--eu', '3.17,3.70,2.23', '--o25', '1.67', '--handi', '0.25'],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        cwd=OUTSIDE, timeout=300)
    name = _logged_name(r.stdout)
    try:
        assert name, "未写预测日志:\n" + r.stdout[-800:]
        assert 'everton-chelsea' not in name, (
            "文件名直接沿用输入 txt 名（未规范化）: " + name)
        assert ' ' not in name, "文件名含空格（会与下划线版本产生重复）: " + name
        assert name.startswith('2026-10-17_1930_'), (
            "文件名未取自「比赛时间」字段（应 2026-10-17_1930_…）: " + name)
        assert '埃弗顿' in name and '切尔西' in name, "文件名缺对阵: " + name
        assert name.endswith('.json')
    finally:
        p = os.path.join(logdir, name) if name else None
        if p and os.path.exists(p):
            os.remove(p)


def test_prediction_log_same_match_same_name():
    """同一场跑两次 → 同一个文件名（根治空格/下划线双份）。"""
    outs = []
    for _ in range(2):
        r = subprocess.run(
            [sys.executable, os.path.join(TMP, 'calc_all.py'), EPL_TXT, '英超',
             '--eu', '3.17,3.70,2.23', '--o25', '1.67', '--handi', '0.25'],
            capture_output=True, text=True, encoding='utf-8', errors='replace',
            cwd=OUTSIDE, timeout=300)
        outs.append(_logged_name(r.stdout))
    logdir = os.path.join(ROOT, 'scripts', 'online_learning', 'prediction_log')
    try:
        assert outs[0] and outs[0] == outs[1], "同一场产生不同文件名: %s" % outs
    finally:
        p = os.path.join(logdir, outs[0]) if outs[0] else None
        if p and os.path.exists(p):
            os.remove(p)
