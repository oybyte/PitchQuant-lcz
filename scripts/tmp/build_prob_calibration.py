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
    raw.append({"lo": lo, "hi": hi, "n": n, "mid": mid, "actual": act, "bias": (act - mid) * 100})

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

out = {}
print()
print("%-14s %5s %8s %8s %9s %s" % ("区间", "n", "隐含中点", "实际", "bias_pp", "处理"))
for r in raw:
    key = "%.2f-%.2f" % (r["lo"], r["hi"])
    out[key] = {"bias_pp": round(r["bias"], 2), "n": r["n"],
                "implied_mid": round(r["mid"], 3), "actual": round(r["actual"], 3)}
    print("%-14s %5d %7.1f%% %7.1f%% %+8.2f %s" % (
        key, r["n"], r["mid"] * 100, r["actual"] * 100, r["bias"],
        "收缩(样本<%d)" % MIN_N if r.get("shrunk") else "实测"))

meta = {"_meta": {"source": "441场盲测实盘(batch_2_5_8/74/140/203)",
                  "method": "主胜隐含档 -> 实际主胜率, bias_pp = (actual - implied_mid)*100",
                  "n_total": len(ROWS), "min_n": MIN_N,
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