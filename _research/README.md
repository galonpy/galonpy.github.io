# Citation review data

This directory is tracked in Git but is not rendered or linked by the Jekyll site.

`citation_review.csv` contains the Semantic Scholar citation-review dataset for
“Detecting Language Model Attacks with Perplexity.” The review covers 484 citing
papers returned by the authenticated Semantic Scholar API on July 26, 2026.

Important distinctions:

- `indexed_author_affiliations` contains Semantic Scholar author-profile data and
  may not represent the affiliation printed on a specific paper.
- `primary_source_verified_organizations` contains organizations whose affiliation
  and citation evidence were checked against the citing paper.
- `review_status` distinguishes records with citation context from records for
  which only metadata was available, and identifies passages recovered directly
  from citing-paper PDFs.
- `excerpt_source_url`, `excerpt_page`, and `excerpt_recovery_method` record where
  recovered evidence came from and whether it is an in-text passage or a
  bibliography-only excerpt.

`recovered_excerpts.json` preserves the page-level PDF recovery annotations.
The build script also publishes a key-free excerpt export under `assets/data/`
for the site’s lazy-loaded citation-excerpt expansion.

`organization_affiliation_audit.csv` records the second-pass verification for
every company and university shown on the site. An organization is retained only
when its linked publication explicitly prints the name as an author affiliation.
Google is the sole documented exception: that publication explicitly describes
Google as the workshop host.

The API key is stored separately in `.env.semantic-scholar`, which is ignored by
Git and must never be committed.
