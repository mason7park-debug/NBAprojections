"""Compare two replays: python scripts/compare_replay.py /tmp/rp/off /tmp/rp/on (each a copy of the repo after a replay)."""
import pandas as pd,glob,numpy as np,sys
def load(v):
    d=pd.concat([pd.read_csv(f) for f in glob.glob(f'{v}/data/graded/*.csv')]); return d[d.played==True]
def metrics(d):
    out={}
    for s,h in d.groupby('stat'):
        L=h.dropna(subset=['line','p_over']); L=L[L.actual!=L.line]
        w=np.where(L.p_over>0.5,L.actual>L.line,L.actual<L.line)
        out[s]=dict(n=len(h),bias=(h.actual-h.expected).mean(),mae=(h.actual-h.expected).abs().mean(),
          naive=(h.actual-h.season_avg).abs().mean(),floor=(h.actual>=h.floor).mean(),
          bfloor=(h[h.final_margin>=20].actual>=h[h.final_margin>=20].blowout_floor).mean(),
          minbias=(h.actual_minutes-h.minutes).mean(),minmae=(h.actual_minutes-h.minutes).abs().mean(),
          vsline=w.mean() if len(L) else np.nan)
    return pd.DataFrame(out).T
for label,cond in [('LIVE 11/12-11/17',lambda d:d.date>='2026-11-12'),('EARLIER 10/30-11/11',lambda d:d.date<'2026-11-12')]:
    print('==',label)
    a,b=load(sys.argv[1]),load(sys.argv[2]); a,b=a[cond(a)],b[cond(b)]
    ma,mb=metrics(a),metrics(b)
    for c in ['bias','mae','floor','bfloor','minbias','minmae','vsline']:
        print(f'{c:8s}', '  '.join(f"{s}: {ma.loc[s,c]:.3f} -> {mb.loc[s,c]:.3f}" for s in ['PTS','REB','AST','3PM']))
    # groups for PTS
    for g,f in [('stars',lambda x:x.star==True),('starters',lambda x:(x.role=='starter')&(x.star!=True)),('bench',lambda x:x.role=='bench')]:
        x,y=a[(a.stat=='PTS')&f(a)],b[(b.stat=='PTS')&f(b)]
        print(f'  PTS {g}: bias {(x.actual-x.expected).mean():.2f}->{(y.actual-y.expected).mean():.2f} mae {(x.actual-x.expected).abs().mean():.2f}->{(y.actual-y.expected).abs().mean():.2f} floor {(x.actual>=x.floor).mean():.3f}->{(y.actual>=y.floor).mean():.3f}')
