# Live Anthropic check

13 October 2026 (Africa/Lagos; the machine-readable start time is 12 October
23:11 UTC). Three real Anthropic calls passed against synthetic project memory.
The API reported model `claude-sonnet-5`, using the model and credentials already
configured in the owner-provided environment file. No credential values were
printed, saved into the project, or included in model prompts.

The memory service and registry were disposable local instances. Owner approvals
used public test identities. No live Monad transaction or UI change occurred.

## Observed behavior

| Call | Role and state | Result |
| --- | --- | --- |
| 1 | Planning, accepted 30-day retention decision | Cited the accepted decision, distinguished the unmeasured latency observation, proposed a 14-day replacement and explicitly said it needed owner approval |
| 2 | Coding, 14-day proposal still pending | Recommended implementing 30 days and cited the existing accepted record; the proposed correction had not become current |
| 3 | Coding, after the test owner approved the exact correction | Recommended 14 days, cited the replacement record, and suggested an implementation check without claiming to execute it |

A separate unapproved 90-day proposal stayed out of every model payload. The
harness verified the owner's prepared control/snapshot against the exact generated
proposal before signing. After approval it independently verified the registry
head and checked that the superseded record was no longer current.

Manual review found the three answers consistent with the retrieved records and
owner-review boundary. The final answer left the retention clock (creation versus
last update) as an implementation choice rather than inventing an accepted rule.
That remains a useful open question for the project, not another approved decision.

## Usage and evidence

The three responses ended normally with `end_turn`. Each call had a 1,536-token
output ceiling, no automatic retries, and a 45-second model request timeout.

| Call | Input tokens | Output tokens | Worker elapsed time |
| --- | ---: | ---: | ---: |
| Planning | 1,018 | 155 | 4.733 s |
| Coding before approval | 1,023 | 144 | 3.086 s |
| Coding after approval | 1,018 | 187 | 3.493 s |
| Total | 3,059 | 486 | 11.312 s |

Token counts come from provider usage metadata. Worker time also includes memory
retrieval and verification; it is not isolated model latency. These are observed
samples, not estimates of future latency or dollar cost.

[The original result](results/live-assistants.json) retains the synthetic questions,
answers, citations, proposal, projected memory payloads, usage and checks. It does
not contain API keys, source credential-file contents or storage keys.

## Fix found during review

The generated prose referred to aliases such as `m1`, but the adapter's citation
objects only returned record IDs. The adapter now includes `ref` alongside each
citation, so consumers can resolve those inline aliases directly. The existing
unit test now checks that mapping. The full deterministic suite passes: 21
TypeScript checks and 30 Python tests.

The archived live outputs intentionally preserve what the provider and adapter
returned before that small fix. No extra paid calls were made to recheck a
presentation-field mapping already covered by the deterministic test.

## Repeat the bounded check

This script is deliberately outside the default test suite. It requires an
explicit live flag and a credential-file path:

```sh
npx tsx scripts/live-assistants.ts --live --env-file /path/to/anthropic.env
```

The file must define `ANTHROPIC_API_KEY` and `ANTHROPIC_MODEL`; workspace ID is
optional when the account does not require one. The reader supports plain or
quoted values and an optional `export` prefix. It does not execute shell code or
expand substitutions. Supply a model supporting the configured structured-output
API. The script creates its own local service and Anvil instance, caps itself at
three model calls, and cleans up only those temporary resources.

This is a small live integration check, not a quality benchmark, an adversarial
model evaluation, a claim that citations prove entailment, or evidence of external
adoption. The next backend milestone is Monad testnet integration with the
specified finalized-block policy. Independent provider compatibility and OS
credential-store custody remain open as well.
