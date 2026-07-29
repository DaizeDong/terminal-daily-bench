#!/usr/bin/env python3
"""Aggregate gate-scored eval result JSONs into leaderboard_data.json (the dashboard's data).
Usage: aggregate_leaderboard.py --results DIR[,DIR:scaffold ...] --out leaderboard_data.json"""
import json, glob, collections, sys
def load(d, scaf):
    R=[]
    for f in glob.glob(d+"/*.json"):
        try: j=json.load(open(f))
        except: continue
        m=j.get("model","")
        if not m or "oracle" in m.lower(): continue
        R.append(dict(model=m, task=j.get("task"),
            solved=bool(j.get("solved") or (isinstance(j.get("reward"),(int,float)) and j["reward"]>=0.999)),
            fa=(j.get("false_accept_check") or {}).get("false_accept",0), scaffold=scaf))
    return R
def main(argv):
    dirs=[]; out="leaderboard_data.json"; date="today"
    for a in argv:
        if a.startswith("--results="): dirs=[x.split(":") for x in a.split("=",1)[1].split(",")]
        elif a.startswith("--out="): out=a.split("=",1)[1]
        elif a.startswith("--date="): date=a.split("=",1)[1]
    rows=[]
    for spec in dirs:
        d=spec[0]; scaf=spec[1] if len(spec)>1 else "single_shot"; rows+=load(d,scaf)
    board=collections.defaultdict(lambda: collections.defaultdict(lambda: dict(n=0,solved=0,fa=0)))
    tasks=set()
    for r in rows:
        tasks.add(r["task"]); b=board[r["model"]][r["scaffold"]]; b["n"]+=1; b["solved"]+=int(r["solved"]); b["fa"]+=int(r["fa"])
    lb=[]
    for m,sc in board.items():
        row={"model":m}
        for s,v in sc.items(): row[s]={"n":v["n"],"solved":v["solved"],"rate":round(v["solved"]/v["n"],3),"fa":v["fa"]}
        lb.append(row)
    lb.sort(key=lambda r:-sum(v.get("rate",0) for k,v in r.items() if isinstance(v,dict)))
    json.dump(dict(date=date,n_tasks=len(tasks),n_cells=len(rows),total_fa=sum(r["fa"] for r in rows),
        leaderboard=lb,community=[]), open(out,"w"), indent=1)
    print(f"aggregated {len(rows)} cells, {len(lb)} models, total_FA={sum(r['fa'] for r in rows)} -> {out}")
if __name__=="__main__": main(sys.argv[1:])
