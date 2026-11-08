"""Kommandozeile: einrichten, einmal abrufen oder dauerhaft im Hintergrund laufen."""

from __future__ import annotations

import argparse
import getpass
import imaplib
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from . import __version__
from .ablage import Ablage
from .config import STANDARD_KONFIG_DATEI, Konfig, imap_server_fuer
from .erkennung import bewerte
from .postfach import Mail, Postfach, start_datum

KEYRING_DIENST = "rechnungen-automatisch"


def log(text: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {text}", flush=True)


# ---------------------------------------------------------------- Passwort
def _keyring():
    try:
        import keyring  # optional
        return keyring
    except ImportError:
        return None


def passwort_holen(konfig: Konfig) -> str:
    if os.environ.get("RECHNUNGEN_PASSWORT"):
        return os.environ["RECHNUNGEN_PASSWORT"]
    kr = _keyring()
    if kr:
        try:
            pw = kr.get_password(KEYRING_DIENST, konfig.email)
            if pw:
                return pw
        except Exception:
            pass
    if konfig.passwort:
        return konfig.passwort
    return getpass.getpass(f"Passwort für {konfig.email}: ")


# ---------------------------------------------------------------- Kernlogik
def plausibles_datum(rechnungsdatum: date | None, maildatum: date) -> date:
    """Nimmt das Datum aus der Rechnung, wenn es zum Eingang der Mail passt."""
    if rechnungsdatum and (
        maildatum - timedelta(days=120) <= rechnungsdatum <= maildatum + timedelta(days=7)
    ):
        return rechnungsdatum
    return maildatum


def verarbeite_mail(mail: Mail, ablage: Ablage, ausfuehrlich: bool = False) -> list[Path]:
    gespeichert = []
    for anhang in mail.anhaenge:
        ergebnis = bewerte(anhang.dateiname, anhang.daten, mail.betreff, mail.text)
        if ausfuehrlich:
            log(f"  {anhang.dateiname}: {ergebnis.punkte} Punkte "
                f"({'; '.join(ergebnis.gruende)})")
        if not ergebnis.ist_rechnung:
            continue
        d = plausibles_datum(ergebnis.datum, mail.datum)
        ziel = ablage.speichern(anhang.daten, anhang.dateiname, d, mail.absender, mail.betreff)
        if ziel:
            gespeichert.append(ziel)
    return gespeichert


def abrufen(konfig: Konfig, passwort: str, ausfuehrlich: bool = False) -> int:
    ablage = Ablage(konfig.ziel_ordner, konfig.zustand_datei)
    zustand = ablage._zustand
    anzahl = 0
    with Postfach(konfig.imap_server, konfig.imap_port, konfig.email, passwort) as pf:
        for ordner in konfig.ordner:
            merk = zustand["letzte_uid"].get(ordner, {})
            seit = start_datum(konfig.tage_zurueck)
            try:
                uidvalidity = pf.oeffne(ordner)
            except RuntimeError as e:
                log(f"Warnung: {e}")
                continue
            ab_uid = merk.get("uid", 0) if merk.get("uidvalidity") == uidvalidity else 0
            gesamt, mails = pf.mails(seit, ab_uid)
            log(f"Ordner '{ordner}': {gesamt} neue E-Mail(s) zu prüfen")
            hoechste = ab_uid
            for mail in mails:
                hoechste = max(hoechste, mail.uid)
                if ablage.mail_bekannt(mail.message_id):
                    continue
                if ausfuehrlich:
                    log(f"{mail.datum} {mail.absender}: {mail.betreff}")
                for ziel in verarbeite_mail(mail, ablage, ausfuehrlich):
                    anzahl += 1
                    log(f"Rechnung gespeichert: {ziel.relative_to(ablage.basis)}")
                ablage.mail_merken(mail.message_id)
                zustand["letzte_uid"][ordner] = {"uidvalidity": uidvalidity, "uid": hoechste}
                ablage.speichere_zustand()
            zustand["letzte_uid"][ordner] = {"uidvalidity": uidvalidity, "uid": hoechste}
            ablage.speichere_zustand()
    log(f"Fertig – {anzahl} neue Rechnung(en) in {konfig.ziel_ordner}")
    return anzahl


# ---------------------------------------------------------------- Befehle
def _frage(text: str, standard: str = "") -> str:
    zusatz = f" [{standard}]" if standard else ""
    antwort = input(f"{text}{zusatz}: ").strip()
    return antwort or standard


def befehl_einrichten(pfad: Path) -> None:
    alt = Konfig.laden(pfad) if pfad.exists() else Konfig()
    print("=== Einrichtung: Rechnungen automatisch aus E-Mails ===\n")
    k = alt
    k.email = _frage("Deine E-Mail-Adresse", alt.email)
    k.imap_server = _frage("IMAP-Server", alt.imap_server or imap_server_fuer(k.email) or "")
    k.imap_port = int(_frage("IMAP-Port", str(alt.imap_port)))
    k.ziel_ordner = _frage("Wohin sollen die Rechnungen gespeichert werden?", alt.ziel_ordner)
    k.tage_zurueck = int(_frage("Wie viele Tage zurück beim ersten Abruf?", str(alt.tage_zurueck)))
    k.intervall_minuten = int(_frage("Abruf-Intervall im Dauerbetrieb (Minuten)",
                                     str(alt.intervall_minuten)))

    print("\nHinweis: Bei Gmail, Outlook, iCloud & Yahoo brauchst du ein App-Passwort"
          " (siehe README).")
    passwort = getpass.getpass("Passwort / App-Passwort: ")

    print("Teste Anmeldung ...")
    try:
        with Postfach(k.imap_server, k.imap_port, k.email, passwort) as pf:
            verfuegbar = pf.ordner_liste()
    except (imaplib.IMAP4.error, OSError) as e:
        print(f"Anmeldung fehlgeschlagen: {e}")
        sys.exit(1)
    print("Anmeldung erfolgreich!")
    if verfuegbar:
        print("Verfügbare Ordner: " + ", ".join(verfuegbar))
    ordner = _frage("Welche Ordner durchsuchen? (Komma-getrennt)", ",".join(alt.ordner))
    k.ordner = [o.strip() for o in ordner.split(",") if o.strip()]

    kr = _keyring()
    k.passwort = ""
    if kr and _frage("Passwort sicher im Schlüsselbund speichern? (j/n)", "j").lower() == "j":
        kr.set_password(KEYRING_DIENST, k.email, passwort)
        print("Passwort im Schlüsselbund gespeichert.")
    elif _frage("Passwort in der Konfigurationsdatei speichern (unverschlüsselt)? (j/n)",
                "n").lower() == "j":
        k.passwort = passwort

    k.speichern(pfad)
    print(f"\nKonfiguration gespeichert: {pfad}")
    print("Starte jetzt mit:  python -m rechnungen abrufen   (einmalig)")
    print("              oder python -m rechnungen dauerbetrieb  (automatisch)")


def _konfig_oder_ende(pfad: Path) -> Konfig:
    if not pfad.exists():
        print("Noch keine Konfiguration. Bitte zuerst ausführen:  python -m rechnungen einrichten")
        sys.exit(1)
    return Konfig.laden(pfad)


def befehl_abrufen(pfad: Path, ausfuehrlich: bool) -> None:
    k = _konfig_oder_ende(pfad)
    try:
        abrufen(k, passwort_holen(k), ausfuehrlich)
    except imaplib.IMAP4.error as e:
        log(f"Fehler bei der Anmeldung/Abfrage: {e}")
        sys.exit(1)


def befehl_dauerbetrieb(pfad: Path, ausfuehrlich: bool) -> None:
    k = _konfig_oder_ende(pfad)
    passwort = passwort_holen(k)
    log(f"Dauerbetrieb gestartet – Abruf alle {k.intervall_minuten} Minuten. "
        "Beenden mit Strg+C.")
    while True:
        try:
            abrufen(k, passwort, ausfuehrlich)
        except imaplib.IMAP4.error as e:
            log(f"Fehler: {e}")
        except OSError as e:
            log(f"Verbindungsproblem: {e} – neuer Versuch beim nächsten Durchlauf")
        try:
            time.sleep(k.intervall_minuten * 60)
        except KeyboardInterrupt:
            log("Beendet.")
            return


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(
        prog="rechnungen",
        description="Exportiert Rechnungen automatisch aus E-Mails und sortiert sie nach Monat.",
    )
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("-k", "--konfig", type=Path, default=STANDARD_KONFIG_DATEI,
                   help=f"Konfigurationsdatei (Standard: {STANDARD_KONFIG_DATEI})")
    p.add_argument("-v", "--ausfuehrlich", action="store_true",
                   help="Zeigt für jeden Anhang, warum er (k)eine Rechnung ist")
    sub = p.add_subparsers(dest="befehl", required=True)
    sub.add_parser("einrichten", help="E-Mail-Konto und Zielordner einrichten")
    sub.add_parser("abrufen", help="Einmal alle neuen E-Mails nach Rechnungen durchsuchen")
    sub.add_parser("dauerbetrieb", help="Regelmäßig automatisch abrufen")
    a = p.parse_args(argv)

    try:
        if a.befehl == "einrichten":
            befehl_einrichten(a.konfig)
        elif a.befehl == "abrufen":
            befehl_abrufen(a.konfig, a.ausfuehrlich)
        elif a.befehl == "dauerbetrieb":
            befehl_dauerbetrieb(a.konfig, a.ausfuehrlich)
    except KeyboardInterrupt:
        print("\nAbgebrochen.")


if __name__ == "__main__":
    main()
