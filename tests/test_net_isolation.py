# -*- coding: utf-8 -*-
"""网络通道隔离 + data_bridge 路径落入点 回归测试（2026-10-18 修复批次）。

根因（两条独立缺陷·同一文件）:

  D1 路径错层 —— data_bridge.py L22-24
      DATA = os.path.dirname(HERE)   # HERE=scripts/online_learning -> DATA=scripts (错)
      TMP  = os.path.join(DATA, "tmp")                -> scripts/tmp (错)
      ROOT = os.path.dirname(DATA)                    -> 仓库根 (对·巧合)
      后果: homeaway_table.json 去 scripts/tmp 找 -> 恒 missing
            -> HAF 139 队主客场档案整批丢失（实测本批 24/24 场 HAF=missing）
            而该表真身在 data/tmp/（111 KB）。

  D2 网络开关粒度 —— collect()
      add("news",...) / add("euro_odds",...) 写在 if net: 分支之外 -> 无条件下发
      后果: 即使不传 --net（默认 False）仍会联网打 Bing / Odds-API。
            实测预测日志 news=missing "Bing News 无结果" = 已发请求后失败，
            与「服务端未提供」性质完全不同（正是项目条款①要防的静默跳过混淆）。
      修法: 拆为 --net-injury / --net-odds / --net-form 三独立通道，默认全关。

判据真源:
  · scripts/tmp/table_paths.py _SEARCH_DIRS 首位 = data/tmp（唯一规范位置）
  · 本仓库 data/tmp/homeaway_table.json 真实存在
"""
import glob
import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OL = os.path.join(ROOT, 'scripts', 'online_learning')
DATA_TMP = os.path.join(ROOT, 'data', 'tmp')
BRIDGE = os.path.join(OL, 'data_bridge.py')

SNIPPETS = os.path.join(DATA_TMP, "batch_v259")


def src():
    with open(BRIDGE, encoding="utf-8") as f:
        return f.read()


def run_snippet(code, timeout=180):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    env.pop("ODDS_API_KEY", None)
    env.pop("API_FOOTBALL_KEY", None)
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", cwd=ROOT, env=env,
                          timeout=timeout)


def _sample_txt():
    cands = [t for t in sorted(glob.glob(os.path.join(SNIPPETS, "*.txt")))
             if not t.endswith("_jc.txt")]
    assert cands, "缺少样本 txt（data/tmp/batch_v259/*.txt）"
    return cands[0]


# ========== D1: 路径落入点 ==========
def test_data_and_tmp_point_to_repo_data_dir():
    """DATA 必须指向 <repo>/data，TMP 必须指向 <repo>/data/tmp。

    旧实现 DATA=scripts（错一层）-> 所有 data 资产恒缺失。
    """
    code = (
        "import sys\n"
        "sys.path.insert(0, %r)\n"
        "import data_bridge as d\n"
        "print(d.DATA)\nprint(d.TMP)\nprint(d.ROOT)\n"
    ) % OL
    r = run_snippet(code)
    assert r.returncode == 0, "导入 data_bridge 失败: " + (r.stderr or "")[-400:]
    got = r.stdout.strip().splitlines()
    assert len(got) >= 3, "输出不足: " + repr(r.stdout)
    data_dir, tmp_dir, root_dir = got[0], got[1], got[2]
    assert os.path.normcase(data_dir) == os.path.normcase(os.path.join(ROOT, "data")), (
        "DATA 应指向 repo/data，实际 %s" % data_dir)
    assert os.path.normcase(tmp_dir) == os.path.normcase(DATA_TMP), (
        "TMP 应指向 repo/data/tmp，实际 %s" % tmp_dir)
    assert os.path.normcase(root_dir) == os.path.normcase(ROOT), (
        "ROOT 应指向仓库根，实际 %s" % root_dir)


def test_haf_source_actually_loads_homeaway_table():
    """行为判据（防「存在不等于活跃」）: 表真实存在于 data/tmp/ 时，
    src_haf 不得返回 missing（表不存在）。

    旧实现报 homeaway_table.json 不存在（因去 scripts/tmp 找），
    与磁盘事实矛盾 —— 这是本批 HAF 全灭的直接原因。
    """
    assert os.path.exists(os.path.join(DATA_TMP, "homeaway_table.json")), \
        "测试前提: data/tmp/homeaway_table.json 应存在"
    code = (
        "import sys\n"
        "sys.path.insert(0, %r)\n"
        "import data_bridge as d\n"
        "st, data, note = d.src_haf(chr(27861)+chr(20848)+chr(20811)+chr(31119), chr(31185)+chr(38534))\n"
        "print(st)\nprint(str(note)[:120])\n"
    ) % OL
    r = run_snippet(code)
    assert r.returncode == 0, (r.stderr or "")[-400:]
    lines = r.stdout.strip().splitlines()
    st = lines[0] if lines else ""
    note = lines[1] if len(lines) > 1 else ""
    assert st != "missing", (
        "src_haf 返回 missing 而 data/tmp/homeaway_table.json 存在 -> 路径错层未修: " + note)
    assert st == "ok", "src_haf 未取得两队档案(missing/partial): %s | %s" % (st, note)


def test_fetch_scripts_resolved_from_scripts_tmp():
    """抓取器(fetch_clubelo.py / understat_xg.py)确实在 scripts/tmp/，
    修 DATA 后不得把它们也指到 data/tmp/ —— 两类资产目录不同，须分别解析。"""
    s = src()
    for sc in ("fetch_clubelo.py", "understat_xg.py"):
        assert sc in s, sc + " 引用缺失(测试前提失效)"
    assert re.search(r"PYDIR|SCRIPT_DIR|SCRIPTS", s), (
        "未见 scripts 目录常量（PYDIR/SCRIPT_DIR/SCRIPTS）-> 抓取脚本目录未与 data 目录分离")


# ========== D2: 网络通道隔离 ==========
def test_collect_signature_has_granular_switches():
    s = src()
    m = re.search(r"def collect\((.*?)\):", s, re.S)
    assert m, "collect 定义缺失"
    sig = m.group(1)
    for kw in ("net_injury", "net_odds", "net_form"):
        assert kw in sig, (
            "collect() 缺细粒度开关 %s -> 无法做到「仅伤停联网」" % kw)


def test_news_and_euro_odds_are_gated():
    """news / euro_odds 的调度必须出现在某个 net_* 分支内，不得无条件调用。

    旧实现二者写在 if net: 之外 -> 默认离线仍联网。
    """
    s = src()
    i = s.find("def collect(")
    j = s.find("\ndef ", i + 10)
    body = s[i:j if j > i else i + 6000]
    for name, flag in (("news", "net_injury"), ("euro_odds", "net_odds")):
        call = re.search(r"add\('" + name + r"'", body)
        assert call, "%s 调度缺失" % name
        win = body[max(0, call.start() - 400):call.start()]
        assert flag in win, (
            "%s 的调度未受 %s 约束（前文无该开关判断）-> 默认离线仍会联网" % (name, flag))


def test_default_collect_issues_no_network():
    """行为判据: 默认调用（不传任何 net 开关）时，不得发出任何网络请求。"""
    code = (
        "import sys, json\n"
        "sys.path.insert(0, %r)\n"
        "import data_bridge as d\n"
        "def boom(name):\n"
        "    def _f(*a, **k):\n"
        "        raise AssertionError(chr(78)+chr(69)+chr(84)+name)\n"
        "    return _f\n"
        "d.src_news = boom(chr(87)+chr(79)+chr(82)+chr(75))\n"
        "d.src_euro_odds = boom(chr(87)+chr(79)+chr(82)+chr(75))\n"
        "d.src_clubelo = boom(chr(87)+chr(79)+chr(82)+chr(75))\n"
        "d.src_xg = boom(chr(87)+chr(79)+chr(82)+chr(75))\n"
        "d.src_api_fb = boom(chr(87)+chr(79)+chr(82)+chr(75))\n"
        "txt = [t for t in sorted(__import__(chr(103)+chr(108)+chr(111)+chr(98)).glob(%r)) if not t.endswith(%r)]\n"
        "r = d.collect(txt[0], chr(24503)+chr(30002))\n"
        "print(json.dumps(r.get(chr(115)+chr(116)+chr(97)+chr(116)+chr(117)+chr(115)), ensure_ascii=False))\n"
    ) % (OL, os.path.join(SNIPPETS, "*.txt"), "_jc.txt")
    r = run_snippet(code)
    out = (r.stdout or "") + (r.stderr or "")
    assert "NETWORK" not in out, (
        "默认(离线)调用仍触发了网络源 -> 开关隔离失效: " + out[-400:])
    assert r.returncode == 0, "collect 执行失败: " + out[-600:]


def test_injury_channel_can_be_enabled_alone():
    """行为判据: 仅开 net_injury 时，只有 news 被调度；odds/form 仍保持离线。"""
    code = (
        "import sys, json\n"
        "sys.path.insert(0, %r)\n"
        "import data_bridge as d\n"
        "called = []\n"
        "def mk(name):\n"
        "    def _f(*a, **k):\n"
        "        called.append(name)\n"
        "        return (chr(111)+chr(107), {}, chr(120))\n"
        "    return _f\n"
        "d.src_news = mk(chr(110)+chr(101)+chr(119)+chr(115))\n"
        "d.src_euro_odds = mk(chr(101)+chr(117)+chr(114)+chr(111))\n"
        "d.src_clubelo = mk(chr(99)+chr(108)+chr(117)+chr(98))\n"
        "d.src_xg = mk(chr(120)+chr(103))\n"
        "d.src_api_fb = mk(chr(97)+chr(112)+chr(105))\n"
        "txt = [t for t in sorted(__import__(chr(103)+chr(108)+chr(111)+chr(98)).glob(%r)) if not t.endswith(%r)]\n"
        "d.collect(txt[0], chr(24503)+chr(30002), net_injury=True)\n"
        "print(json.dumps(called))\n"
    ) % (OL, os.path.join(SNIPPETS, "*.txt"), "_jc.txt")
    r = run_snippet(code)
    assert r.returncode == 0, (r.stderr or "")[-600:]
    line = [x for x in r.stdout.strip().splitlines() if x.startswith("[")]
    assert line, "未捕获调度列表: " + r.stdout[-300:]
    called = json.loads(line[-1]) if False else eval(line[-1])
    assert "news" in called, "net_injury=True 时 news 未被调度"
    for bad in ("euro", "club", "xg", "api"):
        assert bad not in called, "%s 不应在「仅伤停」模式下联网，实际被调度" % bad
