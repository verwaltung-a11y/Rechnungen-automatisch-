"""Erkennt, ob ein Anhang eine Rechnung ist, und ermittelt das Rechnungsdatum."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import date

MONATE = {
    "januar": 1, "jan": 1, "january": 1,
    "februar": 2, "feb": 2, "february": 2,
    "märz": 3, "maerz": 3, "mär": 3, "mrz": 3, "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "mai": 5, "may": 5,
    "juni": 6, "jun": 6, "june": 6,
    "juli": 7, "jul": 7, "july": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "oktober": 10, "okt": 10, "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "dezember": 12, "dez": 12, "december": 12, "dec": 12,
}

MONATSNAMEN = [
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]

# Starke Hinweise (Dateiname, Betreff, Text)
STARKE_WORTE = [
    "rechnung", "invoice", "faktura", "rechnungsnummer", "rechnungs-nr",
    "rechnungsnr", "invoice number", "xrechnung", "zugferd", "gutschrift",
]
# Schwache Hinweise
SCHWACHE_WORTE = [
    "beleg", "quittung", "receipt", "zahlungsbestätigung", "kaufbeleg",
    "bestellbestätigung", "order confirmation", "abrechnung", "billing",
    "mwst", "umsatzsteuer", "netto", "brutto", "gesamtbetrag",
    "zahlbar bis", "fällig", "steuernummer", "ust-idnr", "iban",
]
# Typische Nicht-Rechnungen
AUSSCHLUSS_WORTE = [
    "agb", "datenschutz", "widerruf", "newsletter", "terms", "privacy",
    "allgemeine geschäftsbedingungen", "widerrufsbelehrung",
]

RECHNUNGS_ENDUNGEN = (".pdf", ".xml")

# Label vor dem Datum, das auf das Rechnungsdatum hinweist
_DATUM_LABEL = (
    r"(?:rechnungsdatum|rechnungs-datum|belegdatum|invoice date|date of issue|"
    r"datum der rechnung|ausstellungsdatum|leistungsdatum|datum|date)"
)
_DATUM_NUM = r"(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})"
_DATUM_ISO = r"(\d{4})-(\d{2})-(\d{2})"
_DATUM_TEXT = r"(\d{1,2})\.?\s+([a-zäöü]{3,9})\.?\s+(\d{4})"
_DATUM_TEXT_EN = r"([a-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})"


@dataclass
class Ergebnis:
    ist_rechnung: bool
    punkte: int
    datum: date | None
    gruende: list[str]


def _jahr(j: str) -> int:
    jahr = int(j)
    if jahr < 100:
        jahr += 2000
    return jahr


def _gueltig(jahr: int, monat: int, tag: int) -> date | None:
    try:
        d = date(jahr, monat, tag)
    except ValueError:
        return None
    if not (2000 <= d.year <= date.today().year + 1):
        return None
    return d


def _erstes_datum(text: str) -> date | None:
    """Sucht das erste plausible Datum in einem Textstück."""
    kandidaten: list[tuple[int, date]] = []
    for m in re.finditer(_DATUM_ISO, text):
        d = _gueltig(int(m[1]), int(m[2]), int(m[3]))
        if d:
            kandidaten.append((m.start(), d))
    for m in re.finditer(_DATUM_NUM, text):
        d = _gueltig(_jahr(m[3]), int(m[2]), int(m[1]))
        if d:
            kandidaten.append((m.start(), d))
    for m in re.finditer(_DATUM_TEXT, text):
        monat = MONATE.get(m[2])
        if monat:
            d = _gueltig(int(m[3]), monat, int(m[1]))
            if d:
                kandidaten.append((m.start(), d))
    for m in re.finditer(_DATUM_TEXT_EN, text):
        monat = MONATE.get(m[1])
        if monat:
            d = _gueltig(int(m[3]), monat, int(m[2]))
            if d:
                kandidaten.append((m.start(), d))
    if not kandidaten:
        return None
    return min(kandidaten, key=lambda k: k[0])[1]


def finde_rechnungsdatum(text: str) -> date | None:
    """Ermittelt das Rechnungsdatum aus dem Text einer Rechnung.

    Bevorzugt ein Datum direkt hinter einem Label wie "Rechnungsdatum".
    """
    if not text:
        return None
    klein = text.lower()
    # 1. Datum hinter einem Label (max. 40 Zeichen Abstand)
    for m in re.finditer(_DATUM_LABEL, klein):
        ausschnitt = klein[m.end(): m.end() + 40]
        d = _erstes_datum(ausschnitt)
        if d:
            return d
    # 2. Erstes Datum im Dokument
    return _erstes_datum(klein)


def pdf_text(daten: bytes, max_seiten: int = 3) -> str:
    """Extrahiert Text aus den ersten Seiten eines PDFs (leer bei Fehlern)."""
    try:
        from pypdf import PdfReader
    except ImportError:  # pragma: no cover
        return ""
    try:
        reader = PdfReader(io.BytesIO(daten))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                return ""
        teile = []
        for seite in reader.pages[:max_seiten]:
            teile.append(seite.extract_text() or "")
        return "\n".join(teile)
    except Exception:
        return ""


def xml_text(daten: bytes) -> str:
    try:
        return daten.decode("utf-8", errors="ignore")
    except Exception:  # pragma: no cover
        return ""


def _xml_datum(text: str) -> date | None:
    """Rechnungsdatum aus XRechnung (UBL/CII) bzw. ZUGFeRD-XML."""
    m = re.search(r"<(?:\w+:)?IssueDate>\s*(\d{4})-(\d{2})-(\d{2})", text)
    if m:
        return _gueltig(int(m[1]), int(m[2]), int(m[3]))
    m = re.search(
        r"<(?:\w+:)?IssueDateTime>\s*<(?:\w+:)?DateTimeString[^>]*>\s*(\d{4})(\d{2})(\d{2})",
        text,
    )
    if m:
        return _gueltig(int(m[1]), int(m[2]), int(m[3]))
    return None


def _zaehle(text: str, worte: list[str]) -> list[str]:
    return [w for w in worte if w in text]


def bewerte(
    dateiname: str,
    daten: bytes,
    betreff: str = "",
    mail_text: str = "",
    schwelle: int = 4,
) -> Ergebnis:
    """Bewertet einen Anhang und entscheidet, ob es eine Rechnung ist."""
    name = (dateiname or "").lower()
    gruende: list[str] = []
    punkte = 0

    if not name.endswith(RECHNUNGS_ENDUNGEN):
        return Ergebnis(False, 0, None, ["kein PDF/XML"])

    if name.endswith(".xml"):
        text = xml_text(daten)
        klein = text.lower()
        if "crossindustryinvoice" in klein or "<invoice" in klein or "urn:cen.eu:en16931" in klein:
            return Ergebnis(True, 10, _xml_datum(text), ["E-Rechnung (XRechnung/ZUGFeRD)"])
        return Ergebnis(False, 0, None, ["XML ohne Rechnungsformat"])

    text = pdf_text(daten)
    klein = text.lower()
    betreff_k = (betreff or "").lower()
    mail_k = (mail_text or "").lower()[:5000]

    treffer = _zaehle(name, STARKE_WORTE)
    if treffer:
        punkte += 4
        gruende.append(f"Dateiname: {', '.join(treffer)}")
    treffer = _zaehle(name, SCHWACHE_WORTE[:7])
    if treffer:
        punkte += 2
        gruende.append(f"Dateiname: {', '.join(treffer)}")

    treffer = _zaehle(betreff_k, STARKE_WORTE)
    if treffer:
        punkte += 2
        gruende.append(f"Betreff: {', '.join(treffer)}")
    treffer = _zaehle(betreff_k, SCHWACHE_WORTE[:9])
    if treffer:
        punkte += 1
        gruende.append(f"Betreff: {', '.join(treffer)}")

    if _zaehle(mail_k, STARKE_WORTE):
        punkte += 1
        gruende.append("E-Mail-Text erwähnt Rechnung")

    treffer = _zaehle(klein, STARKE_WORTE)
    if treffer:
        punkte += 3
        gruende.append(f"PDF-Text: {', '.join(treffer[:3])}")
    treffer = _zaehle(klein, SCHWACHE_WORTE)
    if len(treffer) >= 2:
        punkte += 2
        gruende.append(f"PDF-Text: {', '.join(treffer[:4])}")
    if re.search(r"\d+[.,]\d{2}\s*(€|eur)", klein) or re.search(r"(€|eur)\s*\d+[.,]\d{2}", klein):
        punkte += 1
        gruende.append("Geldbetrag gefunden")

    ausschluss = _zaehle(name, AUSSCHLUSS_WORTE)
    if ausschluss:
        punkte -= 6
        gruende.append(f"Ausschluss: {', '.join(ausschluss)}")

    datum = finde_rechnungsdatum(text)
    return Ergebnis(punkte >= schwelle, punkte, datum, gruende)
