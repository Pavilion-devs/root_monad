# Project memory example draft

This is a readable view of [memory.example.json](memory.example.json). It uses
evidence available in this conversation while distinguishing user statements from
assistant proposals. These local labels are illustrative, not signed approvals or
live permissions. No source-message timestamps or platform message IDs are invented.

## Context a new application should receive

The user has selected cross-application, user-owned AI memory as the working Monad
hackathon direction. Project decisions and context are the proposed initial scope.
The exact role of Monad and the choice of storage or memory engine remain open.
An existing agent runtime may supply execution, while the proposed memory protocol
should be usable independently of that runtime.

## Records and their authority

| Record | Kind | Evidence status | Content |
| --- | --- | --- | --- |
| direction | Decision | Supported by an explicit user statement in this conversation | Pursue cross-application AI memory as the working hackathon direction |
| project-scope | Proposal | Suggested by the assistant; a design draft is authorized | Start with ongoing project decisions and context |
| clearance-result | Observation | Recorded experiment report | Clearance enforcement worked in the spike; this does not establish market demand |
| independent-runtime | Proposal | Suggested by the assistant | Other applications should integrate without adopting our runtime |
| monad-role | Proposal | Suggested by the assistant | Evaluate shared authorization and version commitments on Monad |
| chain-necessity | Open question | Unresolved | What does Monad improve over signed portable permissions and a version log? |

## Interpretation rules

"Supported by a user statement" is a description of conversational evidence. In
a real protocol, an imported record cannot acquire owner authority simply by
containing that string. Verification needs trusted identity, an authorized signing
mechanism, and evidence bound to the actual content and revision.

The clearance report supports the observed test results. The separate assessment
of differentiation is an assistant judgment and is not evidence of a customer
decision. A new application should preserve that distinction.

The JSON's demonstration section contains a hypothetical incorrect proposal and
correction. It must not be imported into current project facts. They illustrate
how rejection and replacement could be represented, not actual user approvals.

## A useful first response from application B

"We're exploring a portable memory protocol for the Monad hackathon. The working
direction has your support. Project context is the proposed first use case; the
storage backend and onchain authority model are still undecided. I can propose
changes, but I should not turn those suggestions into your decisions."

This response is the behavioral target. A polished summary that silently turns
all proposals into facts fails the example.
