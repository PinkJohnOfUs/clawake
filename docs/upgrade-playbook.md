# Upgrade-Playbook

Ein Upgrade ist ein kontrollierter, mehrstufiger Ablauf, **keine atomare Transaktion**.
Den konkreten WhatsApp/API-Konflikt des Pflegebetreuers erklärt das
[Betriebshandbuch](manual.md). Stand: 7. September 2026.

## Ziel auswählen und Vorschau prüfen

1. Laufende Version und benötigte Plugin-API feststellen.
2. Veröffentlichtes Zielimage einschließlich Browser-/Slim-Variante auswählen.
3. Passenden Image-Manifest-Digest aus der offiziellen Registry verifizieren.
4. Backup-Quellen, freien Speicher und Wiederherstellbarkeit prüfen.

Vom Repository-Verzeichnis aus:

```bash
export CLAWAKE_PROJECT_ROOT="$PWD"
uv run clawake upgrade -c personal-team/team.yml -m pflegebetreuer \
  --to "${CLAWAKE_TARGET_TAG:?Verifizierten Ziel-Tag setzen}" \
  --digest "${CLAWAKE_TARGET_DIGEST:?Passenden Image-Digest setzen}"
```

Die Vorschau ändert nichts und kontaktiert keine Registry. Sie beweist weder
Image-Verfügbarkeit noch Plugin-Kompatibilität. Beim Tagwechsel ist ein Digest
verpflichtend. Ein veraltetes, fest eingebautes Beispielziel soll nicht als
Upgrade-Empfehlung missverstanden werden.

## Voraussetzungen für Recovery

`backup_policy.enabled` und `pre_mutation` müssen für eine automatische Sicherung
aktiviert sein. `.backups/` liegt relativ zum aktuellen Arbeitsverzeichnis. Gesichert
werden das Inventar sowie Workspace, Teamdefinition und zusätzliche Policy-Pfade.
Environment-Dateien außerhalb dieser Quellen sind nicht automatisch enthalten.

Der gegenwärtige Backup-Code kann unlesbare Dateien überspringen und fehlende
Quellen auslassen. Daher sind vollständige Sicherung und Restore-Probe vor einer
kritischen Migration gesondert zu gewährleisten. Ein Archiv allein genügt nicht.
Sicherungen enthalten gegebenenfalls Sitzungsschlüssel und persönliche Daten;
entsprechend geschützt aufbewahren. Nach erfolgreichem Upgrade greift die
konfigurierte Aufbewahrungszahl, im persönlichen Inventar sieben.

## Ausführen

```bash
uv run clawake upgrade -c personal-team/team.yml -m pflegebetreuer \
  --to "${CLAWAKE_TARGET_TAG:?Ziel-Tag fehlt}" \
  --digest "${CLAWAKE_TARGET_DIGEST:?Ziel-Digest fehlt}" --execute
```

Die aktuelle Reihenfolge:

1. Registry-Manifeste für Tag und Digest prüfen.
2. Ausgewählten Dienst stoppen.
3. Nach Policy Inventar und Laufzeitdaten sichern.
4. Gegebenenfalls Browser-Cache vorbereiten.
5. `openclaw doctor --fix --non-interactive --yes` im Zielimage mit den persistenten
   Mounts ausführen; dieser Schritt kann Daten bereits verändern.
6. Image-Paar im Inventar aktualisieren und vorheriges Paar als `known_good_*` merken.
7. Verwaltete OpenClaw-Konfiguration und Quadlets anwenden.
8. systemd neu laden, Dienst neu starten, HTTP-Health und Runtime-/Image-Angaben prüfen.
9. Alte Sicherungen nach Retention entfernen.

`known_good_*` benennt den vorherigen Inventarstand; der alte Zustand wird nicht
vorab separat als gesund zertifiziert. Andere Mitglieder werden nicht gezielt neu
gestartet; `daemon-reload` betrifft den gemeinsamen systemd-User-Manager.

## Verhalten bei Fehlern

| Fehlerzeitpunkt | Aktuelle Reaktion | Operator-Aufgabe |
| --- | --- | --- |
| Image-Prüfung | Abbruch vor Dienst-Stopp | Referenzen bzw. Registry-Zugriff korrigieren |
| Nach Stopp, vor Inventaränderung | Versuch, den vorherigen Dienst zu starten | Prüfen, ob eine Migration bereits Daten verändert hat |
| Nach Inventaränderung | Versuch, den fehlgeschlagenen Dienst zu stoppen | Gemeldete Recovery-Dateien und Journal prüfen |

Diese Reaktionen ersetzen keinen Rollback. Auch das Stoppen oder Wiederanlaufen
kann fehlschlagen. Ein abgebrochener Schreibvorgang kann zudem einen teilweise
geänderten Zustand hinterlassen.

## Manuelle Wiederherstellung

Es existiert noch kein `clawake rollback`-Befehl.

1. Den tatsächlichen Dienstzustand prüfen und einen laufenden fehlerhaften Dienst
   mit `systemctl --user stop pflegebetreuer.service` stoppen.
2. Fehlgeschlagenen Datenstand bei Bedarf separat sichern und Journal prüfen.
3. Die ausgewählte vertrauenswürdige Sicherung in ein **separates** Verzeichnis
   entpacken; Archivstruktur, Vollständigkeit und Dateirechte prüfen. Der Backup-Code
   verwendet nummerierte Wurzeln wie `01__fokus`, nicht direkt die Zielpfade.
4. Zusammenpassende Laufzeitdaten und das vorherige Image-Paar wiederherstellen.
   Nicht blind das ganze Team-Inventar zurückkopieren: Es kann inzwischen Änderungen
   an anderen Mitgliedern enthalten. Secret-Dateien bei Bedarf separat wiederherstellen.
5. `validate` und Setup-Vorschau für das Mitglied prüfen; erst dann
   `setup -c personal-team/team.yml -m pflegebetreuer --execute` ausführen.
6. Runtime, Anwendungszustand und Kanäle überprüfen. Setup startet bereits neu;
   ein zusätzlicher Restart ist nicht erforderlich.

Ein Downgrade des Images allein macht Datenmigrationen nicht rückgängig. Eine
Wiederherstellung kann Änderungen seit dem Sicherungszeitpunkt verlieren.
