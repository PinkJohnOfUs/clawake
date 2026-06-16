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
- Der Betrieb erfolgt ueber einen kleinen Satz klarer Lifecycle-Kommandos.

## Erste Journey-Etappe: Lifecycle zuerst

Startpunkt sind die vier zentralen Kommandos aus der Architektur:

0. `make install-dev`
1. `clawake setup-quadlets --config|-c <staff.yaml>` (Preview)
2. `clawake setup-quadlets --config|-c <staff.yaml> --execute` (Mutation)
3. `clawake restart-quadlets --config|-c <staff.yaml>` (Preview)
4. `clawake restart-quadlets --config|-c <staff.yaml> [--member <name>] --execute` (Mutation)
5. `clawake status-quadlets --config|-c <staff.yaml> [--format text|json]`
6. `clawake teardown-quadlets --config|-c <staff.yaml> [--member <name>]` (Preview)
7. `clawake teardown-quadlets --config|-c <staff.yaml> [--member <name>] --execute` (Mutation)

Ziel dieser Etappe:
- verstehen, wie schnell ein Team vollstaendig in Betrieb genommen werden kann
- pruefen, ob Lifecycle-Aktionen ohne Infrastrukturwissen ausfuehrbar sind
- Sicherheitsgrenzen frueh sichtbar machen (Mounts, Ports, gezielte Reichweite)

## Launch-Konfigurationen fuer Erprobung

Fuer die erste Erprobung nutzen wir in VS Code:

- Clawake: setup-quadlets
- Clawake: status-quadlets

Konfigurationsbasis:
- `examples/staff/team.yml`

## Beobachtungsprotokoll

### Runde 1: Setup

- Erwartung: Team-Mitglieder werden als Quadlets bereitgestellt, ohne dass ich systemd-Details kennen muss.
- Beobachtung: Setup zeigt im Dry-Run die geplanten Aenderungen und setzt erst mit `--execute` um.
- Erkenntnis: Das mentale Modell ist klar: Team-Definition rein, laufende Services raus.
- Offene Frage: Sollen Setup-Ausgaben standardmaessig pro Rolle gruppiert werden?

### Runde 2: Restart

- Erwartung: Nach Konfigurations- oder Imagewechseln werden nur relevante Mitglieder neu gestartet.
- Beobachtung: Restart folgt demselben Safety-Muster (Preview vor Mutation).
- Erkenntnis: Gezielte Neustarts reduzieren Risiko und beschleunigen den Betrieb.
- Offene Frage: Brauchen wir einen interaktiven Bestatigungsschritt bei Team-weiten Restarts?

### Runde 3: Status

- Erwartung: Status zeigt Team-Zustand in einer kompakten, stakeholder-tauglichen Sicht.
- Beobachtung: Jede Rolle ist mit Laufzustand und Basis-Checks sichtbar.
- Erkenntnis: Der Health-Ueberblick funktioniert als zentrale Betriebsansicht.
- Offene Frage: Welche Statusdetails brauchen wir zwingend im JSON-Modus?

### Runde 4: Teardown

- Erwartung: Einzelne Mitarbeiter oder ganze Teams lassen sich kontrolliert entfernen.
- Beobachtung: Teardown bleibt im Dry-Run risikofrei und wird erst mit `--execute` wirksam.
- Erkenntnis: Das Entfernen ist ein normaler Lifecycle-Schritt und kein Sonderfall.
- Offene Frage: Sollen wir Team-weiten Teardown immer mit zweiter Bestatigung absichern?

## Sicherheits-Check je Runde

- Risiko: ungewollte Host-Mutation
- Impact: Instanz-Ausfall oder Konfigurationsdrift
- Mitigation: Dry-Run als Default, explizites `--execute`, zusaetzlich gezielte Zielauswahl (`--member`)

- Risiko: zu breite Netzwerkfreigabe (z. B. `0.0.0.0`)
- Impact: unerwuenschte Erreichbarkeit von Mitarbeiter-Instanzen
- Mitigation: bind_address bewusst waehlen, fuer interne Rollen `127.0.0.1` bevorzugen

- Risiko: zu breite Schreib-Mounts in den Container
- Impact: Manipulation von Workspace/State auf dem Host
- Mitigation: Mounts auf noetige Pfade begrenzen, read-only wo praktikabel

## Naechster Schritt

Im naechsten Schritt erfassen wir echte Lauf-Erfahrungen fuer alle vier Lifecycle-Kommandos und leiten daraus konkrete CLI-Verbesserungen fuer Ausgabequalitaet, Selektorlogik und Guardrails ab.


## Nutzung der Mitarbeiter

