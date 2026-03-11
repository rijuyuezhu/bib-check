from __future__ import annotations

from urllib.parse import urlencode

import requests


def _ensure_list(x):
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
            for hit in hits:
                info = hit.get("info")
                entry = {
                    "title": info.get("title"),
                    "year": info.get("year"),
                    "venue": info.get("venue"),
                    "doi": info.get("doi"),
                    "url": info.get("ee"),
                    "authors": [
                        x.get("text")
                        for x in _ensure_list(info.get("authors").get("author"))[:2]
                    ],
                    "bibtex": f"{info.get('url')}.bib",
                }
                results.append(entry)
        return results
