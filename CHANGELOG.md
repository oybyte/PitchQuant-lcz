# Changelog · 更新日志

所有重要变更记录于此。格式参考 [Keep a Changelog](https://keepachangelog.com/)。
All notable changes to this project are documented here.

---

## [1.0.0] — 2026-09-19 · 首个公开发布 / First Public Release

### ✨ Added · 新增

**核心组件**
- **34 个 knowledge skills**（规则体系 / 五大联赛子模型 / 裁判规则 / 审计与维护纪律）
- **139 个确定性计算脚本**（去水 · 凯利 · 泊松 + Dixon-Coles · 比分深度查表 · 现场多源融合引擎 · 一致性校验）
- **9 张回测蒸馏表**（联赛基准 / 进球档 / 比分深度 / 水位意图 / 平局温度 / 深度锚 / 半全场条件矩阵…）
- **分析输出模板 + 案例模板**

**Prompt 规范集**（`prompts/`·本项目最具辨识度的部分）
- `01-analyze-a-match.md` — 9 步分析执行规范 + 七条铁律
- `02-self-check-and-patch.md` — 完成度自查与补充（含**历史高频遗漏黑名单**）
- `03-independent-audit.md` — 分析结果独立审计
- `04-audit-the-model.md` — 模型工程审计（12 探查 + 8 维含**实际运行验证**）

**文档**（中英双语 · bilingual）
- `docs/architecture.md` — 四层架构 + 规则优先级 L1–L5 + 四道质量门
- `docs/methodology.md` — 关键回测结论 + **数学公式**（de-vigging / Poisson / Dixon-Coles τ / Kelly）
- `docs/getting-started.md` — 操作手册（输入格式 / 参数 / 输出解读 / FAQ / 故障排查）
- `docs/data-and-apis.md` — **数据与 API 清单**（你需自备什么 / 免费额度 / 降级行为）

**工程**
- `examples/sample-odds.txt` — **真实格式样例**（9 节 · 逐 T 变动 · 全功能激活）
- `examples/case-monza-vs-sassuolo.md` — 脱敏真实案例（含一次误判复盘）
- **`data/` 兼容层** — 使 `git clone` 后即可直接运行（无需调整目录结构）
- CI（`.github/workflows/ci.yml`）：语法检查 + 数据表完整性 + **密钥残留扫描**
- `.gitattributes`（统一行尾）· `.gitignore`（排除密钥/原始数据/运行产物）

**法律文件**
- `DISCLAIMER.md` — 8 条法律条款（项目性质 / 禁止用途 / 无保证 / 第三方权利 / 合规责任 / 责任限制 / 版权 / 效力）
- `NOTICE.md` — 数据来源与致谢 + 第三方商标归属 + **竞彩数据来源合法性声明**
- `LICENSE` — MIT

### 🔄 Changed · 变更

- **项目命名**：`football-odds-model` → **`PitchQuant`**（Pitch × Quant）
- **README 重构**：电梯 pitch · **真实输出预览**（替代 GIF）· 技术关键词块（SEO）· Star History · 联系方式 · 全站双语
- **methodology 强化**：补充公式与复现步骤（3.5KB → 9KB）
- **Further Reading 表**：改为逐条中英对照

### 🗑️ Removed · 移除

- **全部私有数据依赖**：SQL 相关脚本（7 个）与 skills 中的相关描述（已改为通用表述）
- **遗留临时/测试脚本**（10 个：`_verify_*` / `_plan*` / `*_test` / 内部维护工具）
- **原始数据**（`Matches.csv` 43MB · SQL dump · 欧战库 —— 体积与来源条款限制，不发布）

### 🔐 Security & Compliance · 安全与合规

- **全量敏感清洗**：明文 API key → 环境变量 · 本机路径 → 占位符 · 失效旧 key → 前缀掩码（三扫归零）
- **完整数据致谢**：Football-Data.co.uk（赛果/赔率）· ClubElo（ELO）· xgabora/Club-Football-Match-Data（整合数据集·**按作者要求正式引用**）· 中国体育彩票官网（公开赔率）
- **合规边界声明**：学术用途 · 禁止博彩 · **博彩用途许可责任明确转移**（Football DataCo / Genius Sports）

### ✅ Verified · 验证

- **端到端实测**：从 GitHub 重新 clone → CI 三项检查全过 → README 承诺命令全部跑通 → 样例全功能激活
- 语法编译 exit=0 · 9 张表 JSON 可读 · 数据文件 6/6 可读

---

## [1.0.1] — 2026-10-17 · 全链路缺陷修复 / Pipeline Defect Fixes

> 触发：对 `data-2.5.9` 待赛 22 场做端到端分析时暴露 11 项缺陷。改动落在 ②计算层与 ③展示/判定层，
> **不改模型口径**（方向铁依据 / 命中口径 / 去水算法均不变）。新增 64 项回归测试（总数 115 → 179）。

### 🔧 Fixed · 修复

| 编号 | 缺陷 | 修复 |
|:--|:--|:--|
| **P0-1** | `calc_all` 不向 `calc_match` 透传 `--eu/--handi/--o25/--u25/--water` → V5 跨市场分歧与有效凯利恒空（实测 22/22 场） | 组命令时逐项透传 |
| **P0-2** | `calc_match.trap_classify_output` 只有定义、**零调用点** → C16 诱阻识别永久失效 | 接线 `run_extensions`；实现收敛为委托 `match_classifier`（消除双实现） |
| **P0-3** | 净胜档候选按体彩让球 L（固定 −1/0/+1）取，**亚盘线从未进解析**（23/23 场两值不一致，平手场被硬抬成主让 1 球） | 亚盘线为唯一依据；输出 `[netmargin-handi]` 双轨对照 |
| **P0-4** | 无「亚洲四分之一线 → O2.5」折算模块，现场推导易错（首版算错导致 22 场 O2.5 全偏高） | 新增 `scripts/tmp/ou_from_asia.py`（EV 中性拆半注·7 类线型·拒绝未覆盖线型） |
| **P1-1** | `anchor_market_check` 用未回测经验公式给出「必须采用」的建议锚，与「禁机械照搬」冲突 | 改输出 `constraints` + `violations`；`suggestion` 降级为「约束内候选参考」；经验公式加 `未回测` 标注 |
| **P1-2** | SKILL 要求伤停缺失必留痕，脚本层无落点（0/23 场） | `calc_all` 恒打伤停三态行 |
| **P1-3** | `prediction_log` 沿用输入基名 → 同场因空格/下划线产生双份、`--help.json` 落盘 | 规范化为 `YYYY-MM-DD_HHMM_联赛_主队_vs_客队.json` |
| **P1-4** | SKILL 宣称必传 `--max_h/--max_d/--max_a`，脚本却报「未知参数」→ 修正35 从未被消费 | 改为自动解析输入头「最高价/最低价」行 |
| **P2-1** | HAF / ELO / xG 三层缺失写法不统一，`calc_all` 侧 HAF 与 xG 完全无声 | 新增 `_layer_state_lines()`：三行恒输出，缺失必写原因 |
| **P2-2** | HAF 对抗耦合三项平均中 `(基准 − 主队失球)` 可为负 → 强客队被系统性低估（PSG 客场 λ 2.35→1.28） | 改**乘性（泊松对数线性）**耦合 + 守卫（`|Δλ|>0.5` 只标注）；建表拆出使公开版可无 CSV 查表 |
| **P2-3** | 弱共识门限两处不一致（150% vs 130%）→ 130–150% 区间出两种结论 | `WEAK_SKEW_PCT=150` 单一真源 |

### ✨ Added · 新增

- `scripts/tmp/ou_from_asia.py` —— 亚洲盘四分之一线 → O2.5/U2.5 折算（此前完全缺失）
- `tests/test_ou_from_asia.py` / `test_calc_all_passthrough.py` / `test_trace_and_anchor.py` /
  `test_books_skew_haf.py` / `test_three_state_layers.py` / `test_antiregression.py`（共 64 项）
- CI 之外本地门禁：`python -m pytest tests -q`（README 第 6 步已加入）

### 🔄 Changed · 变更

- `AGENTS.md` 新增硬性纪律第 7–12 条（亚盘线为准 / O2.5 禁手算 / 锚由模型定 / HAF 乘性 / 门限单一真源 / 跨机构自动解析）
- `SKILL.md` 增补修复表与口径变更点；`calc_all` 参数行删除已废弃的 `--net` 与 `--max_*` 必传要求
- `calc_homeaway.py` 重构为可导入模块（`haf_couple` / `haf_couple_checked`），建表逻辑移入 `_build_table()`
- `check_sync.py` 公开版可用化（见下）

### 🔧 check_sync.py 公开版可用化（原第 2 条校验即崩栈）

| 项 | 修复前 | 修复后 |
|:--|:--|:--|
| 可执行校验 | **1 条**（第 2 条 FileNotFoundError 崩栈） | **238 条** |
| 结果 | 崩溃，无输出 | ✅161 / ⚠️0 / ❌0 / ⏭️77 |
| 退出码 | 非 0（崩溃） | 0（仅 SKIP 时） |

- **① 纯路径差异**：`.reasonix/skills/` → `skills/`（33 处）、`data/analysis_template.md` → `templates/`。公开版技能目录一直存在，只是路径名不同
- **② 脚本自身 bug**：`VER='V3.5.74'` 而 `VER_RE=r'V3\.5\.72'` → 「AGENTS.md 含 V3.5.74」恒报 ❌；另修 4 处过时判据（联赛 skill `==5` 实为 6、`_netflag` 已在联网策略重构中移除、硬编码 `~/Desktop` 本机路径）
- **③ 公开版确实没有的资产**：`Matches.csv` / `europe/` / `case-library/` / `online_learning/` / `足球分析模型.txt`，以及仅完整版 AGENTS.md 收录的 30+ 长尾小节 → 显式 SKIP 并打印原因与路径
- **实现**：零侵入包装四个内建名（`open` / `os.listdir` / `glob.glob` / `os.path.exists`），不改 180 处调用点
- **诚实性**：被 SKIP 的「代码脚本检查」条数为 **0** —— 跳过项全部是数据资产与文档小节

### 🔧 anchor 候选参考方向约束

- **缺陷**：同一块输出自相矛盾 —— 判 `1:1` 违反方向，却又把 `1:1` 列为「约束内候选参考」
- **根因**：上版给 `anchor_market_check` 加了 `direction` 交叉校验（能发现冲突），但**推荐筛选那段没跟着改**——只检查净胜档/大小球/盘口，漏了 direction；兜底候选表同样未过滤
- **修复**：建议锚与兜底候选均按方向裁剪。方向=主胜 → `1:0/2:1/2:0`；方向=客胜 → `0:1`

### ✅ 测试

- 共 **209 项**（115 → 209），含 `test_check_sync_portable.py`（7 项：不得崩栈/执行数/SKIP 带原因/VER_RE 自洽/退出码语义）
- 关键用例做过红绿验证：移除修复 → 立即变红，恢复 → 变绿
- `scripts/tmp/v259_consistency.py`：数值自洽体检（skew 与隐含一致 / λ 与聚合同向 / 概率和=100 / 锚是否含方向），实测**0 异常**

---

## 关于版本编号 / Versioning Notes

- **本仓库 = Core Model V3.5.74 的公开快照**（`Public Release v1.0 | Core Model V3.5.74`）
- 内部模型版本与公开发布版本**独立演进**：
  - **Core Model V3.5.74** = 完整研究系统的内部版本（含私有数据集与运行环境）
  - **Public Release v1.x** = 面向公开分享的快照（去除私有数据 · 补充文档与合规声明）
- 后续公开发布将在本文件追加条目；内部模型演进不逐条同步至此

---

> ⚠️ **FOR ACADEMIC & EDUCATIONAL USE ONLY** · 仅用于学术交流与技术学习 · **严禁用于博彩/投注** · 完整法律条款: [DISCLAIMER.md](DISCLAIMER.md)
