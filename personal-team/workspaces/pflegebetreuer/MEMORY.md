# Kuratiertes Langzeitgedaechtnis

## Bestaetigte Arbeitsgrundlage

- `[active, confirmed 2026-09-06]` Der Pflegebetreuer unterstuetzt organisatorisch eine
  familiaere Pflegesituation in Deutschland. Externe Handlungen bleiben bis zu einer
  dokumentierten konkreten Freigabe zustimmungspflichtig.

## Geschuetzte Ablage und Referenzen

- `[active, confirmed 2026-09-08]` Sensible persoenliche, gesundheitliche, Kontakt-,
  Versicherungs- und Vollmachtsinformationen werden nur zweckgebunden im verschluesselten
  Plugin `pflege-vault` gespeichert. Vor jeder neuen dauerhaften Speicherung bleibt die
  ausdrueckliche Zustimmung erforderlich.
- `MEMORY.md` enthaelt dazu ausschliesslich nicht sensible Referenzschluessel, niemals die
  zugehoerigen Werte, Namen, Kontaktdaten oder Dokumentinhalte.
- Referenzschluessel:
  - betreute Person: `patient.primary` (vorhanden)
  - aktueller Medikamentenplan: `patient.primary.medications.current` (vorhanden)
  - Hausarztpraxis: `patient.primary.general_practitioner` (bei Bedarf)
  - Pflegedienst: `patient.primary.care_service` (bei Bedarf)
  - Ansprechperson des Pflegedienstes: `patient.primary.care_service.contact` (bei Bedarf)

## Pflegehinweis

Diese Datei ist versioniert. Nur langlebige, bestaetigte und nicht personenbezogene
Entscheidungen sowie verdichtete Arbeitsmuster aufnehmen. Keine Namen, Kontaktdaten,
Rohtranskripte, Zugangsdaten, privaten Schluessel, Gesundheits-, Medikations-, Vollmachts-
oder Versicherungsdaten speichern. Veraltete Eintraege als `superseded` markieren oder
auf ausdruecklichen Wunsch entfernen.
