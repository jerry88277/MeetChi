import os, json, time, uuid, urllib.request, urllib.error, datetime
B="https://meetchi-backend-atro34poxq-as.a.run.app"
UPN="jerry_tai@mail.chimei.com.tw"
def now8(): return (datetime.datetime.utcnow()+datetime.timedelta(hours=8)).strftime("%H:%M:%S (UTC+8)")
def http(m,u,d=None,h=None,t=180):
    r=urllib.request.Request(u,data=d,method=m,headers=h or {})
    try:
        with urllib.request.urlopen(r,timeout=t) as x: return x.status,x.read().decode()
    except urllib.error.HTTPError as e: return e.code,e.read().decode()
def create(title,lang):
    s,t=http("POST",f"{B}/api/v1/meetings",json.dumps({"title":title,"user_upn":UPN,"language":lang,"template_name":"general","duration":0}).encode(),{"Content-Type":"application/json"})
    return json.loads(t)["id"]
def upload(mid,path,ct):
    bnd="----v"+uuid.uuid4().hex; fn=os.path.basename(path)
    body=f'--{bnd}\r\nContent-Disposition: form-data; name="file"; filename="{fn}"\r\nContent-Type: {ct}\r\n\r\n'.encode()+open(path,"rb").read()+f"\r\n--{bnd}--\r\n".encode()
    return http("POST",f"{B}/api/v1/meetings/{mid}/upload",body,{"Content-Type":f"multipart/form-data; boundary={bnd}"})
def enq(mid): return http("POST",f"{B}/api/v1/tasks/enqueue-transcription",json.dumps({"meeting_id":mid,"template_type":"general"}).encode(),{"Content-Type":"application/json"})

tests=[("[VERIFY]silent",  "verify_silent.m4a","audio/mp4","zh"),
       ("[VERIFY]normal",  "verify_normal.wav","audio/wav","zh")]
ids={}
for title,path,ct,lang in tests:
    mid=create(title,lang); upload(mid,path,ct); s,_=enq(mid); ids[mid]=title
    print(f"{title}: {mid} enqueue={s} @ {now8()}")
print("--- polling ---")
deadline=time.time()+420; pending=dict(ids)
while pending and time.time()<deadline:
    time.sleep(15)
    for mid in list(pending):
        s,t=http("GET",f"{B}/api/v1/meetings/{mid}")
        d=json.loads(t); st=d.get("status")
        if st in ("COMPLETED","FAILED","TRANSCRIBED"):
            asd=d.get("audio_stats"); asj=json.loads(asd) if asd else None
            print(f"\n[{pending[mid]}] status={st} @ {now8()}")
            print("  segments:",len(d.get("transcript_segments") or []))
            print("  failure_reason:",d.get("failure_reason"))
            if asj: print(f"  audio_stats: health={asj['health']} peak={asj['peak_dbfs']} mean={asj['mean_dbfs']} dur={asj['duration_sec']} ch={asj['channels']} sr={asj['sample_rate']}")
            else: print("  audio_stats: None")
            pending.pop(mid)
    if pending: print(f"  ...{len(pending)} processing @ {now8()}")
print("\nMEETING IDS:",list(ids.keys()))
