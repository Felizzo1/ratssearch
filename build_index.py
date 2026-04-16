#!/usr/bin/env python3
"""
Baut den Suchindex für RATSSEARCH/DD aus dem offenesdresden/dresden-ratsinfo Repo.

Wird täglich von GitHub Actions aufgerufen.
Output: public/search-index.json

Lokal ausführen (nach manuellem Clone des Repos nach /tmp/dresden-ratsinfo):
  python3 build_index.py
"""

import json, os, gzip, shutil
from datetime import datetime

# Pfade: lokal oder in GitHub Actions
REPO_PATH = os.environ.get('RATSINFO_REPO', '/tmp/dresden-ratsinfo')
if not os.path.isdir(REPO_PATH):
    REPO_PATH = os.path.normpath(
        os.path.join(os.path.dirname(__file__), '..', 'dresden-ratsinfo')
    )

OUT_DIR  = os.path.join(os.path.dirname(__file__), 'public')
OUT_FILE = os.path.join(OUT_DIR, 'search-index.json')
os.makedirs(OUT_DIR, exist_ok=True)

def oparl_id(url):
    return url.rstrip('/').split('/')[-1] if url else None

def ratsinfo_url(obj_type, numeric_id):
    if obj_type == 'paper':
        return f"https://ratsinfo.dresden.de/vo0050.asp?__kvonr={numeric_id}"
    elif obj_type == 'meeting':
        return f"https://ratsinfo.dresden.de/si0057.asp?__ksinr={numeric_id}"
    return None

def load_json(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None

def progress(step, total_steps, label, count=None):
    cnt = f" ({count:,})" if count is not None else ""
    print(f"[{step}/{total_steps}] {label}{cnt}", flush=True)

print(f"\n{'='*50}")
print(f"RATSSEARCH/DD – Index Build")
print(f"Zeitstempel: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"Quelle: {REPO_PATH}")
print(f"{'='*50}\n")

# 1 – Gremien
progress(1, 6, "Lade Gremien ...")
gremien = {}
for f in os.listdir(f'{REPO_PATH}/gremien'):
    d = load_json(f'{REPO_PATH}/gremien/{f}')
    if d:
        gremien[d['id']] = d.get('name', '')
        gremien[oparl_id(d['id'])] = d.get('name', '')
progress(1, 6, "Gremien geladen", len(gremien)//2)

# 2 – Meetings
progress(2, 6, "Lade Sitzungen ...")
meetings = {}
for f in os.listdir(f'{REPO_PATH}/meetings'):
    d = load_json(f'{REPO_PATH}/meetings/{f}')
    if not d: continue
    mid = oparl_id(d['id'])
    orgs = [gremien.get(o, '') for o in d.get('organization', [])]
    meetings[d['id']] = {
        'id':      mid,
        'name':    d.get('name', ''),
        'date':    (d.get('start', '') or '')[:10],
        'gremium': orgs[0] if orgs else '',
        'url':     ratsinfo_url('meeting', mid),
    }
progress(2, 6, "Sitzungen geladen", len(meetings))

# 3 – Consultations
progress(3, 6, "Lade Beratungsvorga\u0308nge ...")
paper_meetings = {}
for f in os.listdir(f'{REPO_PATH}/consultations'):
    d = load_json(f'{REPO_PATH}/consultations/{f}')
    if not d: continue
    paper     = d.get('paper', '')
    meet_url  = d.get('meeting', '')
    role      = d.get('role', '')
    if paper and meet_url and meet_url in meetings:
        m = meetings[meet_url]
        paper_meetings.setdefault(paper, []).append({
            'date':    m['date'],
            'gremium': m['gremium'],
            'role':    role,
            'url':     m['url'],
        })
progress(3, 6, "Beratungsvorga\u0308nge geladen", len(paper_meetings))

# 4 – Vorlagen + Anfragen
progress(4, 6, "Baue Vorlagen-/Antragsindex ...")
records = []

def add_papers(directory):
    count = 0
    path = f'{REPO_PATH}/{directory}'
    if not os.path.isdir(path):
        return 0
    for f in os.listdir(path):
        d = load_json(f'{path}/{f}')
        if not d: continue
        nid       = oparl_id(d['id'])
        paper_url = d['id']
        conns     = sorted(paper_meetings.get(paper_url, []), key=lambda x: x['date'])
        glist     = list(dict.fromkeys(c['gremium'] for c in conns if c['gremium']))
        records.append({
            't':  'p',
            'id': nid,
            'r':  d.get('reference', ''),
            'n':  d.get('name', ''),
            'd':  (d.get('date', '') or '')[:10],
            'pt': d.get('paperType', ''),
            'g':  glist[:3],
            'c':  conns[:5],
            'u':  ratsinfo_url('paper', nid),
        })
        count += 1
    return count

v = add_papers('vorlagen')
a = add_papers('anfragen')
progress(4, 6, "Vorlagen/Antra\u0308ge/Anfragen geladen", v + a)

# 5 – Tagesordnungspunkte
progress(5, 6, "Baue Tagesordnungs-Index ...")
SKIP = {
    'verschiedenes','informationen','bekanntgaben','fragestunde','fragerunde',
    'nichtoeffentlich','oeffentlich','nichtöffentlich','öffentlich',
    'pause','niederschrift','eroeffnung','schluss','sonstiges',
    'anfragen','beschluesse','beschlüsse',
}
ai_count = 0
for f in os.listdir(f'{REPO_PATH}/agendaitems'):
    d = load_json(f'{REPO_PATH}/agendaitems/{f}')
    if not d: continue
    name = (d.get('name', '') or '').strip()
    if len(name) < 10: continue
    if any(s in name.lower() for s in SKIP): continue
    mid_url = d.get('meeting', '')
    m = meetings.get(mid_url, {})
    records.append({
        't':  'a',
        'id': oparl_id(d['id']),
        'n':  name,
        'd':  m.get('date', ''),
        'g':  [m.get('gremium', '')] if m.get('gremium') else [],
        'u':  m.get('url', ''),
        'sn': m.get('name', ''),
    })
    ai_count += 1
progress(5, 6, "Tagesordnungspunkte geladen", ai_count)

# 6 – Schreiben
progress(6, 6, f"Schreibe Index ({len(records):,} Eintra\u0308ge) ...")
with open(OUT_FILE, 'w', encoding='utf-8') as fh:
    json.dump(records, fh, ensure_ascii=False, separators=(',', ':'))

with open(OUT_FILE, 'rb') as f_in:
    with gzip.open(OUT_FILE + '.gz', 'wb') as f_out:
        shutil.copyfileobj(f_in, f_out)

sz    = os.path.getsize(OUT_FILE) / 1024**2
sz_gz = os.path.getsize(OUT_FILE + '.gz') / 1024**2

print(f"\n{'='*50}")
print(f"Fertig!")
print(f"  Eintra\u0308ge:      {len(records):,}")
print(f"  Unkomprimiert: {sz:.1f} MB")
print(f"  Komprimiert:   {sz_gz:.1f} MB")
print(f"  Output:        {OUT_FILE}")
print(f"{'='*50}\n")
