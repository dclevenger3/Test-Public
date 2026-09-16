"""Fetch the text behind attached notes: Google Docs/Slides, PDFs, Canvas pages, plain web pages."""

from __future__ import annotations

import io
import re

from playwright.sync_api import BrowserContext

from .models import Material

GOOGLE_DOC = re.compile(r"docs\.google\.com/document/d/([\w-]+)")
GOOGLE_SLIDES = re.compile(r"docs\.google\.com/presentation/d/([\w-]+)")
GOOGLE_DRIVE_FILE = re.compile(r"drive\.google\.com/file/d/([\w-]+)")
MAX_CHARS = 60_000


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n".join((p.extract_text() or "") for p in reader.pages)


def _html_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|nav|footer).*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    return re.sub(r"[ \t]+\n?", " ", text).strip()


def fetch_text(ctx: BrowserContext, material: Material) -> Material:
    """Fill material.text using the logged-in browser context. Never raises; leaves text empty."""
    url = material.url
    if not url or material.text:
        return material
    try:
        if m := GOOGLE_DOC.search(url):
            r = ctx.request.get(f"https://docs.google.com/document/d/{m.group(1)}/export?format=txt")
            material.kind, material.text = "doc", r.text()
        elif m := GOOGLE_SLIDES.search(url):
            r = ctx.request.get(f"https://docs.google.com/presentation/d/{m.group(1)}/export/txt")
            material.kind, material.text = "slides", r.text()
        elif m := GOOGLE_DRIVE_FILE.search(url):
            r = ctx.request.get(f"https://drive.google.com/uc?export=download&id={m.group(1)}")
            ctype = r.headers.get("content-type", "")
            if "pdf" in ctype:
                material.kind, material.text = "pdf", _pdf_text(r.body())
            else:
                material.kind, material.text = "page", _html_text(r.text())
        else:
            r = ctx.request.get(url)
            ctype = r.headers.get("content-type", "")
            if "pdf" in ctype or url.lower().endswith(".pdf"):
                material.kind, material.text = "pdf", _pdf_text(r.body())
            elif "html" in ctype or "text" in ctype:
                material.kind, material.text = "page", _html_text(r.text())
    except Exception as exc:  # network, auth, parse; the guide just goes without it
        material.text = ""
        material.kind = f"{material.kind} (fetch failed: {type(exc).__name__})"
    if len(material.text) > MAX_CHARS:
        material.text = material.text[:MAX_CHARS] + "\n[truncated]"
    return material


def looks_like_notes(title: str, url: str) -> bool:
    """Heuristic for which links are worth pulling as study material."""
    t = f"{title} {url}".lower()
    return any(k in t for k in ("docs.google", "presentation", "drive.google", ".pdf", "notes", "slides", "study", "review", "vocab", "/pages/", "/files/"))
