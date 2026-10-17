# -*- coding: utf-8 -*-
"""预测日志补全（2026-09-11·用 data_bridge 采集完整源状态写入 prediction_log）
用法: python scripts/online_learning/refresh_predlog.py [--online]
  默认离线（复盘/维护类）；用户明确要求时才加 --online 联网。
"""
import os, sys, io, json, glob
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import data_bridge as DB

# 2026-10-18 联网策略（唯一真源 net_policy）:
#   这是「预测日志补全」工具，属复盘/维护类 -> 默认离线。
#   用户明确要求（--online 或旧 --net）时才联网。
try:
    import net_policy as NP
    _allow = ('--online' in sys.argv) or ('--net' in sys.argv)
    NETKW = NP.for_review(allow=_allow)
except Exception:
    _on = ('--online' in sys.argv) or ('--net' in sys.argv)
    NETKW = {'net_injury': _on, 'net_odds': _on, 'net_form': _on}
d = os.path.join(HERE, 'prediction_log')
for f in sorted(glob.glob(os.path.join(d, '*.json'))):
    try:
        j = json.load(open(f, encoding='utf-8'))
        txt = j.get('txt')
        if not txt or not os.path.exists(txt):
            print('%-14s 跳过（txt 不存在: %s）' % (os.path.basename(f), txt)); continue
        br = DB.collect(txt, j.get('league') or None, net=False, **NETKW)
        j['features'] = br.get('features') or j.get('features')
        j['sources'] = br.get('status', {})
        j['completeness'] = br.get('completeness')
        j['refreshed_at'] = __import__('time').strftime('%Y-%m-%d %H:%M')
        json.dump(j, open(f, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        st = {k: v.get('status') for k, v in (br.get('status') or {}).items()}
        print('%-14s features=%2d | %s | %s' % (os.path.basename(f), len(j['features']), br.get('completeness'), st))
    except Exception as e:
        print('%-14s 失败: %s' % (os.path.basename(f), str(e)[:80]))
