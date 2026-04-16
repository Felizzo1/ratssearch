# RATSSEARCH/DD

Semantische Suche über Dresdner Ratsdokumente — Vorlagen, Anträge, Anfragen, Tagesordnungspunkte von 2009 bis heute.

**Live-URL nach Deployment:** `https://<dein-github-nutzername>.github.io/ratssearch/`

---

## Was ist das?

Eine statische Website, die täglich automatisch aktualisiert wird:

```
offenesdresden/dresden-ratsinfo (GitHub, täglich aktuell)
    ↓  GitHub Actions (täglich 06:00 Uhr)
search-index.json (~2.5 MB komprimiert)
    ↓  GitHub Pages
Browser der Fraktionsmitglieder
```

- **58.000+ durchsuchbare Einträge** — Vorlagen, Anträge, Petitionen, Anfragen, Tagesordnungspunkte
- **Volltextsuche im Browser** — kein Server, kein Login, sofortige Ergebnisse
- **Direkt-Links ins Ratsinfo** bei jedem Treffer
- **Beratungsvorgänge** — welche Gremien haben eine Vorlage wann behandelt?
- **KI-Integration vorbereitet** — mit einem API-Key aktivierbar

---

## Einrichtung (einmalig, ~5 Minuten)

### Schritt 1: Repository anlegen

1. Auf GitHub ein neues Repository erstellen: z.B. `ratssearch`
2. Diesen Projektordner als Inhalt hochladen (oder per Claude Code pushen)

### Schritt 2: GitHub Pages aktivieren

1. Im Repository: **Settings → Pages**
2. Source: **GitHub Actions**
3. Speichern

### Schritt 3: Ersten Build auslösen

1. Im Repository: **Actions → "Suchindex täglich aktualisieren"**
2. **Run workflow** klicken
3. Nach ~3 Minuten ist die Seite live

Die URL lautet dann: `https://<nutzername>.github.io/<repository-name>/`

---

## KI-Integration aktivieren (optional, später)

In `public/index.html` zwei Änderungen vornehmen:

```javascript
// Zeile ~20 in der CONFIG:
AI_ENABLED: true,           // false → true
AI_API_KEY: 'sk-ant-...',   // API-Key eintragen
```

Und im HTML den `disabled`-Attribute vom KI-Toggle entfernen:
```html
<!-- vorher: -->
<input type="checkbox" id="aiToggle" disabled>
<!-- nachher: -->
<input type="checkbox" id="aiToggle">
```

Kosten: ~0,01–0,05 € pro KI-Suchanfrage (Claude Sonnet).

---

## Lokale Entwicklung

```bash
# Repo klonen
git clone https://github.com/offenesdresden/dresden-ratsinfo.git /tmp/dresden-ratsinfo

# Index bauen
python3 build_index.py

# Seite lokal testen (aus dem public/-Ordner)
cd public
python3 -m http.server 8000
# → http://localhost:8000
```

---

## Struktur

```
ratssearch/
├── .github/
│   └── workflows/
│       └── update-index.yml   # Tägliche Aktualisierung
├── public/
│   ├── index.html             # Die Suchoberfläche
│   └── search-index.json      # Generierter Index (wird täglich neu gebaut)
├── build_index.py             # Index-Generator
└── README.md
```

---

## Datenquelle

[offenesdresden/dresden-ratsinfo](https://github.com/offenesdresden/dresden-ratsinfo) —
täglicher Spiegel der offiziellen OParl-Schnittstelle der Landeshauptstadt Dresden (`oparl.dresden.de`).
