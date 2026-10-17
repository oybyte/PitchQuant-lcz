# -*- coding: utf-8 -*-
"""校准表与大小球判向 回归测试（2026-10-17 调整批次）。

背景（441 场盲测实测）:
  · P0  prob_calibration.json 缺失 → 442 场全部打印「去水校准未生效」，
        实测热门确被低估（55-65%档 +15.0pp / 75-85%档 +4.6pp）→ 校准表应存在且可用。
  · P1  大小球「判小球」72 场命中恰 50.0%（真随机，反转同为 50%，不可利用），
        而「判大球」235 场命中 68.5% → 小球档应标「中性·不判」。

设计纪律（项目「数据链三层风险」）:
  本次改动全部落在 ③展示/判定层（新增标注/收敛判向），不触碰 ①输入解析。
"""
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(ROOT, 'scripts', 'tmp')
DATA_TMP = os.path.join(ROOT, 'data', 'tmp')
CALIB = os.path.join(DATA_TMP, 'prob_calibration.json')
BATCHES = ["batch_2_5_8", "batch_74", "batch_140", "batch_203"]


def run_snippet(code, timeout=180):
    env = dict(os.environ, PYTHONPATH=TMP, PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", cwd=ROOT, env=env,
                          timeout=timeout)


# ══════════ P0: 校准表 ══════════
def test_calibration_table_exists():
    """校准表必须存在于 data/tmp/（441 场全部报「校准未生效」的根因就是它缺失）。"""
    assert os.path.exists(CALIB), (
        "data/tmp/prob_calibration.json 不存在 → calc_match/calc_v3572 均打印「去水校准未生效」")


def test_calibration_table_schema():
    """格式须为 {lo-hi: {bias_pp: float}}，且区间连续覆盖 0-1、无重叠。"""
    d = json.load(open(CALIB, encoding="utf-8"))
    assert isinstance(d, dict) and d, "校准表应为非空 dict"
    spans = []
    for k, v in d.items():
        if k.startswith("_"):        # 元信息键（_meta）不是概率档，跳过
            continue
        lo, hi = k.split("-")
        lo, hi = float(lo), float(hi)
        assert lo < hi, "区间下界须小于上界: %s" % k
        assert "bias_pp" in v and isinstance(v["bias_pp"], (int, float)), "缺 bias_pp: %s" % k
        spans.append((lo, hi))
    spans.sort()
    assert abs(spans[0][0] - 0.0) < 1e-9, "最低区间应从 0 开始"
    assert abs(spans[-1][1] - 1.0) < 1e-9, "最高区间应到 1.0"
    for a, b in zip(spans, spans[1:]):
        assert abs(a[1] - b[0]) < 1e-9, "区间必须连续无缝: %s -> %s" % (a, b)


def test_calibration_actually_applies():
    """行为判据（防「存在≠活跃」）: 导入 calc_v3572 并调 direction_full,
    不得再出现「去水校准未生效」提示。"""
    code = (
        "import sys\n"
        "sys.path.insert(0, %r)\n"
        "import calc_v3572 as C\n"
        "r = C.direction_full(1.50, 4.20, 6.00, over25=1.90)\n"
        "hints = r.get(chr(25191)+chr(34892)+chr(25552)+chr(31034)) or []\n"
        "bad = [h for h in hints if chr(21435)+chr(27700)+chr(26657)+chr(20934) in h]\n"
        "print(json.dumps({'calib_warn': len(bad), 'probs': [r.get(k) for k in ('主胜','平局','客胜')]}, ensure_ascii=False))\n"
        "import json\n"
    ) % TMP
    # 需在 json 已导入后使用, 调整顺序
    code = (
        "import sys, json\n"
        "sys.path.insert(0, %r)\n"
        "import calc_v3572 as C\n"
        "r = C.direction_full(1.50, 4.20, 6.00, over25=1.90)\n"
        "hints = r.get(chr(25191)+chr(34892)+chr(25552)+chr(31034)) or []\n"
        "bad = [h for h in hints if chr(21435)+chr(27700)+chr(26657)+chr(20934) in h]\n"
        "print(json.dumps({'calib_warn': len(bad)}, ensure_ascii=False))\n"
    ) % TMP
    r = run_snippet(code)
    assert r.returncode == 0, "direction_full 调用失败: " + (r.stderr or "")[-500:]
    line = [x for x in r.stdout.strip().splitlines() if x.startswith("{")]
    assert line, "无输出: " + r.stdout[-300:]
    got = json.loads(line[-1])
    assert got["calib_warn"] == 0, (
        "direction_full 仍报「去水校准未生效」→ 校准表未被真正加载")


# ══════════ P1: 大小球小球档 ══════════
def test_small_ball_direction_demoted_to_neutral():
    """判小球命中仅 50%(真随机) → 应降级为「中性·不判」，不得输出「小球」。"""
    src_path = os.path.join(TMP, "calc_all.py")
    s = open(src_path, encoding="utf-8").read()
    # 允许出现「小球」字样, 但必须有明确的降级逻辑标记
    assert ("SMALL_BALL_NEUTRAL" in s) or ("小球不判" in s) or ("小球档停判" in s), (
        "calc_all.py 未见「小球档降级为中性」的实现标记 → 小球仍会输出高置信判向")


def test_small_ball_marked_neutral_in_output():
    """行为判据: 用一份 o25>1.90 的样本跑 calc_all，输出不得给出「小于」判向，
    而应标为中性/不判。"""
    cands = []
    for b in BATCHES:
        p = os.path.join(DATA_TMP, b, "meta.json")
        if not os.path.exists(p):
            continue
        for m in json.load(open(p, encoding="utf-8")):
            o = m.get("o25")
            if o and o > 1.92:
                cands.append(os.path.join(DATA_TMP, b, m["slug"] + ".txt"))
    if not cands:
        pytest.skip("无 o25>1.92 样本")
    txt = cands[0]
    # 取该场 meta 参数
    slug = os.path.basename(txt)[:-4]
    meta = None
    for b in BATCHES:
        p = os.path.join(DATA_TMP, b, "meta.json")
        if not os.path.exists(p):
            continue
        for m in json.load(open(p, encoding="utf-8")):
            if m.get("slug") == slug:
                meta = m; break
        if meta: break
    assert meta, "找不到 meta: " + slug
    args = [sys.executable, os.path.join(TMP, "calc_all.py"), txt, meta["league"],
            "--eu", "%.3f,%.3f,%.3f" % tuple(meta["pin"][1:4]),
            "--o25", str(meta["o25"]), "--u25", str(meta["u25"])]
    if meta.get("handi") is not None:
        args += ["--handi", "%g" % meta["handi"]]
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                       cwd=ROOT, timeout=300)
    out = r.stdout or ""
    assert "量级(" in out, "calc_all 未产出量级段: " + (r.stderr or "")[-300:]
    # 该档应显式中性/不判
    assert ("中性" in out) or ("不判" in out), (
        "o25>1.92 的场次未出现「中性/不判」标记 → 小球仍被当作有效判向输出")
