# -*- coding: utf-8 -*-
"""net_policy.py —— 联网策略唯一真源（2026-10-18）

🔴 用户策略（本文件是唯一权威，任何入口不得自行拼装开关）:

  ┌ 场景 ────────────────┬ 联网 ────────────────────────────────┐
  │ 分析 / 预测比赛        │ ❌ **绝对禁止**（无开关·不可开启）        │
  │ 复盘（赛后）           │ ⚠️ 默认**离线**；用户明确要求时才可联网   │
  │ 其他（配置/调试/工具）  │ ✅ 允许                                │
  └───────────────────────┴────────────────────────────────────────┘

  · 禁止申请 / 内置 api key —— 本模块不读取、不缓存任何密钥。
  · 「分析禁止联网」是**结构性约束**：for_analysis() 恒返回全关，
    且不提供任何参数可以打开 —— 命令行 --net 也无法绕过（见 ignore_flags 签名）。

为什么用模块而不是各入口各写一份:
  原实现三处入口策略互相不一致 ——
    · calc_all.py     : --net 可选（默认关，但可开）
    · learn.py        : net=not no_net → **默认联网**（与「复盘默认离线」直接冲突）
    · refresh_predlog : --net 可选
  策略分散 → 必然漂移。收敛为单一真源后，审计只需看这一个文件。

用法:
  import net_policy as NP
  kw = NP.for_analysis()                 # 分析：恒全关
  kw = NP.for_review()                   # 复盘：默认全关
  kw = NP.for_review(allow=True)         # 复盘：用户明确要求时
  kw = NP.for_tooling()                  # 其他：允许
  data_bridge.collect(txt, league, **kw) # 直接解包
"""

MODES = ("analysis", "review", "tooling")

_ALL_ON = {"net_injury": True, "net_odds": True, "net_form": True}
_ALL_OFF = {"net_injury": False, "net_odds": False, "net_form": False}


def for_analysis(*_args, **_kwargs):
    """分析 / 预测比赛 —— 🔴 绝对禁止联网。

    签名接受任意参数（含 ignore_flags）是**刻意的**：
    即便调用方误传 --net 之类的标志，也一律丢弃，保证「不可绕过」。
    这不是冗余——项目历史上多次出现「参数被吞/被误传」导致静默降级
    （case91 slug、case209 漏源），此处用刚性返回阻断同类问题。
    """
    return dict(_ALL_OFF)


def for_review(allow=False, *_args, **_kwargs):
    """复盘 —— 默认离线；`allow=True`（用户明确要求）才联网。

    「明确」的定义：用户在本轮对话中直接说可以联网/去查一下，
    而不是模型的推断。默认为 False，宁可少一次联网。
    """
    return dict(_ALL_ON) if allow else dict(_ALL_OFF)


def for_tooling(*_args, **_kwargs):
    """其他场景（配置、调试、独立工具）—— 允许联网。"""
    return dict(_ALL_ON)


def resolve(mode, allow=False, *args, **kwargs):
    """按模式分派。未知模式 → 按最严格（分析）处理，绝不默认放开。"""
    m = (mode or "").strip().lower()
    if m == "analysis":
        return for_analysis()
    if m == "review":
        return for_review(allow=allow)
    if m == "tooling":
        return for_tooling()
    return dict(_ALL_OFF)   # 未知 → 最严格


def describe(kw):
    """人类可读的通道描述（供日志/审计留痕）。"""
    def s(k):
        return "开" if kw.get(k) else "关"
    return "injury=%s odds=%s form=%s" % (s("net_injury"), s("net_odds"), s("net_form"))


def any_on(kw):
    return any(bool(kw.get(k)) for k in ("net_injury", "net_odds", "net_form"))
