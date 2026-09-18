# User Journey: Ein Team betreiben, Fähigkeiten bewusst erweitern

## Vision

„Ich möchte meinem Pflegebetreuer WhatsApp geben. Zeige mir, was dafür fehlt,
welche Daten und Rechte betroffen sind und wie ich die Änderung verlässlich
vorbereite, anwende und überprüfe.“

Clawake soll diese Absicht in einen nachvollziehbaren Betriebsvorgang übersetzen.
Der Nutzer denkt in Mitgliedern und Fähigkeiten. Die CLI verbindet diese Sicht mit
Image-Versionen, Laufzeitkompatibilität, Zugriffsumfang und Wiederherstellung.
OpenClaw bleibt für Agentenfunktionen und Kanaleinrichtung zuständig.

## Ausgangspunkt

Das persönliche Team enthält `alltags-navigator`, `reflexions-coach` und
`pflegebetreuer`. Die Namen im Inventar sind die CLI-Selektoren; Anzeigename und Rolle
können davon abweichen. Die wiederkehrende Aufgabe ist nicht bloß „Container starten“,
sondern einen arbeitsfähigen, verständlich abgegrenzten und wartbaren Partner erhalten.

Der WhatsApp-Installationsfehler vom 7. September zeigt eine aktuelle Produktlücke:
Die Plugin-Auswahl verlangte API 2026.9.2, während die Pflegebetreuer-Runtime 2026.8.2
ausführte. Der Operator musste selbst vom Pluginfehler zum passenden Runtime-Upgrade
wechseln. Nach dem Upgrade blockierte zusätzlich das DNS-Forwarding des
Podman-Netzwerks den npm-Zugriff; erst ein expliziter Resolver im Inventar machte
die gepinnte Installation möglich.

## Reise mit der heutigen CLI

| Schritt | Nutzerabsicht | Heute verfügbar | Erkennbarer Erfolg |
| --- | --- | --- | --- |
| 1. Beschreiben | Rolle, Workspace, Image und Zugriffe festlegen | Inventar bearbeiten; `validate -c …` | Inventar und Rendering gültig; Rechte bewusst geprüft |
| 2. Verstehen | Änderungen vorab sehen | `setup -c … -m pflegebetreuer` | Dateiziele und Neustartumfang sichtbar, keine Dateien geschrieben |
| 3. Bereitstellen | Mitglied starten und konfigurieren | `setup … --execute`, `onboard … --execute` | Dienst läuft und Modellzugang funktioniert |
| 4. Beobachten | Störung lokalisieren | `status`, `logs`, `dashboard` | Systemd-Zustand und Diagnose sind zugänglich |
| 5. Erweitern | WhatsApp ermöglichen | OpenClaw-Pluginprüfung im Container; Runtime manuell abgleichen | Passendes Image und kompatibles Plugin ausgewählt |
| 6. Aktualisieren | Nur den Pflegebetreuer ändern | `upgrade … -m pflegebetreuer --to TAG --digest DIGEST`, dann `--execute` | Runtime und Image geprüft; Recovery-Grundlage separat bestätigt |
| 7. Verbinden | Konto und Absenderzugriff einrichten | OpenClaw-Kanalsetup und QR-Verknüpfung | Gewünschter Kanal und Zugriffspolitik funktionieren |
| 8. Abnehmen | Funktion und Rechte kontrollieren | Kanalprobe, OpenClaw-Sicherheitsaudit, bewusster Testkontakt | Verbindung funktioniert, unerwünschter Zugriff bleibt ausgeschlossen |
| 9. Wiederherstellen/entfernen | Fehler begrenzen oder Mitglied stilllegen | Manuelle Recovery; `teardown … --execute` | Passender Daten-/Runtime-Stand wiederhergestellt bzw. Dienst entfernt |

Konkrete, kopierbare Befehle stehen im [Betriebshandbuch](manual.md). Es gibt heute
keine automatische Plugin-Kompatibilitätsauflösung, kein Plugin-Lock und keinen
CLI-Rollback. Ein aktiver Dienst gilt nicht automatisch als fachlich arbeitsfähig.

## Gewünschte Erfahrung am WhatsApp-Beispiel

Dies ist ein **Zielbild, keine bereits vorhandene Kommando-Syntax**:

1. Der Nutzer wählt Pflegebetreuer und die gewünschte WhatsApp-Fähigkeit.
2. Clawake erklärt: laufende Runtime, benötigte Plugin-API, geeignete veröffentlichte
   Image-Variante und Auswirkungen auf Zugänge, Daten sowie Verfügbarkeit.
3. Die Vorschau zeigt einen konkreten Plan mit geprüftem Digest, Plugin-Version,
   Sicherungsumfang, Migrationen und Wiederherstellungsweg. Offene Prüfungen werden
   als offen angezeigt; inkompatible Kombinationen werden vor der Installation gestoppt.
4. Der Nutzer führt denselben überprüften Plan explizit aus. Nur das gewählte
   Mitglied wird geändert. Keine wiederholten Bestätigungen für bereits festgelegte
   Schritte; neue Rechte oder geänderte Voraussetzungen brauchen eine neue Entscheidung.
5. Clawake führt in OpenClaws natives Kanalsetup. QR und Geheimnisse werden nicht
   in allgemeinen Statusberichten verbreitet.
6. Der Abschluss unterscheidet Runtime bereit, Plugin geladen, Kanal verbunden und
   Zugriff geprüft. Eine echte Nachricht wird nur bewusst als Test ausgelöst.
7. Scheitert die Änderung, nennt die CLI die betroffene Phase und bietet einen
   überprüfbaren Wiederherstellungsweg für genau dieses Mitglied.

## Sicherheitsversprechen aus Nutzersicht

Der Nutzer soll erkennen können, welche Hostdaten, Konten und Netzwerkziele ein
Mitglied erreichen darf. Mehr Schichten allein sind kein Erfolgskriterium. OpenClaw
steuert Kanal- und Werkzeugrechte; der äußere Container begrenzt zusätzlich den
Gateway mitsamt Plugins. Quadlet beschreibt diese Ausführungsumgebung, Clawake
macht Änderungen daran prüfbar. Die [Sicherheitsbewertung](security.md) trennt
bestehende Regeln, offene Lücken und Szenarien, in denen OpenClaw allein genügt.

## Woran wir die Vision messen

- Die CLI erklärt API-Konflikte vor einer mutierenden Installation mit einer
  überprüfbaren Handlungsoption.
- Ein Mitglied lässt sich aktualisieren, ohne andere Mitglieder neu zu starten.
- Vorschauen zeigen neben Dateien auch Änderungen an Runtime-Konfiguration und Rechten.
- Eine unvollständige Sicherung verhindert die Migration; eine Restore-Probe belegt
  Wiederherstellbarkeit statt nur die Existenz einer Archivdatei.
- Status unterscheidet Dienst, Runtime, Plugin und Kanal; automatisierbare Ausgabe
  enthält keine Tokens.
- Der Standardweg benötigt keine handgeschriebenen Podman-Befehle für Deployment
  und Recovery, nutzt aber weiterhin OpenClaws eigenes Onboarding.

Diese Kriterien priorisieren die CLI vor einem Dashboard oder Remote-Orchestrierung.
