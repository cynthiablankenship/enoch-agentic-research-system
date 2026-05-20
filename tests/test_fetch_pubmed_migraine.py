from __future__ import annotations

from scripts.fetch_pubmed_migraine import efetch_records, esearch_pmids, fetch_pubmed_records


ESEARCH_JSON = b'{"esearchresult":{"idlist":["111","222"]}}'
EFETCH_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>111</PMID>
      <Article>
        <Journal><JournalIssue><PubDate><Year>2024</Year></PubDate></JournalIssue></Journal>
        <ArticleTitle>Sleep timing and migraine attacks</ArticleTitle>
        <Abstract>
          <AbstractText>Sleep disruption and circadian timing are discussed in migraine cohorts.</AbstractText>
        </Abstract>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>222</PMID>
      <Article>
        <ArticleTitle>Caffeine withdrawal and migraine headache</ArticleTitle>
        <Abstract>
          <AbstractText Label="Background">Caffeine withdrawal may be associated with headache recurrence.</AbstractText>
          <AbstractText Label="Conclusion">Evidence remains mixed and observational.</AbstractText>
        </Abstract>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>333</PMID>
      <Article>
        <ArticleTitle>No abstract article</ArticleTitle>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>
"""


def test_esearch_pmids_builds_bounded_pubmed_query_url() -> None:
    seen: list[str] = []

    def fetcher(url: str) -> bytes:
        seen.append(url)
        return ESEARCH_JSON

    ids = esearch_pmids("migraine sleep", limit=500, api_key="abc", email="person@example.com", fetcher=fetcher)

    assert ids == ["111", "222"]
    assert "esearch.fcgi" in seen[0]
    assert "db=pubmed" in seen[0]
    assert "retmax=200" in seen[0]
    assert "api_key=abc" in seen[0]
    assert "email=person%40example.com" in seen[0]


def test_efetch_records_parses_pubmed_xml_into_workbench_records() -> None:
    records = efetch_records(["111", "222"], fetcher=lambda _url: EFETCH_XML)

    assert len(records) == 2
    assert records[0]["source_id"] == "111"
    assert records[0]["source_kind"] == "pubmed"
    assert records[0]["title"] == "Sleep timing and migraine attacks"
    assert records[0]["year"] == "2024"
    assert records[0]["url"] == "https://pubmed.ncbi.nlm.nih.gov/111/"
    assert records[1]["abstract"] == "Caffeine withdrawal may be associated with headache recurrence. Evidence remains mixed and observational."


def test_fetch_pubmed_records_uses_esearch_then_efetch() -> None:
    calls: list[str] = []

    def fetcher(url: str) -> bytes:
        calls.append(url)
        if "esearch.fcgi" in url:
            return ESEARCH_JSON
        return EFETCH_XML

    records = fetch_pubmed_records(query="migraine caffeine", limit=2, fetcher=fetcher)

    assert [record["source_id"] for record in records] == ["111", "222"]
    assert len(calls) == 2
    assert "id=111%2C222" in calls[1]
