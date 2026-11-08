from datetime import date
from email.message import EmailMessage

from rechnungen import main as hauptmodul
from rechnungen.ablage import Ablage
from rechnungen.config import Konfig, imap_server_fuer
from rechnungen.erkennung import bewerte, finde_rechnungsdatum
from rechnungen.main import plausibles_datum
from rechnungen.postfach import mail_aus_bytes

from .pdf_helfer import mache_pdf

RECHNUNG_PDF = mache_pdf([
    "Muster GmbH - Musterstr. 1 - 12345 Berlin",
    "RECHNUNG",
    "Rechnungsnummer: RE-2026-0815",
    "Rechnungsdatum: 14.10.2026",
    "Leistungszeitraum: 01.09.2026 - 30.09.2026",
    "Nettobetrag 100,00 EUR",
    "MwSt 19% 19,00 EUR",
    "Gesamtbetrag 119,00 EUR",
    "Zahlbar bis 28.10.2026  IBAN DE00 1234",
])

AGB_PDF = mache_pdf([
    "Allgemeine Geschaeftsbedingungen",
    "1. Geltungsbereich",
    "Diese Bedingungen gelten fuer alle Vertraege.",
])


# ------------------------------------------------------------ Erkennung
def test_rechnung_wird_erkannt_und_datum_gelesen():
    e = bewerte("dokument.pdf", RECHNUNG_PDF, "Ihre Bestellung", "")
    assert e.ist_rechnung, e.gruende
    assert e.datum == date(2026, 10, 14)


def test_agb_ist_keine_rechnung():
    e = bewerte("AGB.pdf", AGB_PDF, "Ihre Bestellung", "")
    assert not e.ist_rechnung


def test_bild_ist_keine_rechnung():
    assert not bewerte("logo.png", b"\x89PNG", "Rechnung").ist_rechnung


def test_dateiname_und_betreff_reichen():
    e = bewerte("Rechnung_4711.pdf", b"kaputtes pdf", "Ihre Rechnung")
    assert e.ist_rechnung


def test_xrechnung_xml():
    xml = (b'<?xml version="1.0"?><Invoice xmlns="urn:oasis:names:specification:ubl:'
           b'schema:xsd:Invoice-2"><cbc:IssueDate>2026-03-05</cbc:IssueDate></Invoice>')
    e = bewerte("xrechnung.xml", xml)
    assert e.ist_rechnung and e.datum == date(2026, 3, 5)


def test_datumsformate():
    assert finde_rechnungsdatum("Rechnungsdatum: 3. März 2026") == date(2026, 3, 3)
    assert finde_rechnungsdatum("Invoice date: March 7, 2026") == date(2026, 3, 7)
    assert finde_rechnungsdatum("Datum 2026-02-01") == date(2026, 2, 1)
    assert finde_rechnungsdatum("Kunde seit 01.01.2019\nRechnungsdatum 05.06.26") == date(2026, 6, 5)


def test_plausibles_datum():
    mail = date(2026, 10, 15)
    assert plausibles_datum(date(2026, 10, 14), mail) == date(2026, 10, 14)
    assert plausibles_datum(date(2019, 1, 1), mail) == mail
    assert plausibles_datum(None, mail) == mail


def test_imap_server():
    assert imap_server_fuer("max@gmx.de") == "imap.gmx.net"
    assert imap_server_fuer("x@firma-unbekannt.de") is None


# ------------------------------------------------------------ Ablage
def test_ablage_nach_monat_und_ohne_doppelte(tmp_path):
    ablage = Ablage(tmp_path, tmp_path / ".zustand.json")
    p = ablage.speichern(RECHNUNG_PDF, "rechnung.pdf", date(2026, 10, 14), "Muster GmbH", "x")
    assert p == tmp_path / "2026" / "10_Oktober" / "2026-10-14_Muster GmbH_rechnung.pdf"
    assert p.read_bytes() == RECHNUNG_PDF
    assert ablage.speichern(RECHNUNG_PDF, "rechnung.pdf", date(2026, 10, 14), "A", "x") is None
    assert (tmp_path / "Rechnungsuebersicht.csv").exists()


# ------------------------------------------------------------ Gesamtablauf
def _mail_bytes(betreff, datum, anhaenge):
    m = EmailMessage()
    m["From"] = "Muster GmbH <rechnung@muster.de>"
    m["To"] = "ich@example.de"
    m["Subject"] = betreff
    m["Date"] = datum
    m["Message-ID"] = f"<{betreff}@muster.de>"
    m.set_content("Anbei Ihre Unterlagen.")
    for name, daten in anhaenge:
        m.add_attachment(daten, maintype="application", subtype="pdf", filename=name)
    return m.as_bytes()


class FalschesPostfach:
    """Ersetzt die IMAP-Verbindung im Test."""
    mails_roh = []

    def __init__(self, *args):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def oeffne(self, ordner):
        return 42

    def mails(self, seit, ab_uid=0):
        liste = [mail_aus_bytes(i + 1, roh) for i, roh in enumerate(self.mails_roh)
                 if i + 1 > ab_uid]
        return len(liste), iter(liste)


def test_gesamtablauf(tmp_path, monkeypatch):
    FalschesPostfach.mails_roh = [
        _mail_bytes("Ihre Rechnung Oktober", "Thu, 15 Oct 2026 10:00:00 +0200",
                    [("Rechnung.pdf", RECHNUNG_PDF), ("AGB.pdf", AGB_PDF)]),
        _mail_bytes("Newsletter", "Mon, 02 Nov 2026 10:00:00 +0100", []),
    ]
    monkeypatch.setattr(hauptmodul, "Postfach", FalschesPostfach)
    k = Konfig(email="ich@example.de", imap_server="x", ziel_ordner=str(tmp_path),
               tage_zurueck=10000)

    assert hauptmodul.abrufen(k, "pw") == 1
    dateien = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*.pdf"))
    assert dateien == ["2026/10_Oktober/2026-10-14_Muster GmbH_Rechnung.pdf"]

    # Zweiter Lauf: nichts Neues
    assert hauptmodul.abrufen(k, "pw") == 0


def test_umlaut_dateiname():
    roh = _mail_bytes("Rechnung", "Thu, 15 Oct 2026 10:00:00 +0200",
                      [("Gebühren März.pdf", RECHNUNG_PDF)])
    mail = mail_aus_bytes(1, roh)
    assert mail.anhaenge[0].dateiname == "Gebühren März.pdf"
    assert mail.absender == "Muster GmbH"
