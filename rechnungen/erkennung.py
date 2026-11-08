"""Erkennt Rechnungen und Avis (Zahlungsavis) und ermittelt deren Datum.

Andere Dokumente wie Auftragsbestätigungen, Lieferscheine oder Angebote
werden bewusst aussortiert.
"""

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

RECHNUNGS_ENDUNGEN = (".pdf", ".xml")

# Label vor dem Datum, das auf das Rechnungsdatum hinweist
_DATUM_LABEL = (
    r"(?:rechnungsdatum|rechnungs-datum|belegdatum|invoice date|date of issue|"
    r"datum der rechnung|ausstellungsdatum|avisdatum|zahlungsdatum|ausführungsdatum|"
    r"leistungsdatum|datum|date)"
)
_DATUM_NUM = r"(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})"
_DATUM_ISO = r"(\d{4})-(\d{2})-(\d{2})"
_DATUM_TEXT = r"(\d{1,2})\.?\s+([a-zäöü]{3,9})\.?\s+(\d{4})"
_DATUM_TEXT_EN = r"([a-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})"


RECHNUNG = "Rechnung"
AVIS = "Avis"


@dataclass
class Ergebnis:
    art: str | None  # RECHNUNG, AVIS oder None (= nicht archivieren)
    datum: date | None
    gruende: list[str]

    @property
    def archivieren(self) -> bool:
        return self.art is not None


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
    """Ermittelt das Belegdatum aus dem Text einer Rechnung bzw. eines Avis.

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


# ---------------------------------------------------------------- Dokumentart
# Alle Muster arbeiten auf normalisiertem Text (klein, ä->ae, ö->oe, ü->ue, ß->ss).

# Eindeutig Avis (Zahlungsavis / Zahlungsanzeige)
AVIS_MUSTER = [
    r"zahlungsavis", r"ueberweisungsavis", r"gutschriftsavis", r"zahlungs-avis",
    r"\bavis\b", r"remittance advice", r"payment advice", r"zahlungsanzeige",
    r"zahlungsankuendigung", r"zahlungsbenachrichtigung", r"payment notification",
    r"\bavis[-_ ]?\d",
]
# Felder, die nur auf Rechnungen vorkommen
RECHNUNG_FELDER = [
    r"rechnungsnummer", r"rechnungs-nr", r"rechnungsnr", r"rechnungs-nummer",
    r"rechnungsdatum", r"rechnungs-datum", r"invoice number", r"invoice no",
    r"invoice date", r"invoice #", r"\bre[-_ ]?nr\b",
]
# Titel, der auf eine Rechnung hinweist
RECHNUNG_TITEL = [
    r"\brechnung\b", r"\binvoice\b", r"\bfaktura\b", r"\bgutschrift\b",
    r"\bschlussrechnung\b", r"\babschlagsrechnung\b", r"\bteilrechnung\b",
    r"\bsammelrechnung\b", r"\bkorrekturrechnung\b", r"\bstornorechnung\b",
    r"\bxrechnung\b", r"\bzugferd\b", r"\btax invoice\b",
]
# Dokumente, die NICHT archiviert werden sollen
AUSSCHLUSS_MUSTER = [
    r"auftragsbestaetigung", r"auftrags-bestaetigung", r"bestellbestaetigung",
    r"bestellungsbestaetigung", r"order confirmation", r"order acknowledg",
    r"bestelluebersicht", r"\bbestellung\b", r"purchase order",
    r"lieferschein", r"delivery note", r"packing slip", r"packzettel",
    r"versandbestaetigung", r"versandavis", r"lieferavis", r"shipping confirmation",
    r"\bangebot\b", r"kostenvoranschlag", r"\bquotation\b", r"\bquote\b",
    r"proforma", r"pro-forma", r"pro forma",
    r"\bmahnung\b", r"zahlungserinnerung", r"payment reminder",
    r"allgemeine geschaeftsbedingungen", r"\bagb\b", r"datenschutz",
    r"widerruf", r"newsletter", r"terms and conditions", r"privacy policy",
]
# Diese Dokumente enthalten oft eine Rechnungsnummer, sind aber trotzdem keine Rechnung
HARTER_AUSSCHLUSS = [
    r"\bmahnung\b", r"zahlungserinnerung", r"payment reminder",
    r"proforma", r"pro-forma", r"pro forma",
]
# Typische Überschriften anderer Dokumente
TITEL_AUSSCHLUSS = [
    r"auftragsbestaetigung", r"bestellbestaetigung", r"order confirmation",
    r"lieferschein", r"delivery note", r"\bangebot\b", r"kostenvoranschlag",
]
# Kürzel in Dateinamen, z. B. "AB_4711.pdf" oder "LS-123.pdf"
DATEINAME_AUSSCHLUSS = [r"(^|[^a-z])(ab|ls|ang)[-_ ]?\d"]
DATEINAME_RECHNUNG = [r"(^|[^a-z])(re|rg|rn|inv)[-_ ]?\d"]

# Verweise wie "Lieferschein-Nr. 123" auf einer Rechnung sind kein Titel
_VERWEIS = r"\s*[-.:]?\s*(nr\b|nummer|no\b|datum|vom\b)"


def normalisiere(text: str) -> str:
    text = (text or "").lower()
    for alt, neu in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(alt, neu)
    return re.sub(r"[ \t]+", " ", text)


def _erste_stelle(text: str, muster: list[str], ohne_verweise: bool = False):
    """Position und Wort des ersten Treffers (oder None)."""
    beste = None
    for m in muster:
        for treffer in re.finditer(m, text):
            if ohne_verweise and re.match(_VERWEIS, text[treffer.end():]):
                continue
            if beste is None or treffer.start() < beste[0]:
                beste = (treffer.start(), treffer.group(0).strip(" -_"))
            break
    return beste


def _betrag_vorhanden(text: str) -> bool:
    return bool(
        re.search(r"\d[.,]\d{2}\s*(€|eur|euro)\b", text)
        or re.search(r"(€|eur)\s*\d", text)
        or re.search(r"\b(mwst|ust|umsatzsteuer|vat|netto|brutto|summe|total)\b", text)
    )


def klassifiziere_text(text: str, quelle: str) -> tuple[str | None, str | None]:
    """Bestimmt die Dokumentart eines Textes.

    Liefert (art, grund). art ist RECHNUNG, AVIS, "ausschluss" oder None (unklar).
    Es zählt, was zuerst im Dokument steht (meist die Überschrift).
    """
    t = normalisiere(text)
    if not t.strip():
        return None, None
    avis = _erste_stelle(t, AVIS_MUSTER)
    feld = _erste_stelle(t, RECHNUNG_FELDER)
    titel = _erste_stelle(t, RECHNUNG_TITEL)
    # Hat das Dokument echte Rechnungsfelder, sind "Lieferschein-Nr." usw. nur Verweise
    aus = _erste_stelle(t, AUSSCHLUSS_MUSTER, ohne_verweise=bool(feld))

    kandidaten = []
    if avis:
        kandidaten.append((avis[0], AVIS, avis[1]))
    if aus:
        kandidaten.append((aus[0], "ausschluss", aus[1]))
    rechnung = min([x for x in (feld, titel) if x], default=None)
    if rechnung:
        kandidaten.append((rechnung[0], RECHNUNG, rechnung[1]))
    if not kandidaten:
        return None, None

    pos, art, wort = min(kandidaten)
    # Rechnungsfelder sind sehr eindeutig: schlagen einen späteren Ausschluss,
    # aber nicht ein Avis (Avis listen bezahlte Rechnungsnummern auf).
    # Ausnahme: harte Ausschlüsse (Mahnung, Proforma) und Dokumente wie eine
    # Auftragsbestätigung, die nirgends "Rechnung" als Titel tragen.
    if (art == "ausschluss" and feld and not avis and quelle != "Dateiname"
            and not _erste_stelle(t, HARTER_AUSSCHLUSS)
            and (titel or not _erste_stelle(t, TITEL_AUSSCHLUSS, ohne_verweise=True))):
        art, wort = RECHNUNG, feld[1]
    # Nur das Wort "Rechnung" in einem Fließtext ohne Beträge reicht nicht
    if art == RECHNUNG and not feld and quelle == "PDF" and not _betrag_vorhanden(t):
        return None, None
    return art, f"{quelle}: „{wort}“"


def _klassifiziere_dateiname(name: str) -> tuple[str | None, str | None]:
    n = normalisiere(name)
    # "Rechnung4711" -> "rechnung 4711", Trennzeichen zu Leerzeichen
    lesbar = re.sub(r"(?<=[a-z])(?=\d)|(?<=\d)(?=[a-z])", " ", re.sub(r"[_.]", " ", n))
    art, grund = klassifiziere_text(lesbar, "Dateiname")
    if art:
        return art, grund
    if "rechnung" in n or "invoice" in n:
        return RECHNUNG, "Dateiname: „rechnung“"
    if _erste_stelle(n, DATEINAME_AUSSCHLUSS):
        return "ausschluss", "Dateiname: Kürzel AB/LS"
    if _erste_stelle(n, DATEINAME_RECHNUNG):
        return RECHNUNG, "Dateiname: Kürzel RE"
    return None, None


def bewerte(
    dateiname: str,
    daten: bytes,
    betreff: str = "",
    mail_text: str = "",
) -> Ergebnis:
    """Entscheidet, ob ein Anhang eine Rechnung, ein Avis oder etwas anderes ist.

    Reihenfolge: Inhalt des PDFs > Dateiname > Betreff der E-Mail.
    """
    name = (dateiname or "").lower()
    if not name.endswith(RECHNUNGS_ENDUNGEN):
        return Ergebnis(None, None, ["kein PDF/XML"])

    if name.endswith(".xml"):
        text = xml_text(daten)
        klein = text.lower()
        if "crossindustryinvoice" in klein or "<invoice" in klein or "urn:cen.eu:en16931" in klein:
            return Ergebnis(RECHNUNG, _xml_datum(text), ["E-Rechnung (XRechnung/ZUGFeRD)"])
        if "remittanceadvice" in klein:
            return Ergebnis(AVIS, None, ["Avis (XML)"])
        return Ergebnis(None, None, ["XML ohne Rechnungsformat"])

    text = pdf_text(daten)
    gruende: list[str] = []
    stufen = [
        klassifiziere_text(text, "PDF"),
        _klassifiziere_dateiname(dateiname),
        klassifiziere_text(betreff, "Betreff"),
    ]
    art = None
    for stufen_art, grund in stufen:
        if stufen_art:
            art = stufen_art
            gruende.append(grund)
            break
    if art is None:
        gruende.append("weder Rechnung noch Avis erkennbar")
    if art == "ausschluss":
        gruende.append("kein Rechnung/Avis – wird nicht archiviert")
        art = None
    datum = finde_rechnungsdatum(text) if art else None
    return Ergebnis(art, datum, gruende)


def bewerte_mailtext(betreff: str, mail_text: str) -> Ergebnis:
    """Für E-Mails ohne passenden Anhang: ist die E-Mail selbst ein Avis?"""
    art, grund = klassifiziere_text(betreff, "Betreff")
    if art != AVIS:
        art2, grund2 = klassifiziere_text(mail_text[:3000], "E-Mail-Text")
        if art is None and art2 == AVIS:
            art, grund = art2, grund2
    if art != AVIS:
        return Ergebnis(None, None, [])
    return Ergebnis(AVIS, finde_rechnungsdatum(mail_text), [grund])
