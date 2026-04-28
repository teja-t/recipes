"""Entry point + keyword CLI.

Usage:
    python main.py add "Karas Kustoms"
    python main.py remove "Tactile Turn"
    python main.py list

Polling loop wired up in Step 7.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

import yaml

from config import KEYWORDS_PATH


def _load(path: Path = KEYWORDS_PATH) -> List[str]:
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text()) or {}
    kws = data.get("keywords") or []
    return [str(k) for k in kws]


def _save(keywords: List[str], path: Path = KEYWORDS_PATH) -> None:
    path.write_text(yaml.safe_dump({"keywords": keywords}, sort_keys=False, allow_unicode=True))


def add_keyword(keyword: str) -> bool:
    keyword = keyword.strip()
    if not keyword:
        print("error: keyword is empty", file=sys.stderr)
        return False
    keywords = _load()
    if any(k.lower() == keyword.lower() for k in keywords):
        print(f"already present: {keyword}")
        return False
    keywords.append(keyword)
    _save(keywords)
    print(f"added: {keyword}")
    return True


def remove_keyword(keyword: str) -> bool:
    keywords = _load()
    match = next((k for k in keywords if k.lower() == keyword.lower()), None)
    if match is None:
        print(f"not found: {keyword}")
        return False
    keywords.remove(match)
    _save(keywords)
    print(f"removed: {match}")
    return True


def list_keywords() -> List[str]:
    keywords = _load()
    if not keywords:
        print("(no keywords)")
    else:
        for k in keywords:
            print(k)
    return keywords


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pen-hunter", description="Pen-hunter CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add", help="Add a keyword")
    p_add.add_argument("keyword")

    p_rm = sub.add_parser("remove", help="Remove a keyword")
    p_rm.add_argument("keyword")

    sub.add_parser("list", help="List keywords")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.cmd == "add":
        return 0 if add_keyword(args.keyword) else 1
    if args.cmd == "remove":
        return 0 if remove_keyword(args.keyword) else 1
    if args.cmd == "list":
        list_keywords()
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
