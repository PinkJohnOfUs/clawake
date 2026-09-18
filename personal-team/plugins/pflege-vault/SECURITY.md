# Sicherheitsmodell

## Schutzgüter

- Klartextwerte, Aliase und Beziehungsinformationen
- aktiver und vorherige AES-Schlüssel
- Integrität und Verfügbarkeit der Ciphertext-Datei
- Zweckbindung auf den Pflegebetreuer-Agenten

## Vertrauensgrenzen

Vertraut werden der OpenClaw-Gateway-Prozess, Node-Core-Kryptografie, der OpenClaw Secret
Store/SecretRef-Materialisierungspfad, der lokale Betreiber und das zugrunde liegende
persistent gemountete Dateisystem. Das Plugin schützt nicht vor einem kompromittierten
Gateway-Prozess, Root/Host-Administrator, bösartigem nativen Plugin oder Speicherabbild.

SecretRefs sind laut OpenClaw-Dokumentation keine Prozessisolation. Der Klartextschlüssel ist
während einer Operation im Gateway-Speicher vorhanden. Das Plugin schreibt oder loggt ihn nicht
und überschreibt seine eigenen Buffer-Kopien nach jeder Tool-Ausführung; Laufzeit, Garbage
Collector und OpenClaw-Runtime können weitere nicht kontrollierbare Kopien halten.

Das Manifest muss für OpenClaws zweistufige Schema-Prüfung sowohl den SecretRef als auch den
materialisierten Runtime-String akzeptieren. Deshalb gehört `openclaw secrets audit --check`
nach jeder Konfigurationsänderung zum Deployment-Gate; Clawake deklariert ausschließlich den
Store-Ref und niemals einen Klartextschlüssel.

## Vertraulichkeit und Integrität

- AES-256-GCM authentifiziert jeden Datensatz einzeln.
- Jede Verschlüsselung verwendet einen neuen 12-Byte-Nonce aus `randomBytes`.
- Associated Data bindet Formatversion, Datensatz-ID und Schlüsselversion.
- Schlüssel/Wert/Alias/Beziehung/Änderungszeit liegen nur im Ciphertext.
- Dateiname, Datensatzanzahl, zufällige Datensatz-IDs, Ciphertext-Längen, Algorithmus und
  Schlüsselversionen bleiben sichtbar.
- Manipulation führt zu einem generischen Authentifizierungsfehler; es gibt keinen
  Klartext-Fallback.

## Zugriffskontrolle

Der Tool-Factory-Kontext wird nur akzeptiert, wenn `context.agentId` exakt der konfigurierten
`allowedAgentId` entspricht. Fehlt die host-vertrauenswürdige Agent-ID, wird das Tool nicht
registriert. Zusätzlich sind erforderlich:

- Plugin standardmäßig deaktiviert und explizit allowgelistet;
- Tool `pflege_vault` optional und nur in der Tool-Policy des Pflegebetreuer-Agenten erlaubt;
- restriktive Gateway-/Container-/Host-Berechtigungen.

Diese ACL schützt nicht vor dem Betreiber, einem kompromittierten Gateway oder anderem nativen
Code im selben Prozess. Die Korrektheit der Agent-ID-Zuordnung muss bei Inbetriebnahme geprüft
werden. Ein Anzeigename oder die Persona „Pflegebetreuer“ ist keine ACL.

## Persistenz, Schreiben und Backups

Der konfigurierte Pfad muss absolut und außerhalb des aktuellen Agent-Workspace liegen. Bei
fehlender Workspace-Grenze verweigert das Tool den Zugriff. Symlinks und fremde Eigentümer werden
abgewiesen; Rechte werden auf `0700`/`0600` reduziert. Writes erfolgen in derselben Directory über
eine exklusive temporäre Datei, Datei-`fsync`, atomaren `rename` und Directory-`fsync`.

Ein Container-Neustart überlebt nur, wenn `vaultPath` tatsächlich auf einem persistenten Volume
liegt. Das Plugin kann Mount-Persistenz nicht beweisen. Backups dürfen nur die Ciphertext-Datei
und niemals entschlüsselte Exporte oder Secret-Store-Werte enthalten. Weil der Pfad konfigurierbar
und außerhalb des OpenClaw-State-Roots sein kann, ist er nicht als statische
`backupResources`-Ressource im Manifest deklariert.

## Löschung und Rotation

`delete` entfernt den Datensatz aus der neuen atomaren Vault-Datei. Sichere physische Löschung
alter Blöcke, Snapshots, temporärer Storage-Layer und Backups ist auf üblichen SSD-,
Copy-on-write- und Container-Dateisystemen nicht garantiert.

`rotate` liest alle Datensätze mit aktiven/vorherigen Versionen und ersetzt die Datei vollständig
unter der aktiven Version. Alte Schlüssel erst nach erfolgreicher Verifikation entfernen.
Crash-Konsistenz wird auf einem lokalen POSIX-Dateisystem angestrebt; Garantien von Netzwerk- und
Union-Dateisystemen hängen vom jeweiligen Volume-Treiber ab.

## Klartext außerhalb der Datei

`get` muss den Wert als Tool-Ergebnis an den Agenten zurückgeben. Dadurch kann Klartext in
OpenClaw-Run-/Sitzungskontext, Modellkontext oder administrativer Telemetrie erscheinen, auch wenn
das Plugin selbst nichts loggt. Das Storage-Plugin allein kann diese Laufzeitspur nicht
eliminieren. Nur minimal notwendige Werte abrufen, Sitzungsaufbewahrung und Telemetrie separat
härten und keine Vault-Inhalte in Gruppen oder unberechtigte Kanäle weitergeben.

## Bekannte Grenzen

- nur In-Process-Serialisierung; zwei Gateway-Prozesse auf derselben Datei können Updates
  verlieren, obwohl die Datei atomar bleibt;
- keine Größenverschleierung, kein ORAM und keine Metadaten-Verbergung;
- keine semantisch belastbare Erkennung von Gmail-Inhalten im freien `value`-Feld;
- keine physische Löschgarantie;
- keine automatische Backup-Erstellung oder Secret-Rotation;
- Plugin-API ist experimentell und auf OpenClaw `2026.9.2` gepinnt.
