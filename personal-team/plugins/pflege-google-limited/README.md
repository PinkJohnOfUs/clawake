# Pflege Google Limited

**Ab Version 0.5.0:** Anmeldung über die native Dashboard-Seite **Google-Konto**
im normalen Host-Browser. Die aktuelle Installations- und Google-Anleitung steht in
[SETUP.md](./SETUP.md). Kein zusätzlicher Callback-Port und kein Code im Chat nötig.

Der kanonische Quellcode liegt als Bestandteil von Clawake unter
`personal-team/plugins/pflege-google-limited`. Das Team-Inventar pinnt das Release-
Archiv mit SHA-256; Laufzeitkopien unter `.openclaw/extensions` sind installierter
Zustand und keine Quelle für Änderungen.

## Clawake-Release bauen

Das Build verwendet dieselbe per Digest gepinnte OpenClaw-Container-Version wie der
Pflegebetreuer. Nach einer Versionsänderung zuerst `package.json` und Lockfile prüfen,
Build und Tests in einem kurzlebigen Container ausführen und das Archiv über
`openclaw plugins pack` erzeugen. Das Pack-Kommando überschreibt keine vorhandenen
Dateien; jeder Build bekommt deshalb einen neuen eindeutigen Release-Namen.

Das erzeugte Archiv wird zusammen mit seinem `sha256:`-Wert in
`personal-team/team.yml` eingetragen. Danach prüfen:

```bash
uv run clawake validate -c personal-team/team.yml
uv run clawake setup -c personal-team/team.yml -m pflegebetreuer
uv run clawake sync-plugins -c personal-team/team.yml -m pflegebetreuer
```

Erst die beiden erfolgreichen Vorschauen mit `--execute` anwenden. Der Quellcode,
das npm-Lockfile, das kleine Release-Archiv und der Inventar-Pin gehören gemeinsam
in einen Git-Commit. `node_modules`, `dist`, Clientdateien und Tokens sind ignoriert.

Dieses OpenClaw-Plugin bindet ein Google-Konto für organisatorische Pflegeaufgaben an. Es wurde für ein separates Testkonto entwickelt, behandelt Zugangsdaten und Kontoinhalte aber wie Daten eines sensiblen Nutzerkontos.

Das Plugin verwendet die Google-REST-APIs direkt über die nativen Node.js-APIs `fetch` und `fs`. Zur Laufzeit werden weder `googleapis` noch ein externer OAuth-Vermittler oder ein IMAP-App-Passwort benötigt.

## Funktionsumfang

### Gmail

- Nachrichten suchen und auflisten
- einzelne Nachrichten lesen
- E-Mails als Klartext senden
- Labels ändern, archivieren sowie gelesen/ungelesen oder markiert setzen
- Nachrichten in den Gmail-Papierkorb verschieben

Das Plugin löscht Nachrichten nicht unmittelbar endgültig. Der Gmail-Papierkorb unterliegt den Aufbewahrungsregeln von Google.

### Google Kalender

- Termine auflisten und lesen
- Termine erstellen
- vorhandene Termine ändern

Es gibt bewusst kein Werkzeug zum Löschen von Kalendereinträgen.

### Google Drive

- Dateien und Ordner suchen und auflisten
- Metadaten einzelner Dateien lesen
- Binärdateien herunterladen
- Google Docs, Sheets, Slides und Drawings als PDF, XLSX, PPTX bzw. PNG exportieren

Drive-Zugriff ist technisch auf Lesen begrenzt. Das Plugin kann keine Dateien hochladen, verändern, freigeben oder löschen. Downloads werden standardmäßig unter `~/.openclaw/downloads` abgelegt, sind auf 25 MiB pro Datei begrenzt und überschreiben keine vorhandenen Dateien.

## OAuth-Berechtigungen

Der Zustimmungsdialog fordert exakt diese vier Google-Scopes an:

```text
https://www.googleapis.com/auth/gmail.modify
https://www.googleapis.com/auth/gmail.send
https://www.googleapis.com/auth/calendar.events
https://www.googleapis.com/auth/drive.readonly
```

Beim OAuth-Abschluss vergleicht das Plugin die tatsächlich erteilten Berechtigungen mit dieser Liste. Ein abweichender Umfang wird abgelehnt, bevor ein Token gespeichert wird.

## Verfügbare OpenClaw-Werkzeuge

OAuth:

- `pflege_google_auth_start`
- `pflege_google_auth_complete`

Gmail:

- `pflege_gmail_messages_list`
- `pflege_gmail_message_get`
- `pflege_gmail_message_send`
- `pflege_gmail_message_modify`
- `pflege_gmail_message_trash`

Kalender:

- `pflege_calendar_events_list`
- `pflege_calendar_event_get`
- `pflege_calendar_event_create`
- `pflege_calendar_event_update`

Drive:

- `pflege_drive_files_list`
- `pflege_drive_file_get`
- `pflege_drive_file_download`

E-Mail-Versand, Gmail-Änderungen, Verschieben in den Papierkorb sowie das Erstellen oder Ändern von Terminen sind externe Zustandsänderungen. In der vorgesehenen Pflegebetreuer-Rolle benötigen sie vor jedem konkreten Aufruf eine Freigabe für Inhalt und Ziel. Diese Freigaberegel ist derzeit organisatorisch in Rollen- und Toolbeschreibungen verankert, nicht als zusätzliche technische Bestätigungsschicht im Plugin.

## Ablage von Zugangsdaten

Standardpfade im OpenClaw-Container:

```text
~/.openclaw/secrets/pflege-google-credentials.json
~/.openclaw/secrets/pflege-google-token.json
```

In der aktuellen Containerinstallation entsprechen sie:

```text
/home/node/.openclaw/secrets/pflege-google-credentials.json
/home/node/.openclaw/secrets/pflege-google-token.json
```

Beide Dateien müssen dem OpenClaw-Benutzer gehören und Dateirechte `600` besitzen. Zugangsdaten, Token und Autorisierungscodes dürfen nicht in Chats, Logs, versionierte Workspace-Dateien oder Kommandozeilenargumente kopiert werden.

Das Plugin liest die Dateien erst, wenn ein OAuth- oder Google-API-Werkzeug aufgerufen wird. Build, Tests, Validierung und Verpackung greifen nicht auf diese Dateien zu.

## Historischer Host-Helfer (0.4.0; optionaler manueller Fallback)

Für die integrierte Oberfläche ab 0.5.0 stattdessen [SETUP.md](./SETUP.md) verwenden.

Die OpenClaw-Instanz läuft in dieser Umgebung als Podman-Container. In den Beispielen ist `OPENCLAW_CONTAINER` durch den tatsächlichen Containernamen zu ersetzen.

### 1. Google Cloud vorbereiten

1. Ein separates Google-Cloud-Projekt anlegen.
2. Gmail API, Google Calendar API und Google Drive API aktivieren.
3. Den OAuth-Zustimmungsbildschirm als externe Anwendung konfigurieren.
4. Solange die Anwendung den Status `Testing` hat, das verwendete Google-Konto unter **Audience / Test users** eintragen.
5. Einen OAuth-Client vom Typ **Desktop-App** erstellen und die Client-JSON herunterladen.

### 2. Clientdatei geschützt in den Container kopieren

```bash
podman exec OPENCLAW_CONTAINER mkdir -p /home/node/.openclaw/secrets
podman cp ./pflege-google-credentials.json \
  OPENCLAW_CONTAINER:/home/node/.openclaw/secrets/pflege-google-credentials.json
podman exec OPENCLAW_CONTAINER \
  chmod 600 /home/node/.openclaw/secrets/pflege-google-credentials.json
```

Die lokale Quelldatei darf nicht in ein Git-Repository aufgenommen werden.

### 3. OAuth im normalen Host-Browser durchführen

Google akzeptierte den von OpenClaw verwalteten Build-in-Browser in dieser Umgebung nicht als sicheren Anmeldebrowser. Deshalb wird der OAuth-Rückruf auf dem Host ausgeführt und der normale Browser des Nutzers verwendet.

Der dafür erstellte Helfer liegt in dieser Arbeitskopie unter:

```text
/workspace/gmail-readonly-review/pflege-google-oauth-setup.mjs
```

Helfer und Clientdatei zunächst auf den Host kopieren:

```bash
podman cp OPENCLAW_CONTAINER:/workspace/gmail-readonly-review/pflege-google-oauth-setup.mjs .
podman cp OPENCLAW_CONTAINER:/home/node/.openclaw/secrets/pflege-google-credentials.json .
```

Wenn auf dem Host kein Node.js installiert ist, kann der Helfer in einem kurzlebigen Podman-Container mit Host-Netzwerk laufen:

```bash
podman run --rm --network host \
  -e NO_OPEN=1 \
  -v "$PWD:/work:Z" -w /work \
  docker.io/library/node:24-alpine \
  node ./pflege-google-oauth-setup.mjs ./pflege-google-credentials.json
```

Der Helfer zeigt eine Google-Autorisierungsadresse an. Diese Adresse im normalen Browser öffnen, das vorgesehene Google-Konto auswählen und die vier Berechtigungen prüfen. Der Autorisierungscode wird über `http://localhost:4001` lokal entgegengenommen und nicht im Chat übertragen.

Nach erfolgreicher Zustimmung entsteht im Arbeitsordner:

```text
pflege-google-token.json
```

### 4. Token in den OpenClaw-Container kopieren

```bash
podman cp ./pflege-google-token.json \
  OPENCLAW_CONTAINER:/home/node/.openclaw/secrets/pflege-google-token.json
podman exec OPENCLAW_CONTAINER \
  chmod 600 /home/node/.openclaw/secrets/pflege-google-token.json
```

Anschließend lokale Zwischenkopien des Tokens sicher entfernen. Die Clientdatei nur behalten, wenn sie für eine spätere erneute Autorisierung benötigt wird, und auch dann geschützt ablegen.

### 5. Ungefährliche Funktionsprüfung

Nach der Einrichtung zuerst ausschließlich Lesezugriffe prüfen:

- maximal eine Gmail-Nachrichten-ID auflisten
- Kalenderereignisse in einem kleinen Zeitraum auflisten
- maximal einen Drive-Metadatensatz auflisten
- eine kleine, unkritische Drive-Datei herunterladen und den zurückgegebenen Pfad prüfen

Senden, Verschieben in den Papierkorb sowie Kalender-Erstellen oder -Ändern nicht als Smoke-Test ausführen. Dafür ist ein konkreter, ausdrücklich freigegebener Testvorgang erforderlich.

## Build, Tests und Verpackung

```bash
npm run build
npm test
npm run plugin:check
npm run plugin:validate
```

Ein prüfbares OpenClaw-Artefakt erzeugen:

```bash
openclaw plugins pack \
  --root . \
  --out /absoluter/neuer/pfad/pflege-google-limited.tgz \
  --json
```

Die ausgegebene SHA-256-Prüfsumme vor der Aktivierung kontrollieren. Das Packen installiert das Plugin nicht und startet keinen OAuth-Vorgang.

## Funktionsweise zur Laufzeit

1. Das Plugin liest Clientdatei und Token nur bei Bedarf.
2. Vor Google-API-Aufrufen prüft es, ob das Access-Token bald abläuft.
3. Falls nötig, fordert es mit dem Refresh-Token ein neues Access-Token an und speichert den aktualisierten Token mit Dateirechten `600`.
4. API-Aufrufe gehen direkt an die offiziellen Google-Endpunkte.
5. Bei einer HTTP-401-Antwort wird einmalig aktualisiert und erneut versucht.
6. Fehlerantworten werden als Fehler zurückgegeben; Zugangsdaten werden nicht absichtlich protokolliert.

## Offene Punkte und bekannte Grenzen

- **Integrierter OpenClaw-Browser:** Google kann dessen Anmeldung sperren. Die native Plugin-Seite öffnet die Anmeldung deshalb im normalen Host-Browser.
- **OAuth-Rückruf:** Ab 0.5.0 im Gateway integriert; Einrichtung und Sicherheitsgrenzen siehe SETUP.md.
- **Autorisierungscode:** `pflege_google_auth_complete` lehnt Aufrufe ab. Der Codeaustausch erfolgt ausschließlich im Backend des browsergebundenen OAuth-Ablaufs.
- **Google-Testmodus:** Bleibt die OAuth-Anwendung im Status `Testing`, können Refresh-Tokens abhängig von Googles Richtlinien nach kurzer Zeit, häufig nach sieben Tagen, ungültig werden. Für dauerhaften Betrieb müssen Veröffentlichungsstatus und Google-Anforderungen separat geprüft werden.
- **Freigaben vor Schreibaktionen:** Die Zustimmungspflicht ist derzeit eine Verfahrensregel. Eine zusätzliche technische Bestätigungsschicht pro Schreib- oder Löschaufruf wäre robuster.
- **Drive-Downloads:** Dateien werden lokal unter `downloadDirectory` gespeichert. Google-Workspace-Dateien werden in feste Standardformate exportiert. Pro Datei gilt `maxDownloadBytes` (standardmäßig 25 MiB); vorhandene Dateien werden nicht überschrieben.
- **Container-Netzwerk:** Die native Anmeldung nutzt den vorhandenen Gateway-Port; der alte separate Helfer benötigt weiterhin seine eigene Netzwerk-Konfiguration.
- **Paketmetadaten:** `package.json` enthält noch Namen, Autor und Repository des ursprünglichen Community-Plugins. Vor einer Veröffentlichung oder Weitergabe müssen diese Angaben auf das lokale Projekt angepasst und die Lizenz-/Urheberhinweise sauber erhalten werden.
- **Lokales Artefakt:** Die Installation stammt aus einem lokal geprüften Artefakt und besitzt keine ClawHub-Provenienz. Für Updates müssen Quellcode, Tests und SHA-256 erneut geprüft werden.

## Sicherheitsgrundsätze

- Konto trotz Testzweck wie ein sensibles Nutzerkonto behandeln.
- Nur die dokumentierten Scopes anfordern.
- Passwörter, Client-Secret, Token und Autorisierungscodes niemals im Chat austauschen.
- Keine Zugangsdaten im Workspace oder in Git belassen.
- Schreib-, Sende- und Papierkorbaktionen nur nach konkreter Freigabe ausführen.
- Bei unerwarteten Scopes, Konten oder Empfängern abbrechen.
- OAuth-Zugriff bei Google widerrufen, sobald das Plugin nicht mehr benötigt wird.
