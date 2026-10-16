# -*- coding: utf-8 -*-
"""table_paths.py — 数据表路径统一解析器（唯一真源）
════════════════════════════════════════════════════════════════════════
根因（2026-09-15 修复）:
  各计算脚本用 os.path.join(os.path.dirname(__file__), '<表>.json') 拼路径,
  但 14 张表实际位于 <仓库根>/data/tmp/（scripts/tmp/ 下 0 个 .json）。
  加载失败又被三种写法静默吞掉:
    ① calc_v3572.load()      → return {}           (R1-R18 全空转)
    ② except: _GOAL_BINS={}  → 裸 except 吞异常     (总进球档静默 None)
    ③ if os.path.exists():   → 返回 None 不报错     (半场反推静默失效)
  后果: 规则引擎"跑得通但不判定", 且 calc_match 直接 FileNotFoundError 崩栈。

  历史旁证: check_sync.py 里 8 处 chk() 已把规范路径写成 data/tmp/…,
            但计算脚本从未同步 → 校验器与运行时两套路径长期并存。

判据: 解析结果必须是绝对路径且与工作目录无关; 找不到要能被调用方显式发现。
════════════════════════════════════════════════════════════════════════
"""
import os

# 搜索顺序: 语义最明确 → 兜底。data/tmp 为规范位置。
_SEARCH_DIRS = (
    os.path.join('data', 'tmp'),   # ← 规范位置(14 张表)
    'tables',                      # 历史副本(9 张, 与 data/tmp 内容重复)
    '.',                           # 仓库根
    os.path.join('data',),
    os.path.join('scripts', 'tmp'),  # 兼容: 表被拷到脚本旁的老部署
)

_ROOT_MARKERS = (os.path.join('data', 'tmp'), 'tables', 'scripts')

_cache = {}
_root_cache = []


def find_root(start=None):
    """向上回溯定位仓库根(含 data/tmp 或 tables 的最近祖先)。"""
    if _root_cache:
        return _root_cache[0]
    env = os.environ.get('PITCHQUANT_ROOT')
    cands = []
    if env:
        cands.append(os.path.abspath(env))
    here = os.path.abspath(start or os.path.dirname(os.path.abspath(__file__)))
    cur = here
    while True:
        cands.append(cur)
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    for c in cands:
        if os.path.isdir(os.path.join(c, 'data', 'tmp')):
            _root_cache.append(c)
            return c
    for c in cands:
        if any(os.path.isdir(os.path.join(c, m)) for m in _ROOT_MARKERS):
            _root_cache.append(c)
            return c
    _root_cache.append(here)
    return here


def find_table(name, root=None):
    """返回表的绝对路径; 找不到返回 None(调用方须自行显式处理, 不得静默降级)。

    绝对路径原样返回且要求存在; 相对路径/纯文件名按 _SEARCH_DIRS 依次查找。
    """
    if not name:
        return None
    if os.path.isabs(name):
        return name if os.path.exists(name) else None
    if name in _cache:
        return _cache[name]
    base = root or find_root()
    # ① 相对仓库根按序搜索
    for d in _SEARCH_DIRS:
        p = os.path.abspath(os.path.join(base, d, name))
        if os.path.exists(p):
            _cache[name] = p
            return p
    # ② 传入的可能是 data/tmp/x.json 这类已带目录的相对路径
    p = os.path.abspath(os.path.join(base, name))
    if os.path.exists(p):
        _cache[name] = p
        return p
    _cache[name] = None
    return None


def load_table(name, default=None, root=None):
    """加载表; 缺失返回 default(None 或 {}), 不抛异常。"""
    import json
    p = find_table(name, root=root)
    if not p:
        return default
    try:
        with open(p, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def require_table(name, root=None):
    """加载表; 缺失/损坏显式抛 FileNotFoundError(用于不允许静默降级的场景)。"""
    import json
    p = find_table(name, root=root)
    if not p:
        raise FileNotFoundError(
            '%s 未找到 — 应位于 %s' % (name, os.path.join(find_root(), 'data', 'tmp')))
    with open(p, encoding='utf-8') as f:
        return json.load(f)
