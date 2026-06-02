# User Journey: Clawake

## Ausgangslage

Ich nutze Clawake als Stakeholder unseres Produkts. Ich denke in Mitarbeitern: jede OpenClaw-Instanz ist ein eigenstaendiger Mitarbeiter mit einer klaren Rolle.

## Rollenbild

- Nutzer: Ich bediene Clawake ueber CLI und VS Code Launch-Konfigurationen.
- Kunde: Ich bewerte, ob das System fuer reale Produktarbeit taugt.
- Stakeholder: Ich entscheide, welche Mitarbeiter wir erstellen, betreiben und absichern.

## Arbeitsmodell

- Mitarbeiterdefinitionen liegen als staff-Dateien vor.
- Beispiele liegen unter `examples/staff/`.
- Betriebskonfigurationen liegen unter `staff/`.

## Erste Journey-Etappe (README 13-17)

Startpunkt sind die Befehle fuer Validate, Render und Plan.

1. `clawake validate --config|-c <staff.yaml>`
2. `clawake render --config|-c <staff.yaml> [--output|-o <render-dir>]`
3. `clawake plan --config|-c <staff.yaml> [--output|-o <render-dir>]`

Ziel dieser Etappe:
- verstehen, wie schnell ein neuer Mitarbeiter modelliert und geprueft werden kann
- pruefen, ob die Ausgabe fuer Reviews und Freigaben klar genug ist
- Sicherheitsgrenzen frueh sichtbar machen (Mounts, Ports, Mutationen nur mit `--execute`)

## Launch-Konfigurationen fuer Erprobung

Fuer die erste Erprobung nutzen wir in VS Code:

- Clawake: render (developer)
- Clawake: plan (developer)

Konfigurationsbasis:
- `examples/staff/product.yml`

## Beobachtungsprotokoll

### Runde 1: Validate

- Erwartung: Die Mitarbeiter-Datei ist formal valide und kann direkt weiterverarbeitet werden.
- Beobachtung: `OK: examples/staff/product.yml is valid for cluster 'single-host-mvp'`.
- Erkenntnis: Der Validate-Schritt liefert eine klare Freigabe fuer den naechsten Schritt.
- Offene Frage: Wollen wir zusaetzlich Warnungen fuer `0.0.0.0` direkt im Validate-Output sehen?

### Runde 2: Render

- Erwartung: Fuer jeden Mitarbeiter wird eine Quadlet-Datei in `.rendered` erzeugt.
- Beobachtung: `Rendered 2 file(s) into .rendered`.
- Erkenntnis: Die Zuordnung Mitarbeiter -> Render-Artefakt ist fuer Reviews gut nachvollziehbar.
- Offene Frage: Sollen Render-Ausgaben optional nach Rolle gruppiert werden (z. B. Unterordner)?

### Runde 3: Plan

- Erwartung: Plan zeigt Drift oder bestaetigt, dass keine Aenderung auszurollen ist.
- Beobachtung: `No changes for openclaw-product-owner` und `No changes for openclaw-developer`.
- Erkenntnis: Der Dry-Run-Flow ist stabil und zeigt transparent, dass kein Apply notwendig ist.
- Offene Frage: Brauchen wir einen maschinenlesbaren Plan-Modus (`--format json`) fuer Dashboard-Auswertungen?

## Sicherheits-Check je Runde

- Risiko: ungewollte Host-Mutation
- Impact: Instanz-Ausfall oder Konfigurationsdrift
- Mitigation: standardmaessig Dry-Run, `--execute` explizit erforderlich

- Risiko: zu breite Netzwerkfreigabe (z. B. `0.0.0.0`)
- Impact: unerwuenschte Erreichbarkeit von Mitarbeiter-Instanzen
- Mitigation: bind_address bewusst waehlen, fuer interne Rollen `127.0.0.1` bevorzugen

- Risiko: zu breite Schreib-Mounts in den Container
- Impact: Manipulation von Workspace/State auf dem Host
- Mitigation: Mounts auf noetige Pfade begrenzen, read-only wo praktikabel

## Naechster Schritt

Im naechsten Schritt erfassen wir hier echte Lauf-Erfahrungen aus den Launch-Profilen und leiten konkrete Verbesserungen fuer CLI-Ausgaben und Guardrails ab.
