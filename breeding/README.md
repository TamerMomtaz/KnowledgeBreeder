# Breeding: how this repo gets better on its own

KnowledgeBreeder is meant to improve every time it is used. The loop:

1. **Scout.** Look for a new reader, model, rule or dataset (papers, releases, model hubs).
2. **Plug in.** Add it as a reader in `knowledgebreeder/readers/` or a rule in `knowledgebreeder/use/research.py`.
3. **Score.** Run the champion and the challenger on the same gold files:
   `kb score <graph> <gold.json> --log breeding/scores.jsonl --label <name>`.
4. **Promote or drop.** `scoreboard.score.beats()` is the rule: flow F1 must rise and nothing else may fall.
   A challenger that does not win is recorded in `rejected.md` with its score, so nobody tries it twice.
5. **A person signs.** Every promotion is a pull request. Nothing merges itself.

## Files
- `scores.jsonl`: one line per scored run (created by the first `kb score --log`).
- `candidates.md`: what to try next, with sources.
- `rejected.md`: what lost, and by how much (created when the first challenger loses).

## Running it on a schedule
`growth-prompt.md` is the prompt for a scheduled agent run (weekly is plenty). No schedule exists yet; one has to
be created deliberately.
