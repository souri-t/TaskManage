#!/usr/bin/env python3
"""Validate Redmine configuration required by the review-finding skill."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from redmine_common import (
    RedmineClient,
    ReviewFindingError,
    load_config,
    resolve_setup,
    validate_config,
)


def main() -> int:
    default_config = Path(__file__).resolve().parents[1] / "config" / "redmine.json"
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default=str(default_config),
        help="Redmine JSON configuration",
    )
    args = parser.parse_args()

    try:
        config = load_config(args.config)
        validate_config(config)
        client = RedmineClient.from_config(config)
        setup = resolve_setup(client, config)
        print(
            json.dumps(
                {
                    "status": "ok",
                    "project_id": setup.project_id,
                    "tracker_id": setup.tracker_id,
                    "warnings": setup.warnings,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except ReviewFindingError as exc:
        print(
            json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
