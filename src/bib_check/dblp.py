from __future__ import annotations

from urllib.parse import urlencode

import requests


def _ensure_list(x):
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]


class DblpSearch:
    # The following code in this class is adapted from
    # https://github.com/alumik/dblp-api/
    #
    # MIT License
    # Copyright (c) 2021,2023 Zhong Zhenyu
    DEFAULT_SITE = "https://dblp.uni-trier.de"

    def __init__(self, site: str = DEFAULT_SITE):
        self.base_url = f"{site.rstrip('/')}/search/publ/api"

    def search(self, query: str) -> list[dict]:
        results = []
        options = {"q": query, "format": "json", "h": 500}
        resp = requests.get(f"{self.base_url}?{urlencode(options)}")
        resp.raise_for_status()
        r = resp.json()
        hits = r.get("result", {}).get("hits", {}).get("hit")
        if hits is not None:
            for hit in _ensure_list(hits):
                if not isinstance(hit, dict):
                    continue
                info = hit.get("info") or {}
                url = info.get("url")
                if not url:
                    continue
                authors_info = info.get("authors") or {}
                authors = []
                for author in _ensure_list(authors_info.get("author"))[:2]:
                    if isinstance(author, dict) and author.get("text"):
                        authors.append(author["text"])
                entry = {
                    "title": info.get("title"),
                    "year": info.get("year"),
                    "venue": info.get("venue"),
                    "doi": info.get("doi"),
                    "url": info.get("ee"),
                    "authors": authors,
                    "bibtex": f"{url}.bib",
                }
                results.append(entry)
        return results
