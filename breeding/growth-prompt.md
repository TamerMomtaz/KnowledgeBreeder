# Growth run prompt

You are improving KnowledgeBreeder. Work in a branch and finish with a draft pull request. Never merge.

1. Read `breeding/candidates.md`, `breeding/rejected.md` (if present) and the last 20 lines of `breeding/scores.jsonl`.
2. Search for what is new since the last run: P&ID digitization papers, diagram-to-graph models, open datasets,
   releases of the tools in `candidates.md`. Add at most three new rows to `candidates.md`, each with a source
   and the date checked. A vendor's own numbers are a claim, not evidence.
3. Pick the one candidate most likely to raise flow F1. Implement it as a reader or a rule, with tests.
4. Score champion and challenger on every gold file in `gold/`, logging both to `breeding/scores.jsonl`.
5. If `beats()` says the challenger wins, open a draft PR titled "Promote <name>: flow F1 a -> b".
   If it loses, add it to `breeding/rejected.md` with both scores and open a PR for that record only.
6. Report in the PR body: what was tried, both scores, what was not verified.
