import urllib.request, json

req = urllib.request.Request("http://localhost:8000/api/sessions")
with urllib.request.urlopen(req, timeout=5) as resp:
    data = json.loads(resp.read())
    sessions = data.get("sessions", [])
    for s in sessions[:5]:
        print(f"{s['id'][:8]}... | {s.get('title','?')[:20]} | status={s.get('status','?')} | updated={s.get('updated_at','?')}")
