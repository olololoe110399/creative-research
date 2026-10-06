#!/usr/bin/env python3
import argparse, json, re, csv
from pathlib import Path


def clean(v):
    v=str(v or '').strip()
    m=re.search(r'tiktok\.com/@([^/?#]+)',v,re.I)
    if m: v=m.group(1)
    return v.lstrip('@').strip('/')


def read_jsonl(p):
    out=[]
    if not p.exists(): return out
    for line in p.read_text(encoding='utf-8-sig').splitlines():
        if not line.strip(): continue
        try:
            x=json.loads(line)
            if isinstance(x,dict): out.append(x)
        except: pass
    return out


def acc(row):
    for k in ('account','input'):
        if row.get(k): return clean(row[k])
    a=row.get('authorMeta') or row.get('author') or {}
    if isinstance(a,dict):
        for k in ('name','uniqueId','unique_id'):
            if a.get(k): return clean(a[k])
    return ''


def pid(row):
    for k in ('post_id','id','idStr','postId','awemeId','aweme_id'):
        if row.get(k) is not None: return str(row[k])
    for k in ('url','webVideoUrl','postUrl'):
        if row.get(k): return str(row[k])
    return json.dumps(row,sort_keys=True,ensure_ascii=False)


def write_jsonl(p, rows):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('w',encoding='utf-8') as f:
        for r in rows: f.write(json.dumps(r,ensure_ascii=False,default=str)+'\n')


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--sources',nargs='+',required=True)
    ap.add_argument('--accounts',nargs='+',required=True)
    ap.add_argument('--out',default='selected_accounts')
    a=ap.parse_args()

    wanted={clean(x).lower():clean(x) for x in a.accounts}
    raw={u:{} for u in wanted.values()}
    norm={u:{} for u in wanted.values()}

    for s in map(Path,a.sources):
        # normalized
        for r in read_jsonl(s/'normalized'/'posts.jsonl'):
            u=acc(r).lower()
            if u in wanted: norm[wanted[u]][pid(r)]=r
        # per-account raw posts
        pd=s/'posts'
        if pd.exists():
            for p in pd.glob('*.jsonl'):
                for r in read_jsonl(p):
                    u=acc(r).lower()
                    if u in wanted: raw[wanted[u]][pid(r)]=r
        # fallback raw all
        for r in read_jsonl(s/'raw'/'all_items.jsonl'):
            u=acc(r).lower()
            if u in wanted: raw[wanted[u]][pid(r)]=r

    out=Path(a.out)
    alln=[]
    man={}
    for u in wanted.values():
        rr=list(raw[u].values()); nn=list(norm[u].values())
        write_jsonl(out/'posts'/f'{u}.jsonl',rr)
        write_jsonl(out/'normalized'/f'{u}.jsonl',nn)
        alln.extend(nn)
        man[u]={'raw_posts':len(rr),'normalized_posts':len(nn)}
    write_jsonl(out/'normalized'/'posts.jsonl',alln)

    if alln:
        fields=[]; seen=set()
        for r in alln:
            for k in r:
                if k not in seen: seen.add(k); fields.append(k)
        (out/'normalized').mkdir(parents=True,exist_ok=True)
        with (out/'normalized'/'posts.csv').open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore'); w.writeheader()
            for r in alln:
                x={k:(json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v) for k,v in r.items()}
                w.writerow(x)

    (out/'manifest.json').write_text(json.dumps({'sources':a.sources,'accounts':man},ensure_ascii=False,indent=2),encoding='utf-8')
    print('DONE:',out)
    for u,v in man.items(): print(f'@{u}: {v["raw_posts"]} raw | {v["normalized_posts"]} normalized')

if __name__=='__main__': main()
