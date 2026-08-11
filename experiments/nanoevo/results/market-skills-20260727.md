# Marketplace Skill evolution experiment — 2026-07-27

This experiment used the real `agnes-2.0-flash` model and fixed commits of
ItsDangerous and Click as evolution evidence. MarkupSafe was the held-out
repository. No fake provider or manufactured metric was used.

Only two efficiency metrics are compared:

- total tool calls;
- total model tokens.

Each Skill is compared only with its own evolved version.

| Skill | Review result | Tool calls V0 → V1 | Token total V0 → V1 | Outcome |
|---|---|---:|---:|---|
| `codebase-survey` | Patch applied | 17 → 8 (-52.9%) | 202,181 → 83,289 (-58.8%) | Improved both measured metrics |
| `analyzer` | Patch applied | 7 → 7 (0.0%) | 45,787 → 48,336 (+5.6%) | No efficiency improvement |
| `source-code-analysis` | `NO_CHANGE` | 12 → n/a | 106,401 → n/a | Reviewer attributed the inefficiency to execution behavior rather than a reusable Skill defect |

## Evolved changes

`codebase-survey` reduced a broad `head -60` source listing to `head -30` and
added an explicit instruction to use project guidance and manifests before
expanding the scan.

`analyzer` added a behavior guideline to inspect manifests, README files, and
documentation before deep scanning.

The `analyzer` result is deliberately retained even though it regressed in
tokens. NanoEvo can create a valid, trace-grounded Skill version without
guaranteeing that one stochastic held-out run will be cheaper.

## Raw evidence

- `codebase-survey-market-final-20260727.json`
- `analyzer-market-final-20260727.json`
- `source-code-analysis-market-20260727.json`

These are single held-out runs, not statistically significant performance
claims. Repeat trials are required before using the percentages as general
benchmarks.
