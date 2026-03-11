from __future__ import annotations

import argparse
import logging
import os

from .ai import AIReviser
from .colors import COLOR_GREEN, COLOR_NORMAL, COLOR_RED
from .config import Config
from .converter import BibConverter
from .tui import TUI, Action


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="bib-check", description="Automatically convert bibtex to a good-form one"
    )
    parser.add_argument("input_bib_file", type=str, help="Path to the input bib file")
    parser.add_argument(
        "output_bib_file", type=str, nargs="?", help="Path to the output bib file"
    )
    parser.add_argument(
        "--ai", action="store_true", help="Use AI to revise some entries"
    )
    parser.add_argument(
        "--ai-endpoint",
        type=str,
        default="https://api.deepseek.com/v1",
        help="AI API endpoint (default: https://api.deepseek.com/v1)",
    )
    parser.add_argument(
        "--ai-model",
        type=str,
        default="deepseek-chat",
        help="AI model name (default: deepseek-chat)",
    )
    parser.add_argument(
        "--ai-key-env",
        type=str,
        default="DEEPSEEK_API_KEY",
        help="Environment variable name containing the API key (default: DEEPSEEK_API_KEY)",
    )

    parser.add_argument(
        "--dblp", action="store_true", help="Convert the entry to one on DBLP"
    )
    parser.add_argument(
        "--dblp-site",
        type=str,
        default="https://dblp.uni-trier.de",
        help="DBLP mirror site (default: https://dblp.uni-trier.de)",
    )
    parser.add_argument(
        "--suppress-type",
        action="store_true",
        help="Suppress the error from unrecognized entry types",
    )
    parser.add_argument(
        "--tui",
        action="store_true",
        help="Use interactive TUI mode",
    )
    return parser.parse_args()


def _resolve_output(input_path: str, output_path: str | None) -> str:
    if output_path is not None:
        return output_path
    if input_path.endswith(".bib"):
        return input_path.replace(".bib", ".chk.bib")
    return input_path + ".chk.bib"


def _make_ai_reviser(config: Config) -> AIReviser | None:
    if not config.ai:
        return None
    api_key = os.environ.get(config.ai_key_env)
    if not api_key:
        raise ValueError(
            f"Environment variable '{config.ai_key_env}' not found or empty"
        )
    return AIReviser(
        config=config,
        api_key=api_key,
    )


def _print_log():
    try:
        with open("bib-check.log", "r") as f:
            log_data = f.read()
        if log_data.strip():
            print(
                f"\n{COLOR_RED}Issues found (also in ./bib-check.log):{COLOR_NORMAL}\n"
            )
            print(log_data)
        else:
            print(f"\n{COLOR_GREEN}No issues found.{COLOR_NORMAL}")
    except FileNotFoundError:
        pass


def _run_batch(config: Config):
    output_bib_file = _resolve_output(config.input_file, config.output_file)
    ai_reviser = _make_ai_reviser(config)
    converter = BibConverter(config=config, ai_reviser=ai_reviser)
    with open(config.input_file, "r") as f:
        bib_data = f.read()
    converter.convert(bib_data, output_bib_file, use_dblp=config.dblp, use_ai=config.ai)
    _print_log()


def _run_tui(config: Config):
    output_bib_file = _resolve_output(config.input_file, config.output_file)
    ai_reviser = _make_ai_reviser(config)
    converter = BibConverter(config=config, ai_reviser=ai_reviser)

    with open(config.input_file, "r") as f:
        bib_data = f.read()
    library = converter.parse(bib_data)
    entries = library.entries

    def action_dblp(indices: list[int]):
        for idx in indices:
            entry = entries[idx]
            print(f"DBLP search for: {entry.key}")
            try:
                converter.check_dblp(entry)
            except Exception as e:
                print(f"{COLOR_RED}DBLP search failed: {e}{COLOR_NORMAL}")
        input(f"\n{COLOR_GREEN}Press Enter to continue...{COLOR_NORMAL}")

    def action_ai(indices: list[int]):
        if not ai_reviser:
            print(f"{COLOR_RED}AI not configured. Use --ai flag.{COLOR_NORMAL}")
            input(f"\n{COLOR_GREEN}Press Enter to continue...{COLOR_NORMAL}")
            return
        for idx in indices:
            try:
                converter.ai_revise_entry(entries[idx])
            except Exception as e:
                print(
                    f"{COLOR_RED}AI revise failed for {entries[idx].key}: {e}{COLOR_NORMAL}"
                )
        input(f"\n{COLOR_GREEN}Press Enter to continue...{COLOR_NORMAL}")

    def action_format(indices: list[int]):
        for idx in indices:
            try:
                converter.format_entry(entries[idx])
            except Exception as e:
                print(
                    f"{COLOR_RED}Format failed for {entries[idx].key}: {e}{COLOR_NORMAL}"
                )
        print(f"Formatted {len(indices)} entries (stripped to required fields)")
        input(f"\n{COLOR_GREEN}Press Enter to continue...{COLOR_NORMAL}")

    def action_write(_indices: list[int]):
        converter.write(library, output_bib_file)
        print(f"Written to {COLOR_GREEN}{output_bib_file}{COLOR_NORMAL}")
        input(f"\n{COLOR_GREEN}Press Enter to continue...{COLOR_NORMAL}")

    actions = {
        "d": Action(
            key="d", description="DBLP search on selected", callback=action_dblp
        ),
        "r": Action(key="r", description="AI revise selected", callback=action_ai),
        "f": Action(
            key="f",
            description="Format selected (strip fields)",
            callback=action_format,
        ),
        "w": Action(key="w", description="Write output file", callback=action_write),
    }

    tui = TUI(entries, actions)
    tui.run()

    # Always write on exit
    converter.write(library, output_bib_file)
    _print_log()
    print(f"Output written to {COLOR_GREEN}{output_bib_file}{COLOR_NORMAL}")


def main() -> None:
    logging.basicConfig(
        level=getattr(
            logging, os.environ.get("LOGLEVEL", "INFO").upper(), logging.INFO
        ),
        filename="bib-check.log",
        filemode="w",
        format="%(message)s",
    )
    args = parse_args()
    config = Config.from_args(args)

    if args.tui:
        _run_tui(config)
    else:
        _run_batch(config)
