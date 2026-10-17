# -*- coding: utf-8 -*-
"""联网策略回归测试（2026-10-18 第二批）。

用户策略（本文件判据真源）:
  · 分析/预测比赛          → 🔴 **绝对禁止联网**（无开关，不可开启）
  · 复盘                  → 默认**离线**；用户明确要求时才可联网
  · 其他情况              → 允许联网
  · 禁止申请/内置 api key → 代码不得硬编码密钥

原缺陷:
  1) learn.py（复盘入口）L83 `net=not a.no_net` → **默认联网**，与「复盘默认离线」冲突。
  2) calc_all.py（分析入口）虽有 --net 开关 → 但「分析禁止联网」下开关本身就是漏洞。
  3) 三个入口(calc_all / learn / refresh_predlog)各自实现策略，易漂移。

修法: 建立唯一真源 `net_policy.py`，供全部入口调用；分析入口直接走 forced_offline()。
"""
import glob
import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OL = os.path.join(ROOT, 'scripts', 'online_learning')
TMP_SCRIPTS = os.path.join(ROOT, 'scripts', 'tmp')


def run_py(code, timeout=180):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    env.pop("ODDS_API_KEY", None)
    env.pop("API_FOOTBALL_KEY", None)
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", cwd=ROOT, env=env,
                          timeout=timeout)


def src(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


# ========== 策略模块存在且语义正确 ==========
def test_net_policy_module_exists():
    """必须有唯一真源模块，避免三入口各自实现策略而漂移。"""
    p = os.path.join(OL, "net_policy.py")
    assert os.path.exists(p), "缺少 net_policy.py（唯一真源）"


def test_analysis_mode_is_forced_offline():
    """分析模式必须无条件下发「全关」，且不提供开启手段。"""
    code = (
        "import sys\n"
        "sys.path.insert(0, %r)\n"
        "import net_policy as P\n"
        "kw = P.for_analysis()\n"
        "print(sorted(kw.items()))\n"
    ) % OL
    r = run_py(code)
    assert r.returncode == 0, (r.stderr or "")[-500:]
    line = [x for x in r.stdout.strip().splitlines() if x.startswith("[")]
    assert line, "未取得 for_analysis() 返回: " + r.stdout[-300:]
    kw = dict(eval(line[-1]))
    assert kw, "for_analysis() 应返回开关字典"
    assert not any(kw.values()), "分析模式必须全关，实际 %s" % kw


def test_review_mode_defaults_offline():
    """复盘默认离线；只有明确 allow=True 才联网。"""
    code = (
        "import sys\n"
        "sys.path.insert(0, %r)\n"
        "import net_policy as P\n"
        "a = P.for_review()\n"
        "b = P.for_review(allow=True)\n"
        "print(sorted(a.items()))\n"
        "print(sorted(b.items()))\n"
    ) % OL
    r = run_py(code)
    assert r.returncode == 0, (r.stderr or "")[-500:]
    lines = [x for x in r.stdout.strip().splitlines() if x.startswith("[")]
    assert len(lines) >= 2, "输出不足: " + r.stdout[-300:]
    dflt = dict(eval(lines[0]))
    allow = dict(eval(lines[1]))
    assert not any(dflt.values()), "复盘默认必须离线，实际 %s" % dflt
    assert any(allow.values()), "明确允许时复盘应可联网，实际 %s" % allow


def test_analysis_ignores_net_flag():
    """分析入口即使传入 --net，也不得联网（策略不可被命令行绕过）。"""
    code = (
        "import sys\n"
        "sys.path.insert(0, %r)\n"
        "import net_policy as P\n"
        "kw = P.for_analysis(ignore_flags=[\"--net\"])\n"
        "print(sorted(kw.items()))\n"
    ) % OL
    r = run_py(code)
    assert r.returncode == 0, (r.stderr or "")[-500:]
    line = [x for x in r.stdout.strip().splitlines() if x.startswith("[")]
    kw = dict(eval(line[-1]))
    assert not any(kw.values()), "分析模式被 --net 绕过，实际 %s" % kw


# ========== 入口接入真源 ==========
@pytest.mark.parametrize("rel,expect", [
    ("scripts/tmp/calc_all.py", "analysis"),
    ("scripts/online_learning/learn.py", "review"),
    ("scripts/online_learning/refresh_predlog.py", "review"),
])
def test_entrypoint_uses_net_policy(rel, expect):
    """三个入口都必须经 net_policy，禁止各自拼开关。"""
    s = src(rel)
    assert "net_policy" in s, "%s 未接入 net_policy（策略会漂移）" % rel


def test_learn_defaults_offline():
    """learn.py 原 `net=not a.no_net` 使复盘**默认联网** → 必须改为默认离线。"""
    s = src("scripts/online_learning/learn.py")
    # 只检查真实代码行（注释里出现该字符串属正常说明，不应误判）
    code_lines = [l for l in s.splitlines() if not l.strip().startswith("#")]
    code = "\n".join(code_lines)
    assert "not a.no_net" not in code, (
        "learn.py 仍用 no-net 取反 → 复盘默认联网，违反「复盘默认离线」")


def test_calc_all_forces_offline():
    """分析入口不得保留可开启的 --net 联网路径。"""
    s = src("scripts/tmp/calc_all.py")
    assert "for_analysis" in s, (
        "calc_all 未使用 for_analysis() → 分析仍可能联网")


# ========== 禁止内置 key ==========
def test_no_hardcoded_api_key():
    """用户明确禁止申请/内置 api key；代码不得出现 32 位 hex 硬编码密钥。"""
    pat = re.compile(r"[\"\']([0-9a-f]{32})[\"\']")
    offenders = []
    for rel in ("scripts/online_learning/data_bridge.py",
                "scripts/tmp/api_football_mcp.py",
                "scripts/tmp/fetch_books.py"):
        p = os.path.join(ROOT, rel)
        if not os.path.exists(p):
            continue
        try:
            s = open(p, encoding="utf-8").read()
        except Exception:
            continue
        if pat.search(s):
            offenders.append(rel)
    assert not offenders, "存在硬编码密钥: %s" % offenders
