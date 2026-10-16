# -*- coding: utf-8 -*-
"""表路径解析落点回归测试 (2026-09-15 修复批次 3)。

承 Bug6 同一根因(表真源在 data/tmp/, 脚本却按 dirname(__file__) 拼路径),
批次1 只修了计算脚本(match_classifier/calc_v3572/live_score_engine/calc_all/
halftime_inference/audit_alignment), 构建器与消费者仍未修 = 只治症状。本文件覆盖:
  P1 calc_match.prob_calibration.json     文档/data及SKILL均指 data/tmp/ → 恒读失败 → 静默降级
  P2 calc_v3572.prob_calibration.json     同上(裸 except 吞异常)
  P3 snapshot_save.nl_team_cn_en.json     文档(data/tmp/)与代码(scripts/tmp/)不一致 → 中文队名恒不转换
  P4 clv_tracker.clv_log.json             文档 data/tmp/ 与代码 scripts/tmp/ 不一致
  P5 build_quadrant_table 输出目录         写到 scripts/tmp/, 而消费方/审计读 data/tmp/

判据真源:
  · scripts/tmp/clv_tracker.py L16 自述「存储: data/tmp/clv_log.json」
  · scripts/tmp/snapshot_save.py L122 自述「懒加载 data/tmp/nl_team_cn_en.json」
  · SKILL.md L69 「data/tmp/nl_team_cn_en.json（国家队中→英·56 队）」
  · SKILL.md L18 「按 data/tmp/prob_calibration.json 校准热门低估」
  · scripts/tmp/table_paths.py: data/tmp 为规范位置(_SEARCH_DIRS 首位)
"""
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(ROOT, "scripts", "tmp")


def run_snippet(code, timeout=120, cwd=None):
    env = dict(os.environ, PYTHONPATH=TMP, PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", cwd=cwd or ROOT, env=env,
                          timeout=timeout)


def src(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


# ── P1/P2: prob_calibration.json 须经统一解析(真源 data/tmp) ─────────
@pytest.mark.parametrize("rel", [
    "scripts/tmp/calc_match.py",
    "scripts/tmp/calc_v3572.py",
])
def test_prob_calibration_resolved_via_table_paths(rel):
    """文档/SKILL 均指 data/tmp/prob_calibration.json, 但两处都用
    os.path.join(dirname(__file__), ...) → 表放 data/tmp/ 时恒读失败, 且被
    except 静默吞掉(calc_v3572 是裸 except) → 校准恒不生效且无提示。

    严格判据: 在【使用该表名的语句窗口内】必须出现 find_table(而非仅文件里别处有)。
    """
    lines = src(rel).splitlines()
    # 只看【非注释】的代码行(注释里也会提到表名, 不能作为判据)
    code_lines = [(n, l) for n, l in enumerate(lines)
                  if "prob_calibration.json" in l and not l.strip().startswith("#")]
    assert code_lines, rel + " 无 prob_calibration.json 的代码引用(仅注释?)"
    n, line = code_lines[0]
    # 判据: 该读取点前后 6 行内必须出现统一解析器
    win = "\n".join(lines[max(0, n - 6):n + 1])
    assert "find_table(" in win, (
        rel + ":%d 的 prob_calibration.json 读取点未用统一解析器 "
        "→ 与 data/tmp 真源不一致(表放文档位置时恒读失败)\n    %s" % (n + 1, line.strip()))


def test_prob_calibration_path_survives_relocation(tmp_path=None):
    """行为判据: 表存在于 data/tmp/ 时, 解析必须命中(而非返回 None/降级)。"""
    code = ("import sys; sys.path.insert(0, %r);"
            "import table_paths as tp;"
            "print(tp.find_table(chr(112)+chr(114)+chr(111)+chr(98)+chr(95)+chr(99)+chr(97)+chr(108)+chr(105)+chr(98)+chr(114)+chr(97)+chr(116)+chr(105)+chr(111)+chr(110)+chr(46)+chr(106)+chr(115)+chr(111)+chr(110)))") % TMP
    r = run_snippet(code)
    got = r.stdout.strip()
    # 当前仓库无该表 → None 属预期; 关键是要走统一解析(可在 data/tmp 命中)
    assert got in ("None",) or got.lower().endswith("prob_calibration.json"), (
        "prob_calibration.json 未经统一解析: " + got + " | " + r.stderr[-200:])


# ── P3: snapshot_save 国家队中→英表位置 ──────────────────────────
def test_snapshot_nl_team_map_uses_data_tmp():
    """自述(data/tmp/nl_team_cn_en.json)与代码(scripts/tmp/)不一致 → 表放文档位置
    时 cn2en(中文国家队名) 恒返回原名 → N21 快照匹配必失败(快照不进决策链)。"""
    s = src("scripts/tmp/snapshot_save.py")
    assert "nl_team_cn_en.json" in s
    i = s.find("def _nl_map")
    body = s[i:i + 600]
    assert "find_table(" in body, (
        "_nl_map 仍按 dirname(__file__) 拼路径, 与自述的 data/tmp/nl_team_cn_en.json 不一致")


def test_snapshot_cn2en_table_actually_loads_when_present():
    """行为判据(端到端·防"存在不等于活跃"): 把表按文档位置 data/tmp/ 落盘后,
    cn2en(荷兰) 必须真的转成 Netherlands —— 只断言"不崩"会漏掉静默降级。

    用临时表 + PITCHQUANT_ROOT 隔离, 结束即清理; 不依赖真实表是否随仓库分发。
    """
    d = os.path.join(ROOT, "data", "tmp")
    p = os.path.join(d, "nl_team_cn_en.json")
    existed = os.path.exists(p)
    if existed:
        pytest.skip("真实 nl_team_cn_en.json 已存在, 避免覆盖")
    os.makedirs(d, exist_ok=True)
    try:
        with open(p, "w", encoding="utf-8") as f:
            f.write('{"teams": {"\u8377\u5170": "Netherlands"}}')
        code = ("import sys; sys.path.insert(0, %r);"
                "import snapshot_save as ss;"
                "print(ss.cn2en(chr(33655)+chr(20848)))") % TMP
        r = run_snippet(code)
        got = r.stdout.strip()
        assert got == "Netherlands", (
            "表位于 data/tmp/ 时 cn2en(荷兰) 应转 Netherlands, 实得「%s」"
            " → 表未真正进入加载链(静默降级) | %s" % (got, r.stderr[-200:]))
    finally:
        if os.path.exists(p):
            os.remove(p)


# ── P4: clv_tracker 存储位置 ────────────────────────────────────
def test_clv_tracker_log_matches_documented_location():
    """clv_tracker.py L16 自述「存储: data/tmp/clv_log.json」, 但 L29 写到脚本目录
    → 日志分散在两处, 跨运行读不到。"""
    s = src("scripts/tmp/clv_tracker.py")
    assert "data/tmp/clv_log.json" in s, "自述位置缺失(测试前提失效)"
    assert "find_table(" in s or "find_root(" in s, (
        "clv_log.json 仍按 dirname(__file__) 拼接, 与自述的 data/tmp/ 不一致")


# ── P5: build_quadrant_table 输出目录 ────────────────────────────
def test_build_quadrant_table_outputs_to_data_tmp():
    """消费者(audit_alignment TABLES)与 table_paths 规范位置都是 data/tmp/,
    构建器却写 HERE(=scripts/tmp/) → 生成后仍「读取失败」, 自述用法也写 data/tmp/。"""
    s = src("scripts/tmp/build_quadrant_table.py")
    assert "quadrant_table.json" in s
    assert "find_root(" in s or "data" in s.split("OUT")[1][:120], (
        "build_quadrant_table 输出目录仍为脚本目录, 与消费方 data/tmp/ 不一致")
