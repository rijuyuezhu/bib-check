from __future__ import annotations

import logging
import re
import shutil
import subprocess
import traceback

import bibtexparser
import requests
from bibtexparser.model import Entry

from .ai import AIReviser
from .colors import (
    COLOR_BOLD,
    COLOR_CYAN,
    COLOR_DIM,
    COLOR_GREEN,
    COLOR_NORMAL,
    COLOR_PURPLE,
    COLOR_YELLOW,
)
from .config import Config
from .dblp import DblpSearch

logger = logging.getLogger("bib-check")


def _collapse_whitespace(text: str) -> str:
    """Replace multiple consecutive whitespace characters with a single space."""
    return re.sub(r"\s+", " ", text).strip()


def _has_fzf() -> bool:
    return shutil.which("fzf") is not None


def _fzf_select(hits: list[dict]) -> int | None:
    """Use fzf to select from DBLP hits. Returns index or None if cancelled."""
    lines = []
    for i, hit in enumerate(hits):
        authors = "; ".join(_collapse_whitespace(a) for a in hit["authors"])
        line = f"{i}: {_collapse_whitespace(hit['title'])} | {authors}, {hit['year']}, {_collapse_whitespace(hit['venue'])}"
        lines.append(line)
    input_text = "\n".join(lines)
    try:
        result = subprocess.run(
            [
                "fzf",
                "--ansi",
                "--no-multi",
                "--prompt",
                "Select DBLP hit> ",
                "--height",
                "~40%",
                "--reverse",
            ],
            input=input_text,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None
        selected = result.stdout.strip()
        if selected and ":" in selected:
            idx_str = selected.split(":")[0]
            if idx_str.isdigit():
                return int(idx_str)
    except Exception:
        pass
    return None


def _fallback_select(hits: list[dict]) -> int | None:
    """Styled fallback selection without fzf. Returns index or None to skip."""
    print(f"\n  {COLOR_BOLD}Select a DBLP hit:{COLOR_NORMAL}\n")
    for i, hit in enumerate(hits):
        print(
            f"  {COLOR_YELLOW}{i:>3}{COLOR_NORMAL}  "
            f"{COLOR_CYAN}{_collapse_whitespace(hit['title'])}{COLOR_NORMAL}"
        )
        print(
            f"       {COLOR_PURPLE}{'; '.join(_collapse_whitespace(a) for a in hit['authors'])}{COLOR_NORMAL}, "
            f"{hit['year']}, {COLOR_DIM}{_collapse_whitespace(hit['venue'])}{COLOR_NORMAL}"
        )
    print()
    while True:
        choice = input(
            f"  {COLOR_GREEN}Enter choice (0-{len(hits) - 1}), or 's' to skip: {COLOR_NORMAL}"
        )
        if choice.strip().lower() == "s":
            return None
        if choice.isdigit() and 0 <= int(choice) < len(hits):
            return int(choice)
        print(f"  {COLOR_YELLOW}Invalid choice, try again{COLOR_NORMAL}")


class BibConverter:
    def __init__(
        self,
        config: Config,
        ai_reviser: AIReviser | None = None,
    ):
        self.config = config
        self.ai_reviser = ai_reviser
        self.suppress_type = config.suppress_type
        self.dblp = DblpSearch(config.dblp_site)

    def _dblp_select(self, hits: list[dict]) -> int | None:
        """Interactive selection from DBLP hits. Uses fzf if available."""
        if _has_fzf():
            return _fzf_select(hits)
        return _fallback_select(hits)

    def check_dblp(self, entry: Entry) -> None:
        if "title" not in entry:
            logger.warning("Missing title in entry @ key %s", entry.key)
            return
        hits = self.dblp.search(entry["title"])

        if len(hits) == 0:
            logger.warning("No hits in DBLP @ key %s", entry.key)
            return

        if len(hits) == 1:
            idx = 0
        else:
            print(
                f"\nMultiple hits for {COLOR_GREEN}{_collapse_whitespace(entry['title'])}{COLOR_NORMAL} in DBLP"
            )
            print(
                f"Origin authors: {COLOR_GREEN}{_collapse_whitespace(entry['author'][:40])}{COLOR_NORMAL}, "
                f"year: {entry['year']}"
            )
            idx = self._dblp_select(hits)
            if idx is None:
                return

        bibcontent = requests.get(hits[idx]["bibtex"]).text
        lib = bibtexparser.parse_string(bibcontent)
        if len(lib.entries) != 1:
            logger.warning("Failed to parse bibtex from DBLP @ key %s", entry.key)
            return
        downloaded_entry = lib.entries[0]
        entry.fields = downloaded_entry.fields
        entry.entry_type = downloaded_entry.entry_type

    def ai_revise_entry(self, entry: Entry) -> None:
        if not self.ai_reviser:
            return
        if entry.entry_type == "article":
            for key in ("title", "journal"):
                if key in entry:
                    field = entry.fields_dict[key]
                    if key == "title":
                        field.value = self.ai_reviser.revise_title(field.value)
                    elif key == "journal":
                        field.value = self.ai_reviser.revise_journal(field.value)
        elif entry.entry_type == "inproceedings":
            for key in ("title", "booktitle"):
                if key in entry:
                    field = entry.fields_dict[key]
                    if key == "title":
                        field.value = self.ai_reviser.revise_title(field.value)
                    elif key == "booktitle":
                        field.value = self.ai_reviser.revise_inproceedings(field.value)

    def format_entry(self, entry: Entry) -> None:
        if entry.entry_type == "article":
            required = ["title", "author", "journal", "year"]
        elif entry.entry_type == "inproceedings":
            required = ["title", "author", "booktitle", "year", "pages"]
        else:
            if not self.suppress_type:
                logger.warning(
                    "Manually check bibentry of type %s @ key %s",
                    entry.entry_type,
                    entry.key,
                )
            return
        fields = []
        for key in required:
            if key not in entry:
                logger.warning("Missing `%s` in entry @ key %s", key, entry.key)
                continue
            fields.append(entry.fields_dict[key])
        entry.fields = fields

    def process_entry(
        self, entry: Entry, use_dblp: bool = False, use_ai: bool = False
    ) -> None:
        try:
            if use_dblp and entry.entry_type in ("article", "inproceedings"):
                self.check_dblp(entry)
            if use_ai:
                self.ai_revise_entry(entry)
            self.format_entry(entry)
        except Exception as e:
            logger.warning("Failed to convert entry @ key %s: %s", entry.key, e)
            traceback.print_exc()

    @staticmethod
    def parse(bib_data: str) -> bibtexparser.Library:
        library = bibtexparser.parse_string(bib_data)
        if len(library.failed_blocks) != 0:
            for block in library.failed_blocks:
                logger.warning("Failed to parse block: %s", block.error)
        return library

    @staticmethod
    def write(library: bibtexparser.Library, output_path: str) -> None:
        bibtexparser.write_file(output_path, library)

    def convert(
        self,
        bib_data: str,
        output_path: str,
        use_dblp: bool = False,
        use_ai: bool = False,
    ) -> None:
        """Batch convert (legacy non-TUI mode)."""
        library = self.parse(bib_data)
        for entry in library.entries:
            self.process_entry(entry, use_dblp=use_dblp, use_ai=use_ai)
        self.write(library, output_path)
