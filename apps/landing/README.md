# Landing page

A single static file, `index.html`, with no build step and no dependencies.
Open it directly or serve the folder:

```bash
open apps/landing/index.html
# or
python3 -m http.server 4000 --directory apps/landing
```

**Every number on it is measured**, and each one traces to something in this
repository:

| On the page | Where it comes from |
|---|---|
| 225 filings, 363 edges, 207 relationships, 83 companies | `make eval` |
| 28 of 28 concentration relationships correct | `make audit`, judged by hand |
| 41 of 60 narrative relationships correct | `eval/narrative_sample.txt`, seed 991103 |
| 21 of 21 percentages correct, 7 withheld | `eval/concentration_all.txt` |
| 48 of 60 disclosures name nobody | `eval/recall_candidates.txt`, seed 4417 |
| 26 events | `make backtest` |

When the graph changes, re-run `make eval` and `make audit` and update the page
in the same commit. A landing page quoting numbers the repository no longer
produces is worse than one with no numbers at all.
