# 初盘位移接入（S4）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把「初盘→即盘的位移强度」从分析报告里的一个发现，变成项目里可测试、可复现、可审计的单一真源模块，并接入 `v259_ingest` / `calc_all` 展示层（只加标签，不改方向判定）。

**Architecture:** 新建独立模块 `scripts/tmp/opening_shift.py`，内含位移计算的全部口径（真初盘读取、热门方向判定、位移强度、推翻判定、三态降级）。`v259_ingest` 调它写一行 txt 头；`calc_all` 解析该行输出展示块。所有口径常量收敛为模块级单一真源，禁止其他文件内联阈值。

**Tech Stack:** Python 3.11+ / pytest / 无新增第三方依赖

**Spec:** `docs/方案_初盘位移接入_2026-10-19.md`（本研究方案）＋ `docs/初盘判定_2026-10-19.md`（441 场证据）

## Global Constraints

- **只加标签，不改方向**：S4 是置信度调节器，不得覆盖 `direction_full` 或 L2 硬核层（AGENTS §5.5 / §6.5）。
- **阈值单一真源**：`S4_SHIFT_MIN_PP = 5.0`、`S4_MID_PP = 3.0`、`S4_STRONG_FAV_PCT = 70.0` 只在 `opening_shift.py` 定义一次，他处一律 import，禁止硬编码。
- **口径三维组合必须同时校验**：`fav_kept`（热门未变）＋ `|conc_pp| ≥ S4_SHIFT_MIN_PP` ＋ `即盘热门 < S4_STRONG_FAV_PCT`。
- **符号约定**：亚盘原始盘口 `正=主让` 与项目 `handi`（`handi = -line`）相反；本模块不碰亚盘，只处理欧赔。
- **平量纲**：交叉特征只允许「同定义概率」相减；禁止「覆盖率概率 − 胜率」。
- **事前变量做控制**：任何分层/匹配不得使用处理后变量（即盘价）作为控制变量。
- **三态标注**：缺真初盘一律 `无数据(原因)`，禁止静默降级为「平稳」。
- **离线**：全程禁止联网（`net_policy.for_analysis()` 恒全关）。
- 现有 340 项测试必须保持全绿。

## Review Focus

- **缺 `init_*` 字段的快照**（老格式 / 字段名变化）：`compute_shift` 必须返回三态 `无数据`，不得抛异常、不得当成「无位移」。
- **初盘与即盘热门方向相同但某一项赔率恰好相等**：`argmin` 首次出现即取，不得因并列产生 IndexError 或随机翻转。
- **位移恰好等于阈值（5.0pp）**：`>=` 口径必须写死并被测试钉住，边界漂移会让触发场次悄悄变化。
- **`conc_pp` 为 NaN / 赔率 ≤1.0**：必须走三态而不是产出 inf 或负数强度。
- **txt 头新增行被旧解析器读到**：`calc_all` 的 `[输入]` 回显只认固定前缀，新行不得打乱既有的多机构合并去水回显。

---

### Task 1: `opening_shift` 核心计算模块

**Files:**
- Create: `scripts/tmp/opening_shift.py`
- Test: `tests/test_opening_shift.py`

**Interfaces:**
- Consumes: 无（新建，零依赖）
- Produces:
  - `S4_SHIFT_MIN_PP: float = 5.0`, `S4_MID_PP: float = 3.0`, `S4_STRONG_FAV_PCT: float = 70.0`
  - `compute_shift(init: tuple[float,float,float] | None, live: tuple[float,float,float] | None) -> dict`
    返回 dict，键固定为：
    `{"state": "ok"|"missing", "reason": str|None, "fav_open": int|None, "fav_live": int|None, "fav_kept": bool|None, "conc_pp": float|None, "fav_live_pct": float|None, "tier": "strong"|"mid"|"flat"|"flip"|"missing"}`
  - `signal_line(result: dict) -> str` — 生成写进 txt 头的一行（`state=="missing"` 时返回三态行）

- [ ] **Step 1: Write the failing test**

Create `tests/test_opening_shift.py`:

```python
# -*- coding: utf-8 -*-
"""opening_shift 单一真源回归测试（S4 位移强度·2026-10-19）。

口径（docs/方案_初盘位移接入_2026-10-19.md）:
  基准 = 澳门欧赔 init_*（真初盘）  终点 = 同一行 live_*
  fav      = 初盘三项赔率最低的方向
  conc_pp  = (1/live[fav] - 1/init[fav]) * 100
  fav_kept = argmin(init) == argmin(live)
  分级: fav 被翻 → flip | |conc|>=5 → strong | 3<=|conc|<5 → mid | 否则 flat
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(ROOT, "scripts", "tmp")

if TMP not in sys.path:
    sys.path.insert(0, TMP)

import opening_shift as OS  # noqa: E402


def test_shift_strong_when_fav_gained_five_pp():
    # 初盘 1.48/3.97/5.40 → 即盘 1.40/4.20/6.00（主胜被加仓）
    r = OS.compute_shift((1.48, 3.97, 5.40), (1.40, 4.20, 6.00))
    assert r["state"] == "ok"
    assert r["fav_open"] == 0 and r["fav_live"] == 0
    assert r["fav_kept"] is True
    # 1/1.40 - 1/1.48 = 0.714286 - 0.675676 = 0.038610 → 3.861pp
    assert abs(r["conc_pp"] - 3.861) < 0.01
    assert r["tier"] == "mid"


def test_shift_strong_tier_at_threshold():
    # 位移恰好跨过 5pp 门槛
    r = OS.compute_shift((1.50, 4.00, 6.00), (1.44, 4.00, 6.00))
    # 1/1.44 - 1/1.50 = 0.694444 - 0.666667 = 0.027778 → 2.778pp
    assert abs(r["conc_pp"] - 2.778) < 0.01
    assert r["tier"] == "flat"

    r2 = OS.compute_shift((1.50, 4.00, 6.00), (1.42, 4.00, 6.00))
    # 1/1.42 - 1/1.50 = 0.704225 - 0.666667 = 0.037558 → 3.756pp
    assert r2["tier"] == "mid"

    r3 = OS.compute_shift((1.50, 4.00, 6.00), (1.38, 4.00, 6.00))
    # 1/1.38 - 1/1.50 = 0.724638 - 0.666667 = 0.057971 → 5.797pp
    assert r3["tier"] == "strong"


def test_shift_flip_when_favorite_changes():
    # 初盘主胜最热 → 即盘客胜最热
    r = OS.compute_shift((2.10, 3.40, 3.30), (2.90, 3.40, 2.20))
    assert r["fav_open"] == 0
    assert r["fav_live"] == 2
    assert r["fav_kept"] is False
    assert r["tier"] == "flip"


def test_shift_counts_drop_as_strength_too():
    # 热门方向被弃（赔率上升）同样算位移强度，符号为负
    r = OS.compute_shift((1.60, 4.00, 5.20), (1.78, 3.90, 4.50))
    # 1/1.78 - 1/1.60 = 0.561798 - 0.625 = -0.063202 → -6.32pp
    assert abs(r["conc_pp"] + 6.320) < 0.01
    assert r["fav_kept"] is True
    assert r["tier"] == "strong"


def test_fav_live_pct_is_devig_share_of_live():
    r = OS.compute_shift((1.50, 4.00, 6.00), (1.50, 4.00, 6.00))
    assert r["fav_live_pct"] is not None
    # 等比例去水后主胜约为 0.6667/1.6667 = 40.0%
    assert abs(r["fav_live_pct"] - 40.0) < 0.5


def test_missing_init_returns_three_state():
    r = OS.compute_shift(None, (1.50, 4.00, 6.00))
    assert r["state"] == "missing"
    assert "初盘" in r["reason"]
    assert r["tier"] == "missing"
    assert r["conc_pp"] is None


def test_missing_live_returns_three_state():
    r = OS.compute_shift((1.50, 4.00, 6.00), None)
    assert r["state"] == "missing"
    assert r["tier"] == "missing"


def test_illegal_odds_returns_three_state():
    # 赔率 <=1.0 非法 → 三态，不得产出 inf
    r = OS.compute_shift((1.00, 4.00, 6.00), (1.50, 4.00, 6.00))
    assert r["state"] == "missing"
    assert r["conc_pp"] is None


def test_tie_breaks_to_first_non_flip():
    # 主胜与客胜同赔（并列最热）→ argmin 取先出现的主胜，两侧一致即不翻
    r = OS.compute_shift((2.50, 3.20, 2.50), (2.50, 3.20, 2.50))
    assert r["fav_open"] == 0
    assert r["fav_live"] == 0
    assert r["fav_kept"] is True
    assert r["conc_pp"] == 0.0


def test_signal_line_contains_three_state_when_missing():
    line = OS.signal_line(OS.compute_shift(None, (1.5, 4.0, 6.0)))
    assert "无数据" in line
    assert "S4" in line


def test_constants_are_single_source():
    assert OS.S4_SHIFT_MIN_PP == 5.0
    assert OS.S4_MID_PP == 3.0
    assert OS.S4_STRONG_FAV_PCT == 70.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_opening_shift.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'opening_shift'`

- [ ] **Step 3: Implement `scripts/tmp/opening_shift.py`**

Module docstring must record the sign convention warning and the "强度而非方向" finding. Implement:

- `_f(x) -> float | None`
- `_devig(o: tuple) -> list[float] | None` — 等比例去水
- `_argmin_dir(o) -> int` — 返回 0/1/2（主/平/客），并列取先出现者
- `compute_shift(init, live) -> dict` — 按 Step 1 测试锁定的键与语义
- `signal_line(result) -> str` — 形如
  `🔴S4初盘位移: 客胜 −7.9pp（初盘 48.5% → 即盘 56.4%）· 热门未变 · 强度档=strong`
  缺失时返回 `🔴S4初盘位移: 无数据(原因: …)`

分级顺序必须先判 `fav_kept`（flip）、再判 `|conc_pp| >= S4_SHIFT_MIN_PP`（strong）、再判 `>= S4_MID_PP`（mid），否则 flat。

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_opening_shift.py -q`
Expected: PASS（11 passed）

- [ ] **Step 5: Run the whole suite**

Run: `python -m pytest tests -q`
Expected: PASS（351 passed：340 旧 + 11 新）

- [ ] **Step 6: Commit**

```bash
git add scripts/tmp/opening_shift.py tests/test_opening_shift.py
git commit -m "feat(s4): 初盘位移强度单一真源模块"
```

---

### Task 2: `v259_ingest` 写入位移行

**Files:**
- Modify: `scripts/tmp/v259_ingest.py`（在 `build()` 的 `L.append` 序列中，紧跟「🔴机构通道统一基线」之后插入）
- Test: `tests/test_v259_ingest.py`（追加一个用例）

**Interfaces:**
- Consumes: `opening_shift.compute_shift` / `opening_shift.signal_line`（Task 1）
- Produces: txt 头新增一行，前缀固定 `🔴S4初盘位移`（`calc_all` 在 Task 3 解析此前缀）

- [ ] **Step 1: Write the failing test**

在 `tests/test_v259_ingest.py` 末尾追加：

```python
def test_ingest_writes_s4_shift_line(tmp_path):
    """v259_ingest 必须把「初盘→即盘位移」写进 txt 头（S4）。"""
    import json
    import subprocess
    import sys

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    inst = os.path.join(root, "scripts", "tmp", "v259_ingest.py")
    snap = SAMPLE_DIR  # 该文件顶部已有的样例快照常量
    out = tmp_path / "out"
    rc = subprocess.run([sys.executable, inst, "--src", snap, "--out", str(out)],
                        capture_output=True, text=True, encoding="utf-8")
    assert rc.returncode == 0, rc.stderr
    txts = list(out.glob("*.txt"))
    assert txts, "no txt produced"
    head = txts[0].read_text(encoding="utf-8")
    assert "🔴S4初盘位移" in head
```

> 若 `tests/test_v259_ingest.py` 没有现成的 `SAMPLE_DIR`，按该文件已有的样例快照常量取名并复用，不要新建 fixture。

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_v259_ingest.py::test_ingest_writes_s4_shift_line -q`
Expected: FAIL — `AssertionError: assert '🔴S4初盘位移' in ...`

- [ ] **Step 3: Implement**

在 `v259_ingest.py` 顶部 `import ou_from_asia as OA` 附近加 `import opening_shift as S4`，并在 `build()` 里 `L.append('🔴机构通道统一基线 …')` 之后插入：

```python
    _s4 = S4.compute_shift(base_init, base_live)
    L.append(S4.signal_line(_s4))
```

> `base_init` / `base_live` 已是本函数内的真初盘与即盘三元组，直接复用，不得重新读快照。

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_v259_ingest.py -q`
Expected: PASS

- [ ] **Step 5: Run the whole suite**

Run: `python -m pytest tests -q`
Expected: PASS

- [ ] **Step 6: Regenerate today's batch and eyeball one file**

Run:
```bash
python scripts/tmp/v259_ingest.py --src "F:/ocr_python_data/football-research/data-2.5.9/_by_category/竞足" --out data/tmp/batch_v259W
head -20 "data/tmp/batch_v259W/10-19_02_45_意甲_尤文图斯_vs_拉齐奥.txt"
```
Expected: 头部出现 `🔴S4初盘位移: …` 一行，且原有各行次序未变。

- [ ] **Step 7: Commit**

```bash
git add scripts/tmp/v259_ingest.py tests/test_v259_ingest.py
git commit -m "feat(s4): v259_ingest 输出初盘位移行"
```

---

### Task 3: `calc_all` 展示位移块

**Files:**
- Modify: `scripts/tmp/calc_all.py`（`CHECKLIST` 增 `C35`；新增 `_s4_block(txt_path)`；在 `main()` 的多机构合并去水回显附近调用）
- Test: `tests/test_calc_all_passthrough.py`（追加用例）

**Interfaces:**
- Consumes: txt 头 `🔴S4初盘位移` 行（Task 2）
- Produces:
  - `_s4_block(txt_path: str) -> list[str]` — 返回待打印行；无该行时返回三态单行
  - `CHECKLIST` 新条目 `('C35', 'S4 初盘位移强度(只加标签·不改方向)', None, 'opening_shift')`

- [ ] **Step 1: Write the failing test**

在 `tests/test_calc_all_passthrough.py` 末尾追加：

```python
def test_s4_block_reads_shift_line(tmp_path):
    """calc_all 必须回显并标注 S4 位移行，且不改写方向。"""
    import sys
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tmp = os.path.join(root, "scripts", "tmp")
    if tmp not in sys.path:
        sys.path.insert(0, tmp)
    import calc_all as CA

    p = tmp_path / "m.txt"
    p.write_text(
        "🔴S4初盘位移: 客胜 −7.9pp（初盘 48.5% → 即盘 56.4%）· 热门未变 · 强度档=strong\n",
        encoding="utf-8")
    lines = CA._s4_block(str(p))
    joined = "\n".join(lines)
    assert "S4" in joined
    assert "strong" in joined
    assert "只加标签" in joined or "不改方向" in joined


def test_s4_block_three_state_when_absent(tmp_path):
    import sys
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tmp = os.path.join(root, "scripts", "tmp")
    if tmp not in sys.path:
        sys.path.insert(0, tmp)
    import calc_all as CA

    p = tmp_path / "m.txt"
    p.write_text("赛事：x\n", encoding="utf-8")
    joined = "\n".join(CA._s4_block(str(p)))
    assert "S4" in joined
    assert "无数据" in joined


def test_checklist_registers_c35():
    import sys
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tmp = os.path.join(root, "scripts", "tmp")
    if tmp not in sys.path:
        sys.path.insert(0, tmp)
    import calc_all as CA

    ids = [c[0] for c in CA.CHECKLIST]
    assert "C35" in ids
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_calc_all_passthrough.py -q -k s4`
Expected: FAIL — `AttributeError: module 'calc_all' has no attribute '_s4_block'`

- [ ] **Step 3: Implement**

1. `CHECKLIST` 追加 `('C35', 'S4 初盘位移强度(只加标签·不改方向)', None, 'opening_shift')`
2. 新增函数（放在 `_layer_state_lines` 之后）：

```python
def _s4_block(txt_path):
    """S4 初盘位移展示块——只回显 v259_ingest 写入的行，不重算、不改方向。"""
    line = None
    try:
        for _ln in open(txt_path, encoding='utf-8').read().split('\n'):
            if _ln.strip().startswith('🔴S4初盘位移'):
                line = _ln.strip()
                break
    except Exception:
        line = None
    if not line:
        return ['  🔴S4初盘位移: 无数据(原因: 输入未提供真初盘·非 v259_ingest 产出)',
                '    → S4 为置信度调节器·本场不参与']
    return ['  ' + line,
            '    → S4 只加标签·不改方向·不覆盖 L2 硬核（AGENTS §5.5）',
            '    → 回测 n=441: |位移|≥5pp & 热门未变 = 73.6% vs 稳定 55.3%'
            '(Bootstrap CI [+0.068,+0.291])·仅 60-70% 档打平']
```

3. 在 `main()` 的 `[输入]` 回显循环之后调用：

```python
    for _ln in _s4_block(txt_path):
        print(_ln)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_calc_all_passthrough.py -q`
Expected: PASS

- [ ] **Step 5: Run the whole suite**

Run: `python -m pytest tests -q`
Expected: PASS

- [ ] **Step 6: End-to-end eyeball**

Run:
```bash
python scripts/tmp/calc_all.py "data/tmp/batch_v259W/10-19_02_45_意甲_尤文图斯_vs_拉齐奥.txt" seriea --eu 1.48,3.97,5.40 --handi -0.75 --o25 1.94 --u25 2.06 --water 1.77 | Select-String "S4"
```
Expected: 打印 S4 块三行，且后续「方向(欧亚综合)」行与改动前完全一致（用 `git stash` 前后各跑一次比对）。

- [ ] **Step 7: Commit**

```bash
git add scripts/tmp/calc_all.py tests/test_calc_all_passthrough.py
git commit -m "feat(s4): calc_all 展示初盘位移块 + C35 必核项"
```

---

### Task 4: 口径守卫与 D1 档案降级

**Files:**
- Create: `tests/test_s4_guards.py`
- Modify: `scripts/tmp/opening_shift.py`（补断言/守卫）
- Modify: `data/tmp/learned_rules.json`（新增 D1 否定证据条目）

**Interfaces:**
- Consumes: `opening_shift`（Task 1）
- Produces: 无新接口；本条只加固已存在行为与登记结论

- [ ] **Step 1: Write the failing test**

Create `tests/test_s4_guards.py`:

```python
# -*- coding: utf-8 -*-
"""S4 口径守卫（2026-10-19·三次踩坑的固化）。

三个坑：
  1. 不同量纲相减（覆盖率概率 − 胜率）→ 交叉特征必须同定义
  2. 亚盘原始盘口符号与 handi 相反 → 本模块不碰亚盘，碰到即报错
  3. 用处理后变量（即盘）做控制变量 → 分层必须用事前变量
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(ROOT, "scripts", "tmp")

if TMP not in sys.path:
    sys.path.insert(0, TMP)

import opening_shift as OS  # noqa: E402


def test_compute_shift_rejects_asian_line_input():
    """传进来的必须是 3 元欧赔；亚盘盘口(含负数)必须被拒绝。"""
    r = OS.compute_shift((-0.75, 0.83, 1.01), (1.48, 3.97, 5.40))
    assert r["state"] == "missing"


def test_compute_shift_rejects_wrong_arity():
    r = OS.compute_shift((1.48, 3.97), (1.48, 3.97, 5.40))
    assert r["state"] == "missing"


def test_learned_rules_records_d1_negative_evidence():
    p = os.path.join(ROOT, "data", "tmp", "learned_rules.json")
    if not os.path.exists(p):
        import pytest
        pytest.skip("learned_rules.json 未随公开版分发")
    d = json.load(open(p, encoding="utf-8"))
    assert "d1_heuristic_only" in d
    e = d["d1_heuristic_only"]
    assert "启发式" in e["rule"] or "heuristic" in e["rule"].lower()
    assert "441" in e["evidence"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_s4_guards.py -q`
Expected: FAIL — 前两例因当前 `compute_shift` 未做 arity/符号守卫而失败（或抛 ValueError 而非返回三态）；第三例因 `learned_rules.json` 无该键而失败。

- [ ] **Step 3: Implement**

1. `compute_shift` 开头加守卫：非 3 元 → `missing`；任一值 ≤1.0 或 <0 → `missing`（负值即亚盘盘口误传）
2. `data/tmp/learned_rules.json` 追加键（保持既有值不动）：

```json
"d1_heuristic_only": {
  "count": 1,
  "status": "已证伪(大样本)",
  "evidence": [
    "441 场真初盘: D1触发 55.2%(n=67) vs 未触发 59.1%(n=374), p=0.277 不显著; 用 tl 时序重测方向相反(58.1% vs 57.7%)"
  ],
  "last_seen": "2026-10-19",
  "rule": "D1(主方向升赔≥2时点累计>3%→硬降级) 保留为保守启发式(降档成本不对称)·禁止当作已验证规律引用",
  "_auto": "反证登记(防误引)"
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_s4_guards.py -q`
Expected: PASS

- [ ] **Step 5: Run the whole suite**

Run: `python -m pytest tests -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add scripts/tmp/opening_shift.py tests/test_s4_guards.py data/tmp/learned_rules.json
git commit -m "fix(s4): 口径守卫(arity/符号)+ D1 反证登记"
```
