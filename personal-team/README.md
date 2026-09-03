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
- Jede Instanz besitzt einen eigenen beschreibbaren Arbeitsbereich.
- Rollendefinitionen werden schreibgeschuetzt eingebunden.
- Es werden keine persoenlichen Ordner, SSH-Schluessel oder Host-Sockets gemountet.
- Nachrichten, Buchungen, Zahlungen, Loeschungen und andere externe oder schwer
  rueckgaengig zu machende Aktionen brauchen immer eine ausdrueckliche Freigabe.
- Zugangsdaten gehoeren nur in die ignorierten `env/*.env`-Dateien, nie in Git.

## Inbetriebnahme

Voraussetzungen: rootless Podman, systemd-Userdienste, `uv` und ein verfuegbares
OpenClaw-Image. Im Repository:

Das Team verwendet das oeffentlich abrufbare Basisimage
`ghcr.io/openclaw/openclaw:2026.7.1-2`, zusaetzlich fest auf den geprueften
Image-Digest gepinnt. Das private Beispielimage `openclaw-staff` ist nicht
erforderlich.

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
