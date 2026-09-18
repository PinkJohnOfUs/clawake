# Repository Roadmap

Stand: 7. September 2026. Die [User Journey](user_journey.md) beschreibt die gewünschte
Erfahrung; die [Sicherheitsbewertung](security.md) begründet die Prioritäten.

## Vorhandene Basis

- Lokales Team-Inventar, Validierung und Quadlet-Rendering.
- Schreibfreie Setup-Planung und explizite Anwendung.
- `setup`, `restart`, `status`, `teardown`, `onboard`, `dashboard`, `validate`, `logs`;
  bisherige lange Befehlsnamen bleiben verfügbar.
- Mitgliedsbezogenes Upgrade mit Image-Prüfung, optionaler Sicherung, Migration und
  Runtime-/Health-Prüfung; noch kein transaktionaler Rollback.
- Tests mit temporären Dateien und simulierten Runtime-Adaptern. Sie ersetzen
  keine Live-Abnahme der Sicherheits- und Wiederherstellungseigenschaften.

## Priorität 1: Änderungen vorab verlässlich beurteilen

- Plugin-API, Runtime, Image-Variante und veröffentlichten Digest abgleichen.
- Plugin-Pins und Quelle nachvollziehbar erfassen, ohne OpenClaws Installer zu duplizieren.
- Vollständigen Plan für Artefakte, Runtime-Konfiguration, Mounts und Neustarts liefern.
- Abnahme: Der WhatsApp/API-Konflikt wird vor einer Installation erklärt und eine
  überprüfte kompatible Kombination vorgeschlagen.

## Priorität 2: Wiederherstellung belegen

- Unvollständige Sicherungen vor Migration als Fehler behandeln.
- Secret- und Zustandsquellen explizit erfassen; Wiederherstellung pro Mitglied anbieten.
- Upgrade-Sequenz aus der CLI in testbare Workflows extrahieren.
- Abnahme: Restore-Probe für ein Testmitglied, einschließlich Fehler nach Migration
  und Fehler nach Inventaränderung, ohne andere Mitglieder zurückzusetzen.

## Priorität 3: Sicherheitsprofil durchsetzen

- Explizite, getestete Containerregeln für Gateway und Migrationscontainer.
- Mounts, Runtime-Sockets, Netzwerkexposition und Ressourcenbegrenzung prüfen.
- OpenClaws eigene Policies und Audits einbeziehen; innere Sandbox separat integrieren.
- Abnahme: Effektive Regeln sind sichtbar; Browser, Plugins und Upgrades funktionieren
  unter dem Profil. Ausnahmen sind Teil des Plans.

## Danach: Betrieb vereinfachen

- Status nach Dienst, Runtime, Plugin und Kanal differenzieren.
- Drift und letzten erfolgreich angewendeten Plan erfassen.
- Dashboard erst auf stabilen Workflows aufbauen.
- Remote-Betrieb erst mit ausdrücklichem Transport-, Host- und Vertrauensmodell.
