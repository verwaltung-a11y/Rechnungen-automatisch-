"""Erzeugt minimale PDFs mit Text für Tests (ohne zusätzliche Bibliotheken)."""


def mache_pdf(zeilen: list[str]) -> bytes:
    def esc(t: str) -> str:
        return t.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    inhalt = "BT /F1 11 Tf 50 780 Td 14 TL\n"
    for z in zeilen:
        inhalt += f"({esc(z)}) Tj T*\n"
    inhalt += "ET"
    strom = inhalt.encode("latin-1")
    objekte = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(strom)).encode() + b" >>\nstream\n" + strom + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    aus = b"%PDF-1.4\n"
    offsets = []
    for i, obj in enumerate(objekte, 1):
        offsets.append(len(aus))
        aus += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(aus)
    aus += f"xref\n0 {len(objekte) + 1}\n0000000000 65535 f \n".encode()
    for o in offsets:
        aus += f"{o:010d} 00000 n \n".encode()
    aus += f"trailer\n<< /Size {len(objekte) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    return aus
