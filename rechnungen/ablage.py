"""Speichert Rechnungen und Avis sortiert nach Jahr/Monat und merkt sich Verarbeitetes."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import date
from pathlib import Path

from .erkennung import AVIS, MONATSNAMEN, RECHNUNG

# Unterordner je Dokumentart innerhalb des Monats
UNTERORDNER = {RECHNUNG: "Rechnungen", AVIS: "Avis"}


def sicherer_name(text: str, max_laenge: int = 60) -> str:
    text = re.sub(r"[\\/:*?\"<>|\r\n\t]+", "_", text or "").strip(" ._")
    text = re.sub(r"\s+", " ", text)
    return text[:max_laenge] or "unbenannt"


def monats_ordner(basis: Path, d: date) -> Path:
    return Path(basis) / f"{d.year}" / f"{d.month:02d}_{MONATSNAMEN[d.month - 1]}"


class Ablage:
    def __init__(self, basis: str | Path, zustand_datei: str | Path):
        self.basis = Path(basis)
        self.zustand_datei = Path(zustand_datei)
        self.basis.mkdir(parents=True, exist_ok=True)
        self._zustand = self._lade_zustand()

    # ---------- Zustand ----------
    def _lade_zustand(self) -> dict:
        if self.zustand_datei.exists():
            try:
                return json.loads(self.zustand_datei.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
        return {"mails": [], "hashes": [], "letzte_uid": {}}

    def speichere_zustand(self) -> None:
        self.zustand_datei.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.zustand_datei.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._zustand, indent=1), encoding="utf-8")
        tmp.replace(self.zustand_datei)

    def mail_bekannt(self, message_id: str) -> bool:
        return message_id in self._zustand["mails"]

    def mail_merken(self, message_id: str) -> None:
        if message_id and message_id not in self._zustand["mails"]:
            self._zustand["mails"].append(message_id)

    # ---------- Speichern ----------
    def speichern(
        self,
        daten: bytes,
        dateiname: str,
        rechnungsdatum: date,
        absender: str,
        betreff: str,
        art: str = RECHNUNG,
    ) -> Path | None:
        """Legt die Datei ab. Gibt None zurück, wenn sie schon vorhanden war."""
        pruefsumme = hashlib.sha256(daten).hexdigest()
        if pruefsumme in self._zustand["hashes"]:
            return None

        ordner = monats_ordner(self.basis, rechnungsdatum) / UNTERORDNER[art]
        ordner.mkdir(parents=True, exist_ok=True)
        stamm, punkt, endung = dateiname.rpartition(".")
        if not punkt:
            stamm, endung = dateiname, "pdf"
        name = (
            f"{rechnungsdatum.isoformat()}_{sicherer_name(absender, 30)}_"
            f"{sicherer_name(stamm, 50)}.{endung.lower()}"
        )
        ziel = ordner / name
        zaehler = 2
        while ziel.exists():
            ziel = ordner / f"{name.rsplit('.', 1)[0]}_{zaehler}.{endung.lower()}"
            zaehler += 1
        ziel.write_bytes(daten)

        self._zustand["hashes"].append(pruefsumme)
        self._index_eintrag(ziel, rechnungsdatum, art, absender, betreff)
        return ziel

    def _index_eintrag(self, ziel: Path, d: date, art: str, absender: str, betreff: str) -> None:
        index = self.basis / "Rechnungsuebersicht.csv"
        neu = not index.exists()
        with index.open("a", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            if neu:
                w.writerow(["Datum", "Monat", "Art", "Absender", "Betreff", "Datei"])
            w.writerow([
                d.strftime("%d.%m.%Y"),
                f"{MONATSNAMEN[d.month - 1]} {d.year}",
                art,
                absender,
                betreff,
                str(ziel.relative_to(self.basis)),
            ])
