# Rechnungen automatisch aus E-Mails

Dieses Programm meldet sich mit deiner E-Mail-Adresse am Postfach an, durchsucht
die E-Mails nach **Rechnungen** und **Avis** (Zahlungsavis), speichert sie ab und
**sortiert sie automatisch nach Monat**. Alles andere – Auftragsbestätigungen,
Bestellbestätigungen, Lieferscheine, Angebote, Mahnungen, AGB usw. – wird ignoriert.

```
Rechnungen/
├── Rechnungsuebersicht.csv          ← Liste aller Belege (öffnet in Excel)
├── 2026/
│   ├── 09_September/
│   │   └── Rechnungen/
│   │       └── 2026-09-03_Telekom_Rechnung_123456.pdf
│   └── 10_Oktober/
│       ├── Rechnungen/
│       │   ├── 2026-10-14_Muster GmbH_Rechnung.pdf
│       │   └── 2026-10-21_Amazon_invoice.pdf
│       └── Avis/
│           ├── 2026-10-22_Kunde AG_Zahlungsavis.pdf
│           └── 2026-10-26_Kunde AG_Zahlungsavis 4711.eml
```

## So funktioniert die Erkennung

Für jeden PDF-Anhang wird die **Dokumentart** bestimmt – in dieser Reihenfolge:

1. **Text im PDF** – maßgeblich ist, was zuerst im Dokument steht (meist die Überschrift):
   * **Rechnung**: „Rechnung“, „Invoice“, „Gutschrift“, „Schlussrechnung“ … oder Felder
     wie „Rechnungsnummer“ / „Rechnungsdatum“
   * **Avis**: „Zahlungsavis“, „Avis“, „Zahlungsanzeige“, „Remittance/Payment Advice“
   * **Ignoriert**: „Auftragsbestätigung“, „Bestellbestätigung“, „Lieferschein“,
     „Angebot“, „Kostenvoranschlag“, „Proforma“, „Mahnung“, „Zahlungserinnerung“,
     „Versandbestätigung“, AGB, Datenschutz …
   * Verweise wie „Lieferschein-Nr. 123“ oder „Auftragsbestätigung Nr. AB-4711“ *auf
     einer Rechnung* machen sie nicht zur Auftragsbestätigung.
   * Wörter wie „Rechnungsadresse“ zählen nicht als Rechnung.
2. **Dateiname**, falls das PDF keinen lesbaren Text hat (z. B. Scan):
   „Rechnung_4711.pdf“, „RE-4711.pdf“ → Rechnung; „AB_4711.pdf“, „LS-123.pdf“ → ignoriert.
3. **Betreff der E-Mail** als letzter Hinweis.

XRechnung/ZUGFeRD-XML-Dateien werden immer als Rechnung erkannt.

**Avis ohne Anhang:** Kommt ein Avis nur als E-Mail-Text (Betreff z. B. „Zahlungsavis“),
wird die E-Mail selbst als `.eml`-Datei im Ordner `Avis` gespeichert (öffnet in Outlook).

Das **Belegdatum** wird aus dem PDF gelesen (z. B. „Rechnungsdatum: 14.10.2026“).
Wird keins gefunden oder passt es nicht zum Eingang der E-Mail, wird das
Empfangsdatum der E-Mail verwendet.

Jeder Beleg wird nur **einmal** gespeichert, auch wenn er mehrfach ankommt.
Das Programm liest die E-Mails nur – es verändert, verschiebt oder löscht nichts
und markiert auch nichts als gelesen.

**Tipp:** Mit `python -m rechnungen -v abrufen` siehst du für jeden Anhang, ob er als
Rechnung, Avis oder gar nicht archiviert wird – und warum.

## Installation

1. **Python 3.10 oder neuer** installieren: <https://www.python.org/downloads/>
   (unter Windows bei der Installation „Add Python to PATH“ anhaken).
2. Diesen Ordner herunterladen und darin einmal ausführen:

   ```
   pip install -r requirements.txt
   ```

## Einrichten (einmalig)

```
python -m rechnungen einrichten
```

Du wirst nach E-Mail-Adresse, Passwort und Zielordner gefragt. Der IMAP-Server wird
für bekannte Anbieter (Gmail, Outlook/Hotmail, GMX, web.de, T-Online, Yahoo, iCloud,
IONOS, Strato, Posteo, mailbox.org …) automatisch eingetragen. Die Anmeldung wird
sofort getestet.

Das Passwort wird – wenn möglich – sicher im Schlüsselbund des Betriebssystems
(Windows-Anmeldeinformationsverwaltung / macOS-Schlüsselbund) gespeichert.

### Wichtig: App-Passwort bei manchen Anbietern

| Anbieter | Was tun? |
|---|---|
| **Gmail** | 2-Faktor-Anmeldung aktivieren, dann unter <https://myaccount.google.com/apppasswords> ein App-Passwort erstellen und dieses verwenden. |
| **GMX / web.de** | In den Einstellungen unter „POP3/IMAP Abruf“ den IMAP-Zugriff erlauben. |
| **iCloud / Yahoo** | App-spezifisches Passwort in den Kontoeinstellungen erzeugen. |
| **Outlook.com / Microsoft 365** | Microsoft hat die Anmeldung mit normalem Passwort per IMAP weitgehend abgeschaltet; das funktioniert nur, wenn der Administrator IMAP mit App-Passwort erlaubt. |
| **Eigene Domain (z. B. IONOS, Strato, all-inkl)** | Normales Postfach-Passwort; IMAP-Server steht beim Anbieter im Kundenbereich. |

## Benutzen

**Einmal abrufen:**

```
python -m rechnungen abrufen
```

**Automatisch dauerhaft** (prüft alle 15 Minuten, einstellbar):

```
python -m rechnungen dauerbetrieb
```

Beim ersten Abruf werden die E-Mails der letzten 365 Tage durchsucht (einstellbar),
danach nur noch neue E-Mails.

Mit `-v` siehst du für jeden Anhang, ob und warum er archiviert wird:

```
python -m rechnungen -v abrufen
```

### Unter Windows per Doppelklick

* `Einrichten.bat` – Einrichtung starten
* `Rechnungen-abrufen.bat` – einmal abrufen
* `Rechnungen-automatisch.bat` – Dauerbetrieb

Damit es nach jedem Neustart automatisch läuft: Verknüpfung zu
`Rechnungen-automatisch.bat` in den Autostart-Ordner legen
(`Win + R` → `shell:startup`). Alternativ in der Windows-Aufgabenplanung
stündlich `python -m rechnungen abrufen` mit diesem Ordner als „Starten in“ ausführen.

### Mac / Linux: regelmäßig per cron

```
*/30 * * * * cd /pfad/zu/Rechnungen-automatisch- && python3 -m rechnungen abrufen >> ~/rechnungen.log 2>&1
```

## Einstellungen ändern

Einfach `python -m rechnungen einrichten` erneut ausführen, oder die Datei
`~/.rechnungen/config.json` bearbeiten:

| Feld | Bedeutung |
|---|---|
| `ordner` | Welche Postfach-Ordner durchsucht werden, z. B. `["INBOX", "Rechnungen"]` |
| `ziel_ordner` | Wohin die Rechnungen gespeichert werden |
| `tage_zurueck` | Wie weit beim ersten Abruf zurückgeschaut wird |
| `intervall_minuten` | Abstand der Abrufe im Dauerbetrieb |

Um alles noch einmal neu zu durchsuchen, die Datei `.verarbeitet.json` im Zielordner
löschen (bereits gespeicherte Dateien werden trotzdem nicht doppelt angelegt,
solange die Datei vorhanden ist – sonst entstehen ggf. Kopien).

## Tests

```
pip install pytest
python -m pytest
```
