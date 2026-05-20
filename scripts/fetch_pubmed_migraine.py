#!/usr/bin/env python3
"""Fetch PubMed migraine literature records for the medical workbench.

The script uses NCBI E-utilities without third-party dependencies:

1. ESearch retrieves PubMed IDs for a bounded query.
2. EFetch retrieves PubMed XML for those IDs.
3. Records are normalized into the JSON shape accepted by
   scripts/medical_migraine_workbench.py.

Keep usage polite. NCBI's ordinary unauthenticated limit is 3 requests/second;
this script makes only two requests per run by default.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable
from urllib import parse, request
import xml.etree.ElementTree as ET


EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
DEFAULT_QUERY = '(migraine[Title/Abstract]) AND (sleep OR caffeine OR stress OR hormones OR menstrual OR circadian)'

Fetcher = Callable[[str], bytes]


def _urlopen_fetch(url: str) -> bytes:
    req = request.Request(url, headers={"User-Agent": "medical-enoch-migraine-prototype/0.1"})
    with request.urlopen(req, timeout=30) as resp:  # noqa: S310 - fixed HTTPS NCBI endpoint
        return resp.read()


def _build_url(endpoint: str, params: dict[str, str | int]) -> str:
    return f"{EUTILS_BASE}/{endpoint}?{parse.urlencode(params)}"


def esearch_pmids(
    query: str,
    *,
    limit: int,
    api_key: str = "",
    email: str = "",
    tool: str = "medical_enoch_migraine_prototype",
    fetcher: Fetcher = _urlopen_fetch,
) -> list[str]:
    params: dict[str, str | int] = {
        "db": "pubmed",
        "term": query,
        "retmode": "json",
        "retmax": max(1, min(limit, 200)),
        "sort": "relevance",
        "tool": tool,
    }
    if api_key:
        params["api_key"] = api_key
    if email:
        params["email"] = email
    payload = json.loads(fetcher(_build_url("esearch.fcgi", params)).decode("utf-8"))
    ids = payload.get("esearchresult", {}).get("idlist", [])
    if not isinstance(ids, list):
        raise ValueError("NCBI ESearch response did not include an idlist")
    return [str(item) for item in ids if str(item).strip()]


def _text(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return " ".join("".join(node.itertext()).split())


def _article_year(article: ET.Element) -> str:
    for path in (
        "./MedlineCitation/Article/Journal/JournalIssue/PubDate/Year",
        "./MedlineCitation/Article/ArticleDate/Year",
        "./PubmedData/History/PubMedPubDate[@PubStatus='pubmed']/Year",
    ):
        text = _text(article.find(path))
        if text:
            return text
    return ""


def parse_pubmed_xml(xml_bytes: bytes) -> list[dict[str, str]]:
    root = ET.fromstring(xml_bytes)
    records: list[dict[str, str]] = []
    for article in root.findall(".//PubmedArticle"):
        pmid = _text(article.find("./MedlineCitation/PMID"))
        title = _text(article.find("./MedlineCitation/Article/ArticleTitle"))
        abstract_parts = article.findall("./MedlineCitation/Article/Abstract/AbstractText")
        abstract = " ".join(_text(part) for part in abstract_parts if _text(part))
        if not pmid or not title or not abstract:
            continue
        records.append(
            {
                "source_id": pmid,
                "source_kind": "pubmed",
                "title": title,
                "abstract": abstract,
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "year": _article_year(article),
            }
        )
    return records


def efetch_records(
    pmids: list[str],
    *,
    api_key: str = "",
    email: str = "",
    tool: str = "medical_enoch_migraine_prototype",
    fetcher: Fetcher = _urlopen_fetch,
) -> list[dict[str, str]]:
    if not pmids:
        return []
    params: dict[str, str | int] = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
        "tool": tool,
    }
    if api_key:
        params["api_key"] = api_key
    if email:
        params["email"] = email
    return parse_pubmed_xml(fetcher(_build_url("efetch.fcgi", params)))


def fetch_pubmed_records(
    *,
    query: str,
    limit: int,
    api_key: str = "",
    email: str = "",
    fetcher: Fetcher = _urlopen_fetch,
) -> list[dict[str, str]]:
    pmids = esearch_pmids(query, limit=limit, api_key=api_key, email=email, fetcher=fetcher)
    return efetch_records(pmids, api_key=api_key, email=email, fetcher=fetcher)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch PubMed migraine abstracts for Medical Enoch.")
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--output", required=True)
    parser.add_argument("--api-key", default="")
    parser.add_argument("--email", default="")
    args = parser.parse_args(argv)

    records = fetch_pubmed_records(
        query=args.query,
        limit=args.limit,
        api_key=args.api_key,
        email=args.email,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(records, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "records": len(records), "output": str(output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
