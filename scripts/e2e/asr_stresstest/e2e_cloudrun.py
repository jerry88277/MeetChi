#!/usr/bin/env python3
"""End-to-end ASR stress test against the LIVE Cloud Run production stack.
Flow per file: create meeting -> upload -> enqueue-transcription -> poll -> export txt.
Uses REAL production Breeze-ASR-25 + production Silero VAD."""
import os, sys, time, json, io, difflib, datetime, urllib.request, urllib.error, mimetypes, uuid

BACKEND = "https://meetchi-backend-atro34poxq-as.a.run.app"
UPN = "jerry_tai@mail.chimei.com.tw"
ART = os.path.expanduser("~/asr_stresstest/artifacts")

# tag -> (language, reference transcription)
REF = {
    "ZH":  ("zh", "对然后但是呢就是说确实有一个手机呢带来很多方便"),
    "EN":  ("en", "with without with without anybody against"),
    "MIX": ("zh", "如果你customer在知道这个会有五percent的accident"),
}
CONDITIONS = [
    ("1_original",             "原始"),
    ("2_quiet-40dB",           "低音量-40dB"),
    ("3_quiet-40dB_normalized","低音量-40dB+正規化"),
    ("4_noise_SNR0dB",         "加噪SNR0dB"),
]

def now8():
    return (datetime.datetime.utcnow()+datetime.timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S (UTC+8)")

def http(method, url, data=None, headers=None, timeout=120):
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return -1, str(e)

def create_meeting(title, lang):
    body = json.dumps({"title": title, "user_upn": UPN, "language": lang,
                       "template_name": "general", "duration": 0}).encode()
    st, txt = http("POST", f"{BACKEND}/api/v1/meetings", body,
                   {"Content-Type": "application/json"})
    if st not in (200,201):
        return None, f"create failed {st}: {txt[:200]}"
    return json.loads(txt)["id"], None

def upload(mid, path):
    boundary = "----meetchi" + uuid.uuid4().hex
    fn = os.path.basename(path)
    with open(path,"rb") as f: content = f.read()
    body = b""
    body += f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{fn}"\r\nContent-Type: audio/wav\r\n\r\n'.encode()
    body += content + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    st, txt = http("POST", f"{BACKEND}/api/v1/meetings/{mid}/upload", body,
                   {"Content-Type": f"multipart/form-data; boundary={boundary}"}, timeout=180)
    return st in (200,201), f"{st}:{txt[:150]}"

def enqueue(mid):
    body = json.dumps({"meeting_id": mid, "template_type":"general"}).encode()
    st, txt = http("POST", f"{BACKEND}/api/v1/tasks/enqueue-transcription", body,
                   {"Content-Type":"application/json"})
    return st, txt[:200]

def get_status(mid):
    st, txt = http("GET", f"{BACKEND}/api/v1/meetings/{mid}")
    if st!=200: return None, None
    d = json.loads(txt)
    return d.get("status"), d.get("processing_stage")

def get_txt(mid):
    st, txt = http("GET", f"{BACKEND}/api/v1/meetings/{mid}")
    if st!=200: return None
    d = json.loads(txt)
    segs = d.get("transcript_segments") or []
    if segs:
        return " ".join((s.get("content_raw") or "").strip() for s in segs).strip()
    tr = d.get("transcript_raw")
    return tr.strip() if tr else ""

def norm(s):
    return "".join(ch for ch in (s or "") if not ch.isspace()).lower()

def cer(ref, hyp):
    r, h = norm(ref), norm(hyp)
    if not r: return 1.0
    m = difflib.SequenceMatcher(None, r, h)
    same = sum(b.size for b in m.get_matching_blocks())
    return max(0.0, (len(r)-same)/len(r))

def main():
    only = sys.argv[1:] if len(sys.argv)>1 else None  # e.g. ZH_1_original
    jobs = []
    for tag,(lang,ref) in REF.items():
        for cond,label in CONDITIONS:
            name = f"{tag}_{cond}"
            if only and name not in only: continue
            path = os.path.join(ART, name+".wav")
            if not os.path.exists(path): 
                print(f"[skip] missing {path}"); continue
            jobs.append((name, tag, lang, ref, label, path))

    print(f"=== E2E Cloud Run ASR stress test @ {now8()} ===")
    print(f"Backend: {BACKEND}\nModel: production Breeze-ASR-25 + Silero VAD\nJobs: {len(jobs)}\n")

    results = []
    # Phase 1: create + upload + enqueue all
    for name,tag,lang,ref,label,path in jobs:
        mid, err = create_meeting(f"[STRESS]{name}", lang)
        if err: print(f"[{name}] {err}"); results.append((name,label,ref,None,"CREATE_FAIL",None)); continue
        ok,info = upload(mid, path)
        if not ok: print(f"[{name}] upload fail {info}"); results.append((name,label,ref,mid,"UPLOAD_FAIL",None)); continue
        st,info = enqueue(mid)
        print(f"[{name}] meeting={mid} enqueue={st} {info[:80]}")
        results.append((name,label,ref,mid,"ENQUEUED",None))
        time.sleep(1)

    # Phase 2: poll
    print(f"\n--- polling (up to ~15 min) @ {now8()} ---")
    pending = {r[3]:i for i,r in enumerate(results) if r[4]=="ENQUEUED"}
    deadline = time.time()+900
    while pending and time.time()<deadline:
        time.sleep(15)
        done_now=[]
        for mid,idx in list(pending.items()):
            status,stage = get_status(mid)
            if status in ("COMPLETED","TRANSCRIBED","FAILED"):
                name,label,ref = results[idx][0],results[idx][1],results[idx][2]
                hyp = get_txt(mid) if status!="FAILED" else None
                results[idx] = (name,label,ref,mid,status,hyp)
                print(f"  [{name}] {status} @ {now8()}")
                done_now.append(mid)
        for m in done_now: pending.pop(m,None)
        if pending: print(f"  ...{len(pending)} still processing @ {now8()}")

    # Report
    print(f"\n=== RESULTS @ {now8()} ===")
    print(f"{'sample':<28}{'condition':<22}{'status':<12}{'CER':<8}hypothesis")
    for name,label,ref,mid,status,hyp in results:
        if hyp:
            hyp_clean = hyp.strip().replace("\n"," ")[:60]
            c = f"{cer(ref,hyp):.2f}"
        else:
            hyp_clean = "(empty / no segments)"; c="-"
        print(f"{name:<28}{label:<22}{status:<12}{c:<8}{hyp_clean}")

    out = os.path.expanduser("~/asr_stresstest/e2e_results.json")
    with open(out,"w") as f:
        json.dump([{"name":n,"label":l,"ref":r,"meeting_id":m,"status":s,"hyp":h,
                    "cer":(cer(r,h) if h else None)} for n,l,r,m,s,h in results],
                  f, ensure_ascii=False, indent=2)
    print(f"\nSaved -> {out}")

if __name__=="__main__":
    main()
