from __future__ import annotations

import re
import shutil
import sys
import termios
import tty
from dataclasses import dataclass, field
from typing import Callable

from bibtexparser.model import Entry

from .colors import (
    BG_GREEN,
    BG_WHITE,
    COLOR_BLACK_FG,
    COLOR_BOLD,
    COLOR_CYAN,
    COLOR_CYAN_FG,
    COLOR_DIM,
    COLOR_GREEN,
    COLOR_NORMAL,
    COLOR_PURPLE,
    COLOR_RED,
    COLOR_YELLOW,
)


def _collapse_whitespace(text: str) -> str:
    """Replace multiple consecutive whitespace characters with a single space."""
    return re.sub(r"\s+", " ", text).strip()


def _get_key() -> str:
    """Read a single keypress (handles escape sequences)."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            ch2 = sys.stdin.read(1)
            if ch2 == "[":
                ch3 = sys.stdin.read(1)
                if ch3 == "A":
                    return "UP"
                elif ch3 == "B":
                    return "DOWN"
                elif ch3 == "H":
                    return "HOME"
                elif ch3 == "F":
                    return "END"
                elif ch3 == "1":
                    ch4 = sys.stdin.read(1)
                    if ch4 == "~":
                        return "HOME"
                elif ch3 == "4":
                    ch4 = sys.stdin.read(1)
                    if ch4 == "~":
                        return "END"
                return f"ESC[{ch3}"
            return "ESC"
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _clear_screen():
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()


def _move_cursor(row: int, col: int):
    sys.stdout.write(f"\033[{row};{col}H")
    sys.stdout.flush()


def _hide_cursor():
    sys.stdout.write("\033[?25l")
    sys.stdout.flush()


def _show_cursor():
    sys.stdout.write("\033[?25h")
    sys.stdout.flush()


def _truncate(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    return text[: width - 1] + "~"


@dataclass
class TUIState:
    entries: list[Entry]
    cursor: int = 0
    offset: int = 0
    selected: set[int] = field(default_factory=set)
    visual_mode: bool = False
    visual_anchor: int = 0
    verbose: bool = False
    status_msg: str = ""
    pending_g: bool = False


class TUI:
    """Vim-like TUI for browsing and selecting bib entries."""

    def __init__(self, entries: list[Entry], actions: dict[str, Action]):
        self.state = TUIState(entries=entries)
        self.actions = actions
        self.running = True

    def _term_size(self) -> tuple[int, int]:
        cols, rows = shutil.get_terminal_size((80, 24))
        return rows, cols

    def _entry_summary(self, entry: Entry, width: int) -> str:
        title = _collapse_whitespace(entry["title"]) if "title" in entry else "???"
        author = _collapse_whitespace(entry["author"]) if "author" in entry else "???"
        year = entry["year"] if "year" in entry else "?"
        summary = f"[{entry.entry_type}] {entry.key}: {title} ({author[:30]}, {year})"
        return _truncate(summary, width)

    def _entry_verbose_lines(self, entry: Entry, width: int) -> list[str]:
        """Generate verbose detail lines for an entry (shown below the summary)."""
        indent = "        "
        lines = []
        detail_fields = [
            ("title", "Title"),
            ("author", "Author"),
            ("journal", "Journal"),
            ("booktitle", "Booktitle"),
            ("year", "Year"),
            ("pages", "Pages"),
        ]
        for key, label in detail_fields:
            if key in entry:
                val = _collapse_whitespace(entry[key])
                line = f"{indent}{COLOR_PURPLE}{label:>10}{COLOR_NORMAL}: {val}"
                lines.append(_truncate(line, width))
        return lines

    def _visual_range(self) -> set[int]:
        if not self.state.visual_mode:
            return set()
        a = self.state.visual_anchor
        b = self.state.cursor
        lo, hi = min(a, b), max(a, b)
        return set(range(lo, hi + 1))

    def _draw(self):
        rows, cols = self._term_size()
        header_lines = 1
        footer_lines = 2
        list_height = rows - header_lines - footer_lines
        if list_height < 1:
            list_height = 1

        st = self.state
        n = len(st.entries)

        # Calculate how many extra lines the verbose cursor takes
        verbose_extra = 0
        if st.verbose and 0 <= st.cursor < n:
            verbose_extra = len(self._entry_verbose_lines(st.entries[st.cursor], cols))

        # Adjust offset so cursor (including verbose lines) is visible
        if st.cursor < st.offset:
            st.offset = st.cursor
        # Ensure cursor entry + its verbose lines fit in view
        # Count display lines from offset to cursor (inclusive)
        while True:
            used = 0
            for idx in range(st.offset, st.cursor + 1):
                used += 1
                if st.verbose and idx == st.cursor:
                    used += verbose_extra
            if used <= list_height:
                break
            st.offset += 1

        _clear_screen()

        # Header
        mode_str = (
            f" {COLOR_RED}-- VISUAL LINE --{COLOR_NORMAL}" if st.visual_mode else ""
        )
        verbose_str = f" {COLOR_CYAN}[VERBOSE]{COLOR_NORMAL}" if st.verbose else ""
        sel_count = len(st.selected | self._visual_range())
        header = f"{COLOR_BOLD} bib-check TUI{COLOR_NORMAL}  {n} entries, {sel_count} selected{mode_str}{verbose_str}"
        _move_cursor(1, 1)
        sys.stdout.write(header[:cols])

        # Entry list
        vis_range = self._visual_range()
        row = header_lines + 1
        idx = st.offset
        while row <= header_lines + list_height and idx < n:
            is_cursor = idx == st.cursor
            is_selected = idx in st.selected or idx in vis_range

            marker = "*" if is_selected else " "
            line_num = f"{idx + 1:>4}"
            summary = self._entry_summary(st.entries[idx], cols - 8)
            text = f" {marker} {line_num} {summary}"
            text = text.ljust(cols)

            _move_cursor(row, 1)
            if is_cursor and is_selected:
                sys.stdout.write(f"{BG_GREEN}{COLOR_BLACK_FG}{text}{COLOR_NORMAL}")
            elif is_cursor:
                sys.stdout.write(f"{BG_WHITE}{COLOR_CYAN_FG}{text}{COLOR_NORMAL}")
            elif is_selected:
                sys.stdout.write(f"{COLOR_GREEN}{text}{COLOR_NORMAL}")
            else:
                sys.stdout.write(
                    f" {marker} {COLOR_DIM}{line_num}{COLOR_NORMAL} {summary}"
                )
            row += 1

            # Verbose detail lines for cursor entry
            if is_cursor and st.verbose:
                for vline in self._entry_verbose_lines(st.entries[idx], cols):
                    if row > header_lines + list_height:
                        break
                    _move_cursor(row, 1)
                    sys.stdout.write(vline)
                    row += 1

            idx += 1

        # Clear remaining lines
        while row <= header_lines + list_height:
            _move_cursor(row, 1)
            sys.stdout.write(" " * cols)
            row += 1

        # Footer: status bar
        _move_cursor(rows - 1, 1)
        status = st.status_msg or ""
        sys.stdout.write(f"{COLOR_YELLOW}{_truncate(status, cols)}{COLOR_NORMAL}")

        # Footer: key hints
        _move_cursor(rows, 1)
        hints = (
            " h:help  q:quit  space:select  v:verbose  enter:run action on selected "
        )
        sys.stdout.write(f"{COLOR_DIM}{_truncate(hints, cols)}{COLOR_NORMAL}")

        sys.stdout.flush()

    def _show_help(self):
        rows, cols = self._term_size()
        _clear_screen()
        _move_cursor(1, 1)
        help_text = [
            f"{COLOR_BOLD}=== Help ==={COLOR_NORMAL}",
            "",
            f"  {COLOR_CYAN}Navigation{COLOR_NORMAL}",
            "    j / DOWN    Move down",
            "    k / UP      Move up",
            "    gg / HOME   Go to first entry",
            "    G / END     Go to last entry",
            "",
            f"  {COLOR_CYAN}Selection{COLOR_NORMAL}",
            "    SPACE       Toggle selection on current entry",
            "    V           Toggle visual-line mode (select range with j/k)",
            "    a           Select all",
            "    A           Deselect all",
            "",
            f"  {COLOR_CYAN}Actions{COLOR_NORMAL}",
        ]
        for key, action in self.actions.items():
            help_text.append(f"    {key:<12}{action.description}")
        help_text += [
            "",
            f"  {COLOR_CYAN}Other{COLOR_NORMAL}",
            "    v           Toggle verbose mode (expand current entry)",
            "    i           View full entry detail",
            "    h           Show this help",
            "    q / Ctrl-C  Quit",
            "",
            f"  {COLOR_DIM}Press any key to return...{COLOR_NORMAL}",
        ]
        for i, line in enumerate(help_text):
            if i + 1 > rows:
                break
            _move_cursor(i + 1, 1)
            sys.stdout.write(_truncate(line, cols))
        sys.stdout.flush()
        _get_key()

    def _show_entry_detail(self, idx: int):
        """Show full detail of an entry."""
        rows, cols = self._term_size()
        entry = self.state.entries[idx]
        _clear_screen()
        _move_cursor(1, 1)
        lines = [
            f"{COLOR_BOLD}=== Entry Detail: {entry.key} ==={COLOR_NORMAL}",
            f"  Type: {COLOR_CYAN}{entry.entry_type}{COLOR_NORMAL}",
        ]
        for f in entry.fields:
            val = _collapse_whitespace(f.value)
            lines.append(f"  {COLOR_PURPLE}{f.key}{COLOR_NORMAL} = {val}")
        lines += [
            "",
            f"  {COLOR_DIM}Press any key to return...{COLOR_NORMAL}",
        ]
        for i, line in enumerate(lines):
            if i + 1 > rows:
                break
            _move_cursor(i + 1, 1)
            sys.stdout.write(_truncate(line, cols))
        sys.stdout.flush()
        _get_key()

    def _apply_visual_selection(self):
        """Merge visual range into selected set and exit visual mode."""
        if self.state.visual_mode:
            self.state.selected ^= self._visual_range()
            self.state.visual_mode = False

    def _get_selected_indices(self) -> list[int]:
        """Get sorted list of selected indices, or just cursor if none selected."""
        sel = self.state.selected | self._visual_range()
        if not sel:
            return [self.state.cursor]
        return sorted(sel)

    def run(self) -> list[int]:
        """Run the TUI and return indices of selected entries."""
        _hide_cursor()
        try:
            while self.running:
                self._draw()
                key = _get_key()
                self._handle_key(key)
        except KeyboardInterrupt:
            pass
        finally:
            _show_cursor()
            _clear_screen()
        return sorted(self.state.selected)

    def _handle_key(self, key: str):
        st = self.state
        n = len(st.entries)
        if n == 0:
            if key in ("q", "\x03"):
                self.running = False
            return

        st.status_msg = ""

        # Handle pending 'g' for 'gg'
        if st.pending_g:
            st.pending_g = False
            if key == "g":
                st.cursor = 0
                return
            # If not 'g', fall through to normal handling

        if key in ("j", "DOWN"):
            if st.cursor < n - 1:
                st.cursor += 1

        elif key in ("k", "UP"):
            if st.cursor > 0:
                st.cursor -= 1

        elif key == "g":
            st.pending_g = True

        elif key in ("G", "END"):
            st.cursor = n - 1

        elif key in ("HOME",):
            st.cursor = 0

        elif key == " ":
            if st.visual_mode:
                self._apply_visual_selection()
            else:
                if st.cursor in st.selected:
                    st.selected.discard(st.cursor)
                else:
                    st.selected.add(st.cursor)
                if st.cursor < n - 1:
                    st.cursor += 1

        elif key == "V":
            if st.visual_mode:
                self._apply_visual_selection()
            else:
                st.visual_mode = True
                st.visual_anchor = st.cursor

        elif key == "\x1b" or key == "ESC":
            if st.visual_mode:
                st.visual_mode = False
            else:
                st.selected.clear()
                st.status_msg = "Selection cleared"

        elif key == "a":
            st.selected = set(range(n))
            st.status_msg = "All selected"

        elif key == "A":
            st.selected.clear()
            st.status_msg = "All deselected"

        elif key == "v":
            st.verbose = not st.verbose

        elif key == "i":
            self._show_entry_detail(st.cursor)

        elif key == "h":
            self._show_help()

        elif key in ("q", "\x03"):
            self._apply_visual_selection()
            self.running = False

        elif key == "\r":
            # Enter: prompt user to pick an action on selected entries
            self._apply_visual_selection()
            indices = self._get_selected_indices()
            _show_cursor()
            _clear_screen()
            _move_cursor(1, 1)
            sys.stdout.write(
                f"{COLOR_BOLD}Run action on {len(indices)} entries:{COLOR_NORMAL}\n\n"
            )
            for akey, action in self.actions.items():
                sys.stdout.write(
                    f"  {COLOR_CYAN}{akey}{COLOR_NORMAL}  {action.description}\n"
                )
            sys.stdout.write(
                f"\n  {COLOR_DIM}Press action key, or any other key to cancel...{COLOR_NORMAL}\n"
            )
            sys.stdout.flush()
            choice = _get_key()
            if choice in self.actions:
                _clear_screen()
                self.actions[choice].callback(indices)
                st.status_msg = f"Action '{self.actions[choice].description}' done on {len(indices)} entries"
            else:
                st.status_msg = "Cancelled"
            _hide_cursor()

        elif key in self.actions:
            self._apply_visual_selection()
            indices = self._get_selected_indices()
            action = self.actions[key]
            _show_cursor()
            _clear_screen()
            action.callback(indices)
            st.status_msg = (
                f"Action '{action.description}' done on {len(indices)} entries"
            )
            _hide_cursor()

        else:
            st.status_msg = f"Unknown key: {repr(key)}"


@dataclass
class Action:
    key: str
    description: str
    callback: Callable[[list[int]], None]
