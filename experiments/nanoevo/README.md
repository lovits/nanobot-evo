# NanoEvo real-model experiment

This experiment uses two fixed-commit Python repositories as experience and a
third fixed-commit Python repository as held-out evaluation. It does not install
or call a fake provider, and it does not manufacture success metrics.

The runner:

1. creates a fresh agent workspace with the baseline `repo-analysis` Skill;
2. clones the three repositories at the commits in `repositories.json`;
3. runs the held-out repository once without collecting evolution evidence;
4. runs the two experience repositories and records real trajectories;
5. triggers one evidence review through the configured real model;
6. optionally applies the Pending Proposal when `--approve` is supplied;
7. reruns the held-out repository and writes the raw responses and deterministic
   metrics to the requested JSON file.

It also accepts a ClawHub-installed Workspace Skill through `--skill-name` and
`--skill-source`. When evolution is applied, the result contains an
`efficiency` object with the only two cost metrics used by the marketplace
experiment:

- total tool calls;
- total model tokens.

Example using an installed market Skill:

```bash
.venv/bin/python experiments/nanoevo/run_experiment.py \
  --config ~/.nanobot/config.json \
  --workspace /tmp/nanoevo-codebase-survey \
  --output experiments/nanoevo/results/codebase-survey.json \
  --skill-name codebase-survey \
  --skill-source ~/.nanobot/workspace/skills/codebase-survey \
  --max-tool-iterations 12 \
  --review-feedback "Reduce redundant listing and repeated file reads." \
  --approve
```

Run the same command with fresh workspaces for `source-code-analysis` and
`analyzer`. Compare each Skill only against its own prior version; do not rank
different Skills by raw token count because their output contracts differ.
The experiment overrides the production agent's tool-iteration budget only
inside its isolated workspace; both V0 and V1 receive the same limit.

Example:

```bash
export AGNES_API_KEY="..."

.venv/bin/python experiments/nanoevo/run_experiment.py \
  --config experiments/nanoevo/agnes-config.example.json \
  --workspace /tmp/nanoevo-real-run \
  --output /tmp/nanoevo-real-result.json \
  --review-feedback "Check one concrete defect visible in both experience traces." \
  --approve
```

The API key and model come from the normal nanobot configuration/environment.
If the review should use a different configured model preset, add
`--review-model-preset <name>`. Never place an API key in this repository or in
the result JSON.

The checked-in Agnes example contains only an environment-variable reference;
it does not contain a credential. `agnes-2.0-flash` is selected because the
provider exposes it as its free text/tool-calling model. Replace the example
config when reproducing with a different provider.

Pinned repositories:

| Role | Repository | Commit |
|---|---|---|
| Experience | `pallets/itsdangerous` | `672971d66a2ef9f85151e53283113f33d642dabd` |
| Experience | `pallets/click` | `00e592cea702e0b2caa0dee42489fdb1c22cd845` |
| Held-out | `pallets/markupsafe` | `b2e4d9c7687be25695fffbe93a37622302b24fb1` |

The output is intentionally raw JSON. Do not claim an improvement until the
same file contains both the real baseline and evolved held-out responses.
The runner sets `evolution_applied=false` and skips the evolved run when Review
returns `NO_CHANGE`, the Proposal is not approved, or a safety gate rejects it.
This prevents an unchanged second sample from being mislabeled as evolution.

`--review-feedback` is optional and is stored in the `ReviewRequest`. It may
focus Review on an observed cross-trace defect, but it cannot bypass Workspace
targeting, evidence existence, patch validation, base-hash checking, or human
approval.

The multi-Skill marketplace run and its honest V0/V1 efficiency summary are
recorded in
[`results/market-skills-20260727.md`](./results/market-skills-20260727.md).

## Recorded real run

The checked-in result
[`results/agnes-2.0-flash-20260726.json`](./results/agnes-2.0-flash-20260726.json)
contains the unedited model responses, tool calls, token usage, Review decision,
Proposal, approval record, and deterministic metrics from one real run.

The two experience trajectories independently showed the same defect: the
analysis often cited bare filenames that could not be resolved from the
repository root. The real Review model proposed one local replacement in the
existing `repo-analysis` Skill:

```text
Cite concrete relative paths ...
```

became:

```text
Cite repository-root-relative paths ... Never cite bare filenames ...
```

Held-out result on the pinned MarkupSafe commit:

| Metric | Baseline | Evolved | Change |
|---|---:|---:|---:|
| Grounded repository-path rate | 77.8% | 93.3% | +15.6 pp |
| Required-term recall | 100.0% | 83.3% | -16.7 pp |
| Tool calls | 19 | 25 | +6 |
| Total tokens | 145,361 | 304,555 | +159,194 |

This is a successful end-to-end evolution case, not evidence of universal
performance improvement. Path grounding improved, while coverage and cost
regressed. It is a single held-out repository and a single stochastic sample;
repeat runs and more held-out repositories are required for a statistical
claim.

During this run the real evidence payload initially starved the Reviewer of the
second trajectory because the normal tool-result limit truncated the window.
The runtime was corrected by giving the isolated Reviewer a larger bounded
result limit and returning a compact projection of every trace. No model output
or metric was invented to hide the failed first Review attempt; it remains in
the result JSON under `review_attempts`.
