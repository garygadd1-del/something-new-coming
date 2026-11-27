"""Read-only SQLite FTS needle index.

Pointers cite path + title + a short snippet stored in the index. Source files
on disk are not opened. ``decide`` never writes the database. ``init_index``
is an explicit builder for tests and for an operator who already chose a path.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .textutil import coverage, evidence_thickness, fts_match, stem, strength, terms_of

# Trinary depth windows. Shallow is a thin slice; deep reads a wider set of hits.
DEPTH_WINDOWS = {
    "shallow": {"k": 1, "term_limit": 8, "snippet": 80, "breadth": 0.45},
    "mid": {"k": 3, "term_limit": 16, "snippet": 160, "breadth": 0.75},
    "deep": {"k": 6, "term_limit": 24, "snippet": 280, "breadth": 1.0},
}


@dataclass(frozen=True)
class Pointer:
    path: str
    title: str
    snippet: str
    confidence: float
    source: str = "knowledge"
    lines: tuple[int, int] | None = None

    def as_dict(self):
        return {
            "path": self.path,
            "title": self.title,
            "snippet": self.snippet,
            "confidence": self.confidence,
            "source": self.source,
            "lines": list(self.lines) if self.lines else None,
        }


class NeedleIndex:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)

    def available(self) -> bool:
        return Path(self.db_path).is_file()

    def _connect(self):
        uri = Path(self.db_path).resolve().as_uri() + "?mode=ro"
        return sqlite3.connect(uri, uri=True)

    def search(self, query: str, depth: str) -> dict:
        window = DEPTH_WINDOWS[depth]
        terms = terms_of(query, window["term_limit"])
        info = {"terms": terms, "depth": depth, "hits": 0}
        if not self.available() or not terms:
            return {"thickness": 0.0, "pointers": (), "terms": terms, "info": info}
        match = fts_match(terms)
        try:
            con = self._connect()
        except sqlite3.Error as exc:
            info["error"] = str(exc)[:160]
            return {"thickness": 0.0, "pointers": (), "terms": terms, "info": info}
        try:
            rows = con.execute(
                "select path, title, body, bm25(fts) as s from fts "
                "where fts match ? order by s limit ?",
                (match, window["k"]),
            ).fetchall()
        except sqlite3.Error as exc:
            info["error"] = str(exc)[:160]
            return {"thickness": 0.0, "pointers": (), "terms": terms, "info": info}
        finally:
            con.close()
        pointers = []
        best_cov = 0.0
        best_bm25 = None
        for path, title, body, score in rows:
            text = "%s\n%s\n%s" % (title or "", path or "", body or "")
            cov = coverage(terms, text)
            if cov > best_cov:
                best_cov = cov
            if best_bm25 is None or abs(score) > abs(best_bm25):
                best_bm25 = score
            snippet = _best_snippet(terms, body or title or "", window["snippet"])
            pointers.append(
                Pointer(
                    path=path or "",
                    title=title or "",
                    snippet=snippet,
                    confidence=round(cov, 3),
                    source="knowledge",
                )
            )
        info["hits"] = len(pointers)
        thick = evidence_thickness(
            best_cov,
            strength(best_bm25, len(terms)),
            len(pointers),
            window["k"],
            window["breadth"],
        )
        return {
            "thickness": round(thick, 3),
            "pointers": tuple(pointers),
            "terms": terms,
            "info": info,
        }


def _best_snippet(terms, text, max_chars):
    best, best_score = "", -1
    for line in (text or "").splitlines() or [text or ""]:
        score = sum(1 for t in terms if stem(t) in line.lower())
        if score > best_score and line.strip():
            best, best_score = line.strip(), score
    best = " ".join(best.split())
    if len(best) > max_chars:
        return best[:max_chars] + "..."
    return best


def init_index(path: str | Path, documents: list[dict]) -> None:
    """Create or replace an FTS index. Not called by the router."""
    target = Path(path)
    if target.exists():
        target.unlink()
    con = sqlite3.connect(str(target))
    try:
        con.execute("create virtual table fts using fts5(path, title, body)")
        for doc in documents:
            con.execute(
                "insert into fts(path, title, body) values (?, ?, ?)",
                (str(doc.get("path") or ""), str(doc.get("title") or ""), str(doc.get("body") or "")),
            )
        con.commit()
    finally:
        con.close()
