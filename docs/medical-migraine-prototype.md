# Medical Migraine Prototype

This prototype adapts the Enoch control-plane pattern to a literature-only
medical research workflow. It is for research-team demonstration and review,
not clinical decision support.

## What It Does

- Fetches migraine-related PubMed abstracts through NCBI E-utilities.
- Converts literature records into safety-gated hypothesis cards.
- Preserves source snippets, PubMed links, evidence limits, and safe next-test
  labels.
- Adds human review states for each card.
- Writes live demo runs under `state_dir/medical_workbench/` so dashboard use
  does not modify committed artifacts.

## Safety Boundary

Allowed next-test labels are limited to:

- literature review
- synthetic data simulation
- retrospective de-identified analysis
- wellness diary observation

The prototype must not produce or approve:

- diagnosis
- treatment recommendations
- medication or supplement changes
- human-subject experiments without formal review
- animal experiments
- invasive procedures
- self-experimentation beyond non-interventional wellness diary observation

Quoted PubMed evidence can contain clinical language, but generated hypotheses
and next-step labels must stay inside the research-only boundary.

## Dashboard Demo

Start the control-plane dashboard as described in `docs/quickstart.md`, then
open:

```text
http://127.0.0.1:8787/control/dashboard#medical
```

The Medical Research page can:

- load the committed PubMed sample report;
- generate a fresh state-dir report from the bundled PubMed sample records;
- fetch a bounded PubMed query and generate cards from those records;
- mark cards as `approved_for_research_planning`, `needs_more_evidence`, or
  `rejected`.

## CLI Demo

Fetch a small PubMed sample:

```bash
python scripts/fetch_pubmed_migraine.py \
  --limit 25 \
  --output targeted_paper_intakes/migraine_pubmed_sample.json
```

Generate a report:

```bash
python scripts/medical_migraine_workbench.py \
  --input targeted_paper_intakes/migraine_pubmed_sample.json \
  --output artifacts/medical-migraine-workbench/pubmed_sample_report.json
```

For repeated local demo runs, prefer the dashboard/API path because it writes
outputs under `state_dir/medical_workbench/`.

## API Surface

All endpoints require the normal control-plane bearer token.

- `GET /control/api/medical/migraine/sample-report`
- `POST /control/api/medical/migraine/fetch`
- `POST /control/api/medical/migraine/generate`
- `POST /control/api/medical/migraine/review/{card_id}`

`/fetch` accepts `query`, `limit`, optional `email`, and optional `api_key`.
The limit is bounded to `1..200`.

`/generate` accepts either inline `records` or a `records_path` previously
created under `state_dir/medical_workbench/`.

`/review/{card_id}` accepts `review_status`, optional `report_path`,
`reviewed_by`, and `review_notes`.
