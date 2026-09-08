# Version 0.5.0: Google im Dashboard verbinden

Geprüfte Zielruntime: OpenClaw 2026.9.2, Container `fokus-partner`.
Die neue native Seite heißt **Google-Konto**. Google öffnet in einem normalen
Firefox-Tab; der OpenClaw-Container-Browser ist dafür nicht beteiligt.

## 1. Google-Webclient vorbereiten

Im vorhandenen Google-Cloud-Projekt einen OAuth-Client vom Typ **Webanwendung**
anlegen. Die aktivierten APIs, Testnutzer und vier Scopes aus der README beibehalten.
Als autorisierte Weiterleitungs-URI exakt registrieren:

```text
http://127.0.0.1:18989/integrations/google/callback
```

Die Client-JSON herunterladen. Kein Client-Secret im Dashboard oder Chat eingeben.
Die Datei geschützt außerhalb des Workspace aufbewahren.

Vom **Host-Terminal** kopieren; den Downloadpfad anpassen:

```bash
podman cp /absoluter/pfad/zum/google-webclient.json fokus-partner:/home/node/.openclaw/secrets/pflege-google-web-credentials.json
podman exec fokus-partner chmod 600 /home/node/.openclaw/secrets/pflege-google-web-credentials.json
```

Die neuen Dateinamen sind absichtlich getrennt: Ein Refresh-Token des alten
Desktop-Clients darf nicht mit den Zugangsdaten des neuen Webclients kombiniert
werden. Die bisherigen Credential- und Token-Dateien bleiben für einen Rollback erhalten.

## 2. Plugin aktualisieren und konfigurieren

Quellcode und geprüftes Artefakt werden durch Clawake unter
`personal-team/plugins/pflege-google-limited` verwaltet. Der SHA-256-Digest steht
im Team-Inventar. Vor dem erstmaligen Clawake-Sync kann die installierte Version
zusätzlich auf dem Host gesichert werden:

```bash
podman cp fokus-partner:/home/node/.openclaw/extensions/pflege-google-limited ./pflege-google-limited-backup-0.4.0
uv run clawake setup -c personal-team/team.yml -m fokus-partner
uv run clawake sync-plugins -c personal-team/team.yml -m fokus-partner
uv run clawake setup -c personal-team/team.yml -m fokus-partner --execute
uv run clawake sync-plugins -c personal-team/team.yml -m fokus-partner --execute
```

Ein bereits vorhandenes Sicherungsverzeichnis nicht überschreiben; einen neuen Namen
wählen. Clawake prüft das Archiv gegen den gepinnten SHA-256-Digest, bevor der
OpenClaw-Installer das benannte Plugin ersetzt.
Falls der Installer eine konkrete Policy-Sperre meldet, diese prüfen und nicht mit
unsicheren Optionen umgehen. Native Plugin-UI ist experimentell und läuft mit den
Rechten des angemeldeten Dashboard-Nutzers; die Labs-Option gilt auch für andere
aktivierte benutzerdefinierte Plugins mit nativer UI.

## 3. In Firefox anmelden

1. `http://127.0.0.1:18989` öffnen und als OpenClaw-Administrator verbinden.
2. Nach dem Neustart die Seite vollständig neu laden.
3. **Google-Konto** in der Seitennavigation öffnen. Falls ausgeblendet, über die
   Anpassung der Seitennavigation hinzufügen; gegebenenfalls Plugin-UI-Fehler prüfen.
4. **Google-Konto verbinden** anklicken. Pop-ups für diese lokale Adresse erlauben.
5. In Google das richtige Konto und die vier Berechtigungen prüfen und zustimmen.
6. Nach der Erfolgsmeldung den Google-Tab schließen; **Status aktualisieren** anklicken.

Der Status „Token gespeichert“ bestätigt nur die lokale Ablage, nicht einen aktuellen
API-Zugriff. Anschließend bei Bedarf einen ausdrücklich gewünschten minimalen
Gmail-Lesezugriff ausführen. Keine Schreibaktion als Anmeldetest verwenden.

Keine zusätzliche Portfreigabe ist notwendig. Weiterhin genügt:

```ini
PublishPort=127.0.0.1:18989:18789/tcp
```

Der HTTP-Empfänger wird durch das Plugin im vorhandenen Gateway registriert.
`localhost` und `127.0.0.1` sind verschiedene Origins: Für diese Konfiguration
konsequent `127.0.0.1` verwenden. Keine Origin-Wildcards oder Abschaltung der
Gateway-/Geräteauthentisierung nötig.

## Sicherheit und spätere VPN-Nutzung

- Start und Status laufen über authentisierte Gateway-RPCs mit `operator.admin`.
- Der öffentliche POST-Einstieg akzeptiert ausschließlich ein über diesen RPC
  ausgestelltes Einmal-Ticket und die konfigurierte Browser-Origin. Das Ticket
  wird im POST-Body übertragen, nicht in einer URL.
- Der Callback verlangt zufälligen `state` und ein passendes HttpOnly-Cookie
  (`SameSite=Lax`, zusätzlich `Secure` bei HTTPS). PKCE bindet den Codeaustausch.
- Transaktionen sind maximal zehn Minuten gültig, auf 32 begrenzt und nach
  Verwendung oder Neustart ungültig. Gleichzeitige Anmeldungen im selben Browser
  können das Cookie ersetzen; deshalb einen Vorgang nach dem anderen abschließen.
- Google-Fehler und falsche Scopes speichern kein neues Token. Callback-Antworten
  enthalten keine Codes oder Tokens und tragen `Cache-Control: no-store` sowie
  `Referrer-Policy: no-referrer`. Ein zukünftiger Proxy muss Callback-Querystrings,
  POST-Bodies und Cookies von Logs ausnehmen: Google liefert den Code in der URL.
- Der alte Agenten-Aufruf `pflege_google_auth_complete` ist deaktiviert. Keine
  Autorisierungscodes in Chat oder Toolparameter kopieren.
- Tokens sind mit `600` gespeichert. Das schützt nicht vor anderem Plugin-Code
  mit denselben Prozessrechten. Die organisatorischen Freigaberegeln der bestehenden
  Google-Schreibwerkzeuge wurden in dieser Änderung nicht erweitert.

Für späteren VPN-/HTTPS-Zugang `publicOrigin`, OpenClaws `allowedOrigins` und die
bei Google sowie in der Clientdatei hinterlegte Rückrufadresse gemeinsam ändern.
`publicOrigin` enthält ausschließlich Schema, Host und optional Port, keinen Pfad.
HTTP wird nur auf Loopback akzeptiert, sonst ist HTTPS erforderlich. Proxy-Zugriff,
MFA, WebSocket-Schutz und Gateway-Authentisierung bleiben separate Betriebsaufgaben.

## Validierung und Rückkehr zur alten Version

Die automatisierten Tests verwenden ausschließlich Testdateien und simulierte
Google-Antworten. Ein echter Google-Login erfordert die neue Clientdatei und die
Zustimmung des Kontoinhabers. Der Browser-Smoke-Test prüft die Seite und den
kompletten Redirect-/Cookie-Ablauf gegen eine simulierte Dashboard-Anbindung.
Er ersetzt keine Prüfung der nativen Seite in deinem angemeldeten Firefox.

Zur Rückkehr die gesicherte Plugin-Version installieren, die alten
`credentialsPath`-/`tokenPath`-Werte konfigurieren, `publicOrigin` aus der
Plugin-Konfiguration entfernen und den Container neu starten. Die neuen
Google-Zugriffsrechte gegebenenfalls im Google-Konto widerrufen; ein Löschen
lokaler Dateien allein widerruft sie nicht.
