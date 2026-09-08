# Pflege Vault

Zweckgebundenes OpenClaw-Tool-Plugin für minimale sensible
Pflege-Schlüssel/Wert-Einträge. Alias und Beziehungsinformation sind optional. Das Plugin
speichert keine Gmail-Nachrichten und ist weder Dokumentenarchiv noch Ersatz für Einwilligung,
Vollmacht oder ein fachliches Pflegedokumentationssystem.

## Eigenschaften

- AES-256-GCM aus `node:crypto`, 96-Bit-Zufallsnonce je Datensatz und Schreibvorgang
- verschlüsselte Nutzdaten und Metadaten; im Dateikopf stehen nur Format, Algorithmus,
  Datensatz-IDs und Schlüsselversionen
- absoluter, konfigurierbarer Ciphertext-Pfad außerhalb des Agent-Workspace
- Verzeichnis `0700`, Datei und temporäre Dateien `0600`, Eigentümer- und Symlink-Prüfung
- atomarer Write über exklusive temporäre Datei, `fsync`, `rename` und Verzeichnis-`fsync`
- fail-closed Tool-Freigabe für genau eine konfigurierte, host-vertrauenswürdige Agent-ID
- optionale Tool-Registrierung; zusätzliche OpenClaw-Plugin- und Tool-Allowlisten bleiben nötig
- logische Löschung und atomare Umschlüsselung; Backups bestehen ausschließlich aus der
  Ciphertext-Datei

## Verwaltete Installation mit Clawake

Der Quellstand und das SHA-256-gepinnte Release werden von Clawake verwaltet. Das Secret
`PFLEGE_VAULT_MASTER_KEY` bleibt ausschließlich im write-only OpenClaw Secret Store und
wird weder in diesem Verzeichnis noch im Team-Inventar gespeichert.

Für die Inbetriebnahme muss der Betreiber:

1. einen zufälligen 32-Byte-Schlüssel außerhalb des Chats erzeugen und unter
   `Settings -> Secrets` als geschütztes Secret `PFLEGE_VAULT_MASTER_KEY` speichern;
2. `clawake sync-plugins` ausführen. Das Inventar bindet das Release read-only ein, verwendet
   `/home/node/.openclaw/pflege-vault/vault.json` im persistenten OpenClaw-State und erlaubt
   das optionale Tool nur Agent `main`;
3. Gateway-Version `2026.9.2` verwenden oder das Plugin gegen eine andere Version neu testen.

Schematische Konfiguration ohne echte IDs oder Schlüsselwerte:

```json5
{
  vaultPath: "/var/lib/openclaw/pflege-vault/vault.json",
  allowedAgentId: "<pflegebetreuer-agent-id>",
  activeKeyVersion: 1,
  masterKey: { source: "store", provider: "default", id: "<SECRET_STORE_NAME>" },
  previousKeys: []
}
```

Das Manifest verwendet das von OpenClaw dokumentierte `secretInput`-Paar aus SecretRef und
materialisiertem Runtime-String. Im verwalteten Quellzustand steht ausschließlich
`source: "store"`; `configContracts.secretInputs` materialisiert diesen Ref beim Start in den
In-Memory-Runtime-Snapshot. Das Deployment prüft mit `openclaw secrets audit`, dass kein
Klartextwert in der Konfiguration steht. Ein fehlender oder unauflösbarer Schlüssel macht die
Capability kalt beziehungsweise lässt das Plugin fail-closed.

## Datenmodell und Aktionen

Ein Klartext-Datensatz existiert nur im Prozessspeicher:

```text
{ id, key, value, alias?, relation?, updatedAt }
```

Das optionale Tool `pflege_vault` unterstützt:

- `put`: anlegen/ersetzen; erfordert `confirmed: true`
- `get`: einen Wert lesen
- `list`: Schlüssel, Alias, Beziehung und Änderungszeit auflisten, aber keine Werte
- `delete`: logisch löschen; erfordert `confirmed: true`
- `rotate`: alle Datensätze mit der aktiven Schlüsselversion neu verschlüsseln; erfordert
  `confirmed: true`

Gmail-Nachrichten, Anhänge, Zugangsdaten und nicht ausdrücklich freigegebene Gesundheitsdaten
dürfen nicht in `value` kopiert werden. Eine zuverlässige semantische Gmail-Erkennung ohne
zusätzliche Klartextverarbeitung gibt es nicht; diese Zweckgrenze wird organisatorisch und über
Tool-Beschreibung durchgesetzt.

## Rotation

1. Neuen Schlüssel als neues geschütztes Secret speichern.
2. `activeKeyVersion` erhöhen, `masterKey` auf den neuen SecretRef setzen und den alten unter
   `previousKeys` mit seiner alten Version vorübergehend behalten.
3. Konfiguration neu materialisieren und `rotate` nach konkreter Freigabe ausführen.
4. Lesen mit nur dem neuen Schlüssel verifizieren.
5. Erst dann alten SecretRef aus `previousKeys` und anschließend das alte Secret entfernen.

Jeder normale schreibende Vorgang verschlüsselt ebenfalls alle aktuellen Datensätze mit dem
aktiven Schlüssel neu. Veraltete Ciphertext-Kopien können jedoch in Snapshots, Backups oder
Copy-on-write-Dateisystemen fortbestehen.

## Testen

```bash
npm run check:no-sensitive-fixtures
npm test
```

Die Tests erzeugen Schlüssel ausschließlich flüchtig mit `randomBytes(32)` und schreiben nur
synthetische Datensätze in temporäre Betriebssystemverzeichnisse. Es gibt keine Schlüsseldatei,
keinen festen Testschlüssel und keine echten personenbezogenen Daten.

Siehe [SECURITY.md](./SECURITY.md) für Sicherheitsgrenzen und verbleibende Risiken.
