import csv, re, math
from collections import defaultdict

# --- projections from the pre-tip log
proj=[]; game=team=None
for ln in open('logs/2026-11-06.md'):
    ln=ln.rstrip()
    if ln.startswith('## '): game=ln[3:].split('   ')[0].strip()
    elif ln.startswith('### '): team=ln[4:].split(' (')[0]
    elif ln.startswith('| ') and 'Player' not in ln and '---' not in ln:
        c=[x.strip() for x in ln.strip('|').split('|')]
        proj.append({'game':game,'team':team,'p':c[0],'min':float(c[1]),
                     'PTS':float(c[2]),'REB':float(c[3]),'AST':float(c[4]),'3PM':float(c[5])})

# --- naive baseline: season per-game average, no adjustment at all
base={}
for r in csv.DictReader(open('data/baseline/2026-11-06.csv')):
    def f(k):
        try: return float(r[k])
        except: return 0.0
    base[r['player']]={'PTS':f('PTS'),'REB':f('REB'),'AST':f('AST'),'3PM':f('3PM'),'min':f('MIN')}

# --- actuals
act={}
for r in csv.DictReader(open('data/boxscores/2026-11-06.csv')):
    if str(r.get('dnp','')).lower()=='true': continue
    def i(k):
        v=r.get(k,'')
        try: return float(v)
        except: return None
    tp=r.get('3PT','') or ''
    tpm=float(tp.split('-')[0]) if '-' in tp and tp.split('-')[0].isdigit() else None
    m=i('MIN')
    if m is None: continue
    act[r['player']]={'min':m,'PTS':i('PTS'),'REB':i('REB'),'AST':i('AST'),'3PM':tpm}

cats=['PTS','REB','AST','3PM']
rows=[]; dnp=[]; missing=[]
for p in proj:
    a=act.get(p['p'])
    if a is None:
        (dnp if p['p'] in base else missing).append(p['p']); continue
    b=base.get(p['p'],{})
    rows.append({'game':p['game'],'team':p['team'],'p':p['p'],
                 'pmin':p['min'],'amin':a['min'],
                 **{f'proj_{c}':p[c] for c in cats},
                 **{f'act_{c}':a[c] for c in cats},
                 **{f'base_{c}':b.get(c,0.0) for c in cats}})

print(f"projected {len(proj)} | graded {len(rows)} | did not play {len(dnp)} | name-unmatched {len(missing)}")
if dnp: print("  DNP/scratch:", ", ".join(dnp[:12]))
if missing: print("  unmatched:", ", ".join(missing[:12]))

def stats(key_p,key_a,rs):
    e=[r[key_p]-r[key_a] for r in rs]
    n=len(e)
    mae=sum(abs(x) for x in e)/n
    bias=sum(e)/n
    rmse=(sum(x*x for x in e)/n)**.5
    return mae,bias,rmse,n

print("\n=== MODEL vs NAIVE BASELINE (season avg, unadjusted) ===")
print(f"{'Stat':<6}{'MAE':>7}{'base':>7}{'delta':>8}{'bias':>8}{'RMSE':>7}{'%ofmean':>9}  verdict")
summary={}
for c in cats:
    mae,bias,rmse,n=stats(f'proj_{c}',f'act_{c}',rows)
    bmae,_,_,_=stats(f'base_{c}',f'act_{c}',rows)
    mean=sum(r[f'proj_{c}'] for r in rows)/n
    d=mae-bmae
    # paired test
    diffs=[abs(r[f'proj_{c}']-r[f'act_{c}'])-abs(r[f'base_{c}']-r[f'act_{c}']) for r in rows]
    sd=(sum((x-d)**2 for x in diffs)/(n-1))**.5
    se=sd/math.sqrt(n)
    sig = "sig" if abs(d) > 1.96*se else "n.s."
    verdict=("model better" if d<0 else "baseline better")+f" ({sig})"
    summary[c]=(mae,bmae,d,se)
    print(f"{c:<6}{mae:7.2f}{bmae:7.2f}{d:+8.2f}{bias:+8.2f}{rmse:7.2f}{100*mae/mean:8.0f}%  {verdict}")

print("\n=== MINUTES ===")
mae,bias,rmse,n=stats('pmin','amin',rows)
print(f"MIN   MAE {mae:.2f}  bias {bias:+.2f}  RMSE {rmse:.2f}")

print("\n=== WORST POINTS MISSES ===")
rows.sort(key=lambda r: -abs(r['proj_PTS']-r['act_PTS']))
print(f"{'Player':<26}{'team':<5}{'proj':>6}{'act':>6}{'err':>7}{'pmin':>6}{'amin':>6}")
for r in rows[:12]:
    print(f"{r['p']:<26}{r['team']:<5}{r['proj_PTS']:6.1f}{r['act_PTS']:6.0f}{r['proj_PTS']-r['act_PTS']:+7.1f}{r['pmin']:6.0f}{r['amin']:6.0f}")

import json
json.dump(rows, open('/tmp/graded.json','w'))
