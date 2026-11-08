"""Konfiguration laden/speichern und IMAP-Server anhand der E-Mail-Adresse erkennen."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Bekannte Anbieter: Domain -> IMAP-Server
IMAP_SERVER = {
    "gmail.com": "imap.gmail.com",
    "googlemail.com": "imap.gmail.com",
    "outlook.com": "outlook.office365.com",
    "outlook.de": "outlook.office365.com",
    "hotmail.com": "outlook.office365.com",
    "hotmail.de": "outlook.office365.com",
    "live.com": "outlook.office365.com",
    "live.de": "outlook.office365.com",
    "gmx.de": "imap.gmx.net",
    "gmx.net": "imap.gmx.net",
    "gmx.at": "imap.gmx.net",
    "gmx.ch": "imap.gmx.net",
    "web.de": "imap.web.de",
    "t-online.de": "secureimap.t-online.de",
    "freenet.de": "mx.freenet.de",
    "yahoo.com": "imap.mail.yahoo.com",
    "yahoo.de": "imap.mail.yahoo.com",
    "icloud.com": "imap.mail.me.com",
    "me.com": "imap.mail.me.com",
    "mail.de": "imap.mail.de",
    "posteo.de": "posteo.de",
    "mailbox.org": "imap.mailbox.org",
    "ionos.de": "imap.ionos.de",
    "1und1.de": "imap.1und1.de",
    "strato.de": "imap.strato.de",
}

STANDARD_KONFIG_DATEI = Path.home() / ".rechnungen" / "config.json"


def imap_server_fuer(email_adresse: str) -> str | None:
    """Liefert den IMAP-Server für bekannte Anbieter, sonst None."""
    if "@" not in email_adresse:
        return None
    domain = email_adresse.rsplit("@", 1)[1].strip().lower()
    return IMAP_SERVER.get(domain)


@dataclass
class Konfig:
    email: str = ""
    imap_server: str = ""
    imap_port: int = 993
    ordner: list[str] = field(default_factory=lambda: ["INBOX"])
    ziel_ordner: str = str(Path.home() / "Rechnungen")
    # Beim ersten Lauf nur E-Mails der letzten N Tage durchsuchen
    tage_zurueck: int = 365
    # Abstand im Dauerbetrieb (Minuten)
    intervall_minuten: int = 15
    # Passwort nur speichern, wenn ausdrücklich gewünscht (Klartext!)
    passwort: str = ""

    @classmethod
    def laden(cls, pfad: Path) -> "Konfig":
        daten = json.loads(Path(pfad).read_text(encoding="utf-8"))
        bekannte = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in daten.items() if k in bekannte})

    def speichern(self, pfad: Path) -> None:
        pfad = Path(pfad)
        pfad.parent.mkdir(parents=True, exist_ok=True)
        pfad.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
        try:
            os.chmod(pfad, 0o600)
        except OSError:
            pass

    @property
    def zustand_datei(self) -> Path:
        return Path(self.ziel_ordner) / ".verarbeitet.json"
