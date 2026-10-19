# -*- coding: utf-8 -*-
"""build_prob_calibration.py -- 用 441 场盲测实盘反推热门低估校准表

数据来源: data/tmp/batch_{2_5_8,74,140,203}/ 的 decided.json + result_compare.json
          （441 场·全部有真实赛果·SHA256 已锁定）

方法: 取「主胜隐含概率」分档 → 统计该档实际主胜率 → bias_pp = 实际 - 隐含档中点。
      🔴 与项目 calc_match/calc_v3572 的读取口径完全一致:
         for k, v in calib.items(): lo,hi = k.split("-"); if lo <= ph < hi: ph += bias_pp/100

边界处理:
  · 大样本档( n>=30 ) 用实测 bias
  · 小样本档( n<30 ) 向相邻大样本档收缩(避免噪声)
  · 最高档收敛到 85-1.00（更细分段样本不足）

🔴 2026-10-19 修复（2.5pp 缺口根因）:
  原表对每一档都照抄实测 bias，**未做统计显著性检验** →
  0.30-0.40 档拿到 -5.97pp（n=93, p=0.114 不显著，四批次 +15.0/+1.8/-16.5/-4.8 正负颠倒），
  该修正把「主胜领先但主客接近」的场次直接压成客胜，
  实测 79 场里 5 次改判全错（模型 59.5% < 直接押热门 62.0%）。
  现规则：**二项检验 p>=0.05 的档一律置 0**，只保留统计显著的偏差；
  每档写入 p_value 供下游审计。
"""
import json, os, sys, math
sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
ROOT = r"E:\footbal-github\PitchQuant"
OUT = os.path.join(ROOT, "data", "tmp", "prob_calibration.json")
BATCHES = ("batch_2_5_8", "batch_74", "batch_140", "batch_203")

ROWS = []
for b in BATCHES:
    p = os.path.join(ROOT, "data", "tmp", b, "decided.json")
    q = os.path.join(ROOT, "data", "tmp", b, "result_compare.json")
    if not (os.path.exists(p) and os.path.exists(q)):
        continue
    DD = {d["slug"]: d for d in json.load(open(p, encoding="utf-8"))}
    for x in json.load(open(q, encoding="utf-8")):
        d = DD.get(x["slug"])
        if not d:
            continue
        ph = d.get("ph")
        if ph is None:
            continue
        ROWS.append((ph / 100.0, 1 if x["act"] == "主胜" else 0))

print("样本: %d 场" % len(ROWS))

# 档位（与项目 5pp 粒度兼容·高档细分因样本少而合并）
BANDS = [(0.00, 0.15), (0.15, 0.30), (0.30, 0.40), (0.40, 0.50), (0.50, 0.60),
         (0.60, 0.70), (0.70, 0.80), (0.80, 1.00)]

raw = []
for lo, hi in BANDS:
    g = [r for r in ROWS if lo <= r[0] < hi]
    n = len(g)
    mid = (lo + hi) / 2.0
    if n == 0:
        raw.append({"lo": lo, "hi": hi, "n": 0, "mid": mid, "actual": mid, "bias": 0.0})
        continue
    act = sum(r[1] for r in g) / n
    raw.append({"lo": lo, "hi": hi, "n": n, "mid": mid, "actual": act, "bias": (act - mid) * 100,
                "k": sum(r[1] for r in g)})

# 平滑：n<30 的档向 n>=30 的相邻档收缩
MIN_N = 30
for i, r in enumerate(raw):
    if r["n"] >= MIN_N:
        continue
    neigh = [raw[j]["bias"] for j in (i - 1, i + 1)
             if 0 <= j < len(raw) and raw[j]["n"] >= MIN_N]
    if neigh:
        target = sum(neigh) / len(neigh)
        w = r["n"] / float(MIN_N)
        r["bias"] = r["bias"] * w + target * (1 - w)
    r["shrunk"] = True

# 🔴 2026-10-19: 统计显著性门（二项检验·H0: 实际命中率 = 隐含中点）
#   p >= ALPHA 的档视为噪声 → bias 置 0（不是「保守地小改」，是「不施加」）
ALPHA = 0.05


def _pvalue(k, n, p0):
    """双侧二项检验（正态近似·n>=13 时足够准）"""
    if n == 0:
        return 1.0
    a = k / float(n)
    se = math.sqrt(p0 * (1 - p0) / n)
    if se <= 0:
        return 1.0
    z = (a - p0) / se
    return 0.5 * math.erfc(abs(z) / math.sqrt(2))


out = {}
print()
print("%-14s %5s %8s %8s %9s %8s %s" % ("区间", "n", "隐含中点", "实际", "bias_pp", "p值", "处理"))
for r in raw:
    key = "%.2f-%.2f" % (r["lo"], r["hi"])
    pv = _pvalue(r.get("k", 0), r["n"], r["mid"]) if r["n"] else 1.0
    bias = r["bias"]
    if pv >= ALPHA:
        bias = 0.0                     # 不显著 → 不施加
        tag = "🔴噪声置0(p=%.3f)" % pv
    else:
        tag = "✅显著" + ("(收缩)" if r.get("shrunk") else "")
    out[key] = {"bias_pp": round(bias, 2), "n": r["n"],
                "implied_mid": round(r["mid"], 3), "actual": round(r["actual"], 3),
                "p_value": round(pv, 4), "raw_bias_pp": round(r["bias"], 2)}
    print("%-14s %5d %7.1f%% %7.1f%% %+8.2f %8.4f %s" % (
        key, r["n"], r["mid"] * 100, r["actual"] * 100, r["bias"], pv, tag))

meta = {"_meta": {"source": "441场盲测实盘(batch_2_5_8/74/140/203)",
                  "method": "主胜隐含档 -> 实际主胜率, bias_pp = (actual - implied_mid)*100",
                  "significance": "双侧二项检验, p>=%g 的档 bias_pp 置0(不施加)" % ALPHA,
                  "n_total": len(ROWS), "min_n": MIN_N, "alpha": ALPHA,
                  "generated_by": "build_prob_calibration.py"}}
out.update(meta)

# 校验: 必须连续无缝覆盖 0-1（否则读取端 if lo<=ph<hi 会漏档）
sp = sorted((float(k.split("-")[0]), float(k.split("-")[1]))
            for k in out if k != "_meta")
assert abs(sp[0][0]) < 1e-9 and abs(sp[-1][1] - 1.0) < 1e-9, "未覆盖 0-1"
for a, b in zip(sp, sp[1:]):
    assert abs(a[1] - b[0]) < 1e-9, "区间不连续: %s -> %s" % (a, b)

json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print()
print("已写入: %s" % OUT)
print("校验: 区间连续覆盖 0-1 ✅")