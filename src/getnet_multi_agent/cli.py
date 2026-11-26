"""Command line: token issuing, crawl refresh and ingestion."""

import argparse

from getnet_multi_agent.core.settings import get_settings


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="getnet")
    sub = p.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("token", help="print a signed JWT")
    t.add_argument("--sub", required=True)
    t.add_argument("--role", required=True, choices=["merchant", "operator"])
    t.add_argument("--ttl-minutes", type=int, default=60)
    r = sub.add_parser("refresh", help="crawl the knowledge sites")
    r.add_argument("--max-pages", type=int, default=None)
    i = sub.add_parser("ingest", help="chunk, embed and index the crawl")
    i.add_argument("--rebuild", action="store_true")
    args = p.parse_args(argv)
    settings = get_settings()

    if args.cmd == "token":
        from getnet_multi_agent.security.auth import issue_token

        print(issue_token(settings, args.sub, args.role, args.ttl_minutes))
    elif args.cmd == "refresh":
        from getnet_multi_agent.rag.crawler import refresh

        refresh(settings, args.max_pages)
    else:
        from getnet_multi_agent.core.llm import get_llm
        from getnet_multi_agent.rag.ingest import ingest

        ingest(settings, get_llm(settings), args.rebuild)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
