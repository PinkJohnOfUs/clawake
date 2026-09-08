# Persoenliches OpenClaw-Team

Dieses Team besteht aus drei voneinander isolierten OpenClaw-Instanzen:

- **Alltags-Navigator** (`http://127.0.0.1:18789`): Tagesplanung und Priorisierung
- **Reflexions-Coach** (`http://127.0.0.1:18889`): Coaching, Reflexion und Motivation
- **Pflegebetreuer** (`http://127.0.0.1:18989`): Pflegekoordination, Schriftverkehr und Termine

## Sicherheitsmodell

- Alle Ports sind nur an Loopback (`127.0.0.1`) gebunden.
- `setup-quadlets --execute` traegt die daraus abgeleiteten lokalen Dashboard-Origins
  idempotent in OpenClaws `gateway.controlUi.allowedOrigins` ein. Vorhandene Origins und
  bewusst gesetzte Authentifizierungsoptionen bleiben erhalten.
- `setup-quadlets --execute`, `onboard-member --execute` und `upgrade --execute` gleichen
  `agents.defaults.workspace` auf den im Container verwalteten Pfad `/workspace` ab.
  Dadurch faellt OpenClaw nach Neustarts oder Migrationen nicht auf
  `/home/node/.openclaw/workspace` zurueck.
- Jede Instanz besitzt einen eigenen beschreibbaren Arbeitsbereich.
- Rollendefinitionen werden schreibgeschuetzt eingebunden.
- Es werden keine persoenlichen Ordner, SSH-Schluessel oder Host-Sockets gemountet.
- Nachrichten, Buchungen, Zahlungen, Loeschungen und andere externe oder schwer
  rueckgaengig zu machende Aktionen brauchen immer eine ausdrueckliche Freigabe.
- Zugangsdaten gehoeren nur in die ignorierten `env/*.env`-Dateien, nie in Git.

## Inbetriebnahme

Voraussetzungen: rootless Podman, systemd-Userdienste, `uv` und ein verfuegbares
OpenClaw-Image. Im Repository:

Das Team verwendet oeffentlich abrufbare OpenClaw-Images der Version `2026.8.2`,
zusaetzlich fest auf gepruefte Image-Digests gepinnt. Der Alltags-Navigator nutzt
die offizielle `2026.8.2-browser`-Variante mit Chromium und Playwright; die anderen
Mitglieder verwenden das Standardimage. Das private Beispielimage `openclaw-staff`
ist nicht erforderlich.

```bash
# Auf CachyOS/Arch einmalig (auf diesem System fehlen uv und Podman noch):
sudo pacman -S --needed uv podman

export CLAWAKE_PROJECT_ROOT="$PWD"
make install-dev
make doctor
mkdir -p personal-team/env
cp personal-team/env.example personal-team/env/navigator.env
cp personal-team/env.example personal-team/env/coach.env
cp personal-team/env.example personal-team/env/fokus.env
```

In jede Datei einen eigenen, langen `OPENCLAW_GATEWAY_TOKEN` eintragen und die
benoetigten Provider-Zugangsdaten ergaenzen. Anschliessend erst Vorschau, dann
bewusst ausfuehren:

```bash
uv run clawake setup-quadlets -c personal-team/team.yml
uv run clawake setup-quadlets -c personal-team/team.yml --execute
uv run clawake status-quadlets -c personal-team/team.yml
uv run clawake diagnose-dashboard -c personal-team/team.yml
```

## Verwaltete Plugins

Der Quellcode von `pflege-google-limited` liegt versionierbar unter
`personal-team/plugins/pflege-google-limited`. Das Inventar pinnt das gebaute Archiv
mit SHA-256 für den Fokus-Partner. Zusätzlich wird das offizielle WhatsApp-Plugin als
exakte npm-Version mit der vom Registry-Paket gelieferten SHA-512-Integrität verwaltet.
Google-Credentials und Tokens bleiben ausschließlich
im ignorierten Laufzeitverzeichnis `workspaces/fokus/.openclaw/secrets`.

Nach einer Quellcodeänderung das Plugin gemäß seiner README bauen und testen, das neue
Archiv und dessen SHA-256 im Inventar prüfen und anschließend erst Quadlet und Plugin
anwenden:

```bash
uv run clawake setup -c personal-team/team.yml -m fokus-partner
uv run clawake sync-plugins -c personal-team/team.yml -m fokus-partner
uv run clawake setup -c personal-team/team.yml -m fokus-partner --execute
uv run clawake sync-plugins -c personal-team/team.yml -m fokus-partner --execute
```

`setup` bindet lokale, gepinnte Archive schreibgeschützt in den Container.
`sync-plugins` prüft bei Archiven Host und Read-only-Mount vor der Installation. Bei
npm-Plugins akzeptiert es nur eine exakte Version und gleicht nach der Installation
`resolvedSpec` sowie die SHA-512-Integrität mit dem Inventar ab. Danach setzt es die
deklarierte Plugin-Konfiguration ohne Ausgabe ihres Inhalts und startet die Instanz
neu. Das Akzeptieren der Plugin-Fähigkeiten ist damit an den jeweiligen Pin gebunden.

In `plugins[].config` gehören nur nicht geheime Werte oder Verweise auf OpenClaw-
Secrets, niemals Token oder Passwörter. Das Git-Repository sichert Quellcode und
Deployment-Rezept. Die Dateien unter `.openclaw/secrets` benötigen unabhängig davon
eine verschlüsselte, zugriffsgeschützte Sicherung; sie werden bewusst nicht in Git
aufgenommen.

Zum Kennenlernen zuerst nur den Navigator starten:

```bash
uv run clawake setup-quadlets -c personal-team/team.yml -m alltags-navigator --execute
```

Danach OpenClaws eigene interaktive Einrichtung im sandboxierten Container
ausfuehren. Clawake gibt dabei `/workspace` als Agent-Workspace vor, behaelt die
vorbereiteten Markdown-Dateien und verhindert eine konkurrierende
Daemon-Installation im Container:

```bash
uv run clawake onboard-member \
  -c personal-team/team.yml \
  -m alltags-navigator \
  --execute
```

## Empfohlener Rhythmus

1. Morgens dem Navigator Aufgaben, Termine, Energie und verfuegbare Zeit nennen.
2. Mit dem Pflegebetreuer offene Pflegevorgaenge, Termine und Freigaben koordinieren.
3. Abends mit dem Coach kurz auswerten: Was lief gut, was war schwer, was wird angepasst?

Die Datei `workspaces/*/USER.md` kann vor dem ersten Start mit Name,
Arbeitszeiten, Zielen, Einschraenkungen und bevorzugtem Coaching-Stil ergaenzt werden.
Keine Geheimnisse oder Gesundheitsdaten eintragen, die nicht dauerhaft gespeichert
werden sollen.
