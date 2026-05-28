#!/usr/bin/env python3
"""
Baut den Suchindex für RATSSEARCH/DD aus dem offenesdresden/dresden-ratsinfo Repo.

Wird täglich von GitHub Actions aufgerufen.
Output: public/search-index.json

Lokal ausführen (nach manuellem Clone des Repos nach /tmp/dresden-ratsinfo):
  python3 build_index.py
"""

import json, os, gzip, shutil, re, time
from datetime import datetime
from urllib.request import urlopen, Request

# Pfade: lokal oder in GitHub Actions
REPO_PATH = os.environ.get('RATSINFO_REPO', '/tmp/dresden-ratsinfo')
if not os.path.isdir(REPO_PATH):
    REPO_PATH = os.path.normpath(
        os.path.join(os.path.dirname(__file__), '..', 'dresden-ratsinfo')
    )

OUT_DIR  = os.path.join(os.path.dirname(__file__), 'public')
OUT_FILE = os.path.join(OUT_DIR, 'search-index.json')
os.makedirs(OUT_DIR, exist_ok=True)

TOTAL_STEPS = 7

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

def progress(step, label, count=None):
    cnt = f" ({count:,})" if count is not None else ""
    print(f"[{step}/{TOTAL_STEPS}] {label}{cnt}", flush=True)

def normalize_role(role):
    return ' '.join((role or '').split())

def _find_table_value(html, *labels):
    """Sucht Tabellenfeld-Wert nach einem Label-Pattern im HTML."""
    for label in labels:
        m = re.search(
            rf'(?i){re.escape(label)}\s*:?\s*</td>\s*<td[^>]*>(.*?)</td>',
            html, re.DOTALL
        )
        if m:
            val = re.sub(r'<[^>]+>', ' ', m.group(1))
            val = re.sub(r'\s+', ' ', val).strip()
            if val:
                return val
    return ''

def fetch_bi_page(kvonr, timeout=10):
    """
    Holt Aktenzeichen + Betreff von der Bürgerinfo-Seite für eine verwaiste Vorlage.
    Gibt ('', '') zurück wenn die Seite nicht erreichbar ist, damit der Build nicht bricht.
    """
    url = f"https://ratsinfo.dresden.de/vo0050.asp?__kvonr={kvonr}"
    try:
        req = Request(url, headers={'User-Agent': 'ratssearch-indexer/1.0 (orphan-fallback)'})
        with urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode('latin-1', errors='replace')
        ref  = _find_table_value(html, 'Vorlagennummer', 'Aktenzeichen')
        name = _find_table_value(html, 'Betreff')
        return ref, name
    except Exception as e:
        print(f"    BI-Seite {kvonr} nicht erreichbar: {type(e).__name__}", flush=True)
        return '', ''

print(f"\n{'='*50}")
print(f"RATSSEARCH/DD – Index Build")
print(f"Zeitstempel: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"Quelle: {REPO_PATH}")
print(f"{'='*50}\n")

# 1 – Gremien
progress(1, "Lade Gremien ...")
gremien = {}
for f in os.listdir(f'{REPO_PATH}/gremien'):
    d = load_json(f'{REPO_PATH}/gremien/{f}')
    if d:
        gremien[d['id']] = d.get('name', '')
        gremien[oparl_id(d['id'])] = d.get('name', '')
progress(1, "Gremien geladen", len(gremien)//2)

# 2 – Meetings
progress(2, "Lade Sitzungen ...")
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
progress(2, "Sitzungen geladen", len(meetings))

# 3 – Consultations
progress(3, "Lade Beratungsvorgänge ...")
paper_meetings = {}   # paper URL → [{date, gremium, role, url}]  nur mit Meeting
paper_consults = {}   # paper URL → [{gremium, role, created}]    alle (Orphan-Fallback)

for f in os.listdir(f'{REPO_PATH}/consultations'):
    d = load_json(f'{REPO_PATH}/consultations/{f}')
    if not d:
        continue
    paper    = d.get('paper', '')
    meet_url = d.get('meeting', '')
    role     = normalize_role(d.get('role', ''))
    created  = (d.get('created', '') or '')[:10]
    orgs     = d.get('organization', [])
    if not paper:
        continue

    gremium_names = [gremien.get(o, '') for o in orgs]
    gremium = next((g for g in gremium_names if g), '')

    # Alle Consultations für Orphan-Fallback erfassen (auch ohne Meeting)
    paper_consults.setdefault(paper, []).append({
        'gremium': gremium,
        'role':    role,
        'created': created,
    })

    if meet_url and meet_url in meetings:
        m = meetings[meet_url]
        paper_meetings.setdefault(paper, []).append({
            'date':    m['date'],
            'gremium': m['gremium'],
            'role':    role,
            'url':     m['url'],
        })

progress(3, "Beratungsvorgänge geladen", len(paper_meetings))

# 4 – Vorlagen + Anfragen
progress(4, "Baue Vorlagen-/Antragsindex ...")
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
progress(4, "Vorlagen/Anträge/Anfragen geladen", v + a)

# 5 – Orphan-Fallback: Vorlagen, deren Paper-Objekt im OParl-Export fehlt (HTTP 404),
#     aber über Consultations/Files referenziert werden.
progress(5, "Suche verwaiste Vorlagen ...")
produced_ids = {r['id'] for r in records if r['t'] == 'p'}
orphan_count = 0
need_delay   = False

for paper_url, consults in paper_consults.items():
    pid = oparl_id(paper_url)
    if pid in produced_ids:
        continue

    dates    = sorted(c['created'] for c in consults if c.get('created'))
    earliest = dates[0] if dates else ''
    glist    = list(dict.fromkeys(c['gremium'] for c in consults if c.get('gremium')))
    conns    = [{'date': c['created'], 'gremium': c['gremium'], 'role': c['role']}
                for c in sorted(consults, key=lambda x: x['created'])
                if c.get('gremium')]

    # BI-Seite abrufen um Aktenzeichen + Betreff zu holen (höfliches Rate-Limit)
    if need_delay:
        time.sleep(0.7)
    ref, name = fetch_bi_page(pid)
    need_delay = True

    records.append({
        't':  'p',
        'id': pid,
        'r':  ref,
        'n':  name,
        'd':  earliest,
        'pt': 'Vorlage (nur Beratungsdaten)',
        'g':  glist[:3],
        'c':  conns[:5],
        'u':  ratsinfo_url('paper', pid),
        'x':  1,
    })
    produced_ids.add(pid)
    orphan_count += 1

progress(5, "Verwaiste Vorlagen ergänzt", orphan_count)

# 6 – Sitzungen (komplette Tagesordnungen)
progress(6, "Baue Sitzungsindex ...")
sit_count = 0
for url, m in meetings.items():
    if not m.get('date') or not m.get('name'):
        continue
    records.append({
        't': 'm',
        'id': m['id'],
        'n':  m['name'],
        'd':  m['date'],
        'g':  [m['gremium']] if m.get('gremium') else [],
        'u':  m['url'],
    })
    sit_count += 1
progress(6, "Sitzungen geladen", sit_count)

# 7 – Schreiben
progress(7, f"Schreibe Index ({len(records):,} Einträge) ...")
with open(OUT_FILE, 'w', encoding='utf-8') as fh:
    json.dump(records, fh, ensure_ascii=False, separators=(',', ':'))

with open(OUT_FILE, 'rb') as f_in:
    with gzip.open(OUT_FILE + '.gz', 'wb') as f_out:
        shutil.copyfileobj(f_in, f_out)

sz    = os.path.getsize(OUT_FILE) / 1024**2
sz_gz = os.path.getsize(OUT_FILE + '.gz') / 1024**2

print(f"\n{'='*50}")
print(f"Fertig!")
print(f"  Einträge:      {len(records):,}")
print(f"  Unkomprimiert: {sz:.1f} MB")
print(f"  Komprimiert:   {sz_gz:.1f} MB")
print(f"  Output:        {OUT_FILE}")
print(f"{'='*50}\n")
