from __future__ import annotations

import argparse
from dataclasses import dataclass


@dataclass
class Config:
    """Configuration for the bib_check tool."""

    input_file: str
    output_file: str | None
    ai: bool
    ai_endpoint: str
    ai_model: str
    ai_key_env: str
    dblp: bool
    dblp_site: str
    suppress_type: bool

    @classmethod
    def from_args(cls, args: argparse.Namespace):
        return cls(
            input_file=args.input_bib_file,
            output_file=args.output_bib_file,
            ai=args.ai,
            ai_endpoint=args.ai_endpoint,
            ai_model=args.ai_model,
            ai_key_env=args.ai_key_env,
            dblp=args.dblp,
            dblp_site=args.dblp_site,
            suppress_type=args.suppress_type,
        )
