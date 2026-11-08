"""Verbindung zum E-Mail-Postfach (IMAP) und Auslesen der Anhänge."""

from __future__ import annotations

import email
import imaplib
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from email.header import decode_header, make_header
from email.message import Message
from email.utils import parseaddr, parsedate_to_datetime


@dataclass
class Anhang:
    dateiname: str
    daten: bytes


@dataclass
class Mail:
    uid: int
    message_id: str
    betreff: str
    absender: str
    datum: date
    text: str
    anhaenge: list[Anhang] = field(default_factory=list)
    roh: bytes = b""


def _dekodiere(wert: str | None) -> str:
    if not wert:
        return ""
    try:
        return str(make_header(decode_header(wert)))
    except Exception:
        return wert


def _absender_name(wert: str) -> str:
    name, adresse = parseaddr(_dekodiere(wert))
    if name:
        return name
    if "@" in adresse:
        return adresse.split("@", 1)[1].split(".")[0]
    return adresse or "unbekannt"


def _text_aus(nachricht: Message) -> str:
    teile = []
    for teil in nachricht.walk():
        if teil.get_content_maintype() != "text" or teil.get_filename():
            continue
        try:
            nutzlast = teil.get_payload(decode=True) or b""
            zeichensatz = teil.get_content_charset() or "utf-8"
            text = nutzlast.decode(zeichensatz, errors="ignore")
        except (LookupError, AttributeError):
            continue
        if teil.get_content_subtype() == "html":
            text = re.sub(r"<[^>]+>", " ", text)
        teile.append(text)
    return "\n".join(teile)


def mail_aus_bytes(uid: int, roh: bytes) -> Mail:
    nachricht = email.message_from_bytes(roh)
    try:
        datum = parsedate_to_datetime(nachricht.get("Date")).date()
    except (TypeError, ValueError):
        datum = date.today()
    anhaenge = []
    for teil in nachricht.walk():
        dateiname = _dekodiere(teil.get_filename())
        if not dateiname:
            continue
        daten = teil.get_payload(decode=True)
        if daten:
            anhaenge.append(Anhang(dateiname, daten))
    return Mail(
        uid=uid,
        message_id=(nachricht.get("Message-ID") or f"uid-{uid}").strip(),
        betreff=_dekodiere(nachricht.get("Subject")),
        absender=_absender_name(nachricht.get("From", "")),
        datum=datum,
        text=_text_aus(nachricht),
        anhaenge=anhaenge,
        roh=roh,
    )


_IMAP_MONATE = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


class Postfach:
    def __init__(self, server: str, port: int, benutzer: str, passwort: str):
        self.server = server
        self.port = port
        self.benutzer = benutzer
        self.passwort = passwort
        self.imap: imaplib.IMAP4_SSL | None = None

    def __enter__(self) -> "Postfach":
        self.imap = imaplib.IMAP4_SSL(self.server, self.port)
        self.imap.login(self.benutzer, self.passwort)
        return self

    def __exit__(self, *args) -> None:
        if self.imap:
            try:
                self.imap.logout()
            except Exception:
                pass

    def ordner_liste(self) -> list[str]:
        typ, daten = self.imap.list()
        namen = []
        for zeile in daten or []:
            text = zeile.decode(errors="ignore") if isinstance(zeile, bytes) else str(zeile)
            m = re.search(r'"([^"]*)"\s*$|\s(\S+)$', text)
            if m:
                namen.append(m[1] or m[2])
        return namen

    def oeffne(self, ordner: str) -> int:
        """Öffnet einen Ordner (nur lesend) und liefert dessen UIDVALIDITY."""
        typ, _ = self.imap.select(f'"{ordner}"', readonly=True)
        if typ != "OK":
            raise RuntimeError(f"Ordner '{ordner}' konnte nicht geöffnet werden")
        antwort = self.imap.response("UIDVALIDITY")[1]
        return int(antwort[0]) if antwort and antwort[0] else 0

    def mails(self, seit: date, ab_uid: int = 0):
        """Liefert (Anzahl, Generator) für Mails im geöffneten Ordner mit UID > ab_uid."""
        imap_datum = f"{seit.day:02d}-{_IMAP_MONATE[seit.month - 1]}-{seit.year}"
        typ, daten = self.imap.uid("search", None, f"(SINCE {imap_datum})")
        uids = [int(u) for u in (daten[0] or b"").split()]
        uids = [u for u in uids if u > ab_uid]

        def generator():
            for uid in uids:
                typ, teile = self.imap.uid("fetch", str(uid), "(BODY.PEEK[])")
                if typ != "OK" or not teile or not isinstance(teile[0], tuple):
                    continue
                yield mail_aus_bytes(uid, teile[0][1])

        return len(uids), generator()


def start_datum(tage_zurueck: int) -> date:
    return (datetime.now() - timedelta(days=tage_zurueck)).date()
