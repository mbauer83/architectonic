# Proposing Changes to Promoted Content

An engagement repository holds a reference to each artifact promoted to the enterprise
repository, not the artifact itself. Editing one therefore has nowhere local to write. Instead of
refusing the edit, the repository records it as a **change**: a statement of what the artifact
should say, held here until somebody upstream accepts it.

There is no separate "propose" action. You edit; it is recorded, because that is the only thing
an edit to content you do not own can be.

&nbsp;

## The lifecycle

```
 edit a promoted artifact ──► draft ──► submitted ──► integrated
        [recorded here]                   │             [upstream carries it]
                                          │
                          draft ◄─────────┘  the branch went away without it
```

| State | Meaning |
| --- | --- |
| `draft` | Recorded here. Nobody upstream has been asked to look. |
| `submitted` | Replayed into the enterprise repository and published on a review branch. |
| `integrated` | Upstream carries the change's effect. The record is kept, not deleted. |
| `abandoned` | Taken back. The record is kept as evidence it existed. |

A terminal record is never changed again, and never removed — a change somebody reviewed leaves a
trace whatever became of it.

&nbsp;

## Seeing what you are holding

The **Proposed** page lists every live change. A row names the artifact, not the change file: you
did not author that file and have no use for its id. For each changed field it shows what the
change asks for beside what the artifact says now, so a change needing attention can be acted on
without opening anything else.

An artifact carrying changes is marked wherever it is read. The marker says which fields are
proposed and whether anyone upstream has been asked yet — a read never silently blends a proposal
into the enterprise baseline.

&nbsp;

## Submitting

**Submit** on the Proposed page takes the changes you are holding, in the order shown, and:

1. replays each recorded edit into the enterprise repository through its own authorised writer;
2. commits the result on the enterprise working branch, verifying the whole tree first;
3. pushes that branch and marks the changes submitted — only once the remote confirms the ref.

The branch is the unit of review, and it is the same working branch promotions accumulate on: one
branch, one review, whatever it carries.

A submission is refused, with nothing written, when:

- **the enterprise repository has unsaved work** — the commit stages the whole tree, so submitting
  would publish that alongside the proposed changes;
- **upstream already says what a change asks for** — there is nothing to put in front of a
  reviewer, and the remedy is to discard the change;
- **a change no longer applies** to the artifact as it stands — rebase it first;
- **two changes write the same field of the same artifact** — whichever replayed second would
  silently overwrite the other, so the pair is refused rather than ordered.

&nbsp;

## When upstream moves

The enterprise branch moves while proposals wait, so a change going stale is the ordinary case
rather than an error. **Bring onto the current version** re-applies the recorded edit where it can
be judged and reports one of three outcomes:

- **clean** — it still applies and still verifies; the change now records the version it was
  proven against;
- **already upstream** — the artifact says what the change asked, so discard it;
- **conflicting** — the verifier's own refusal, and nothing is written.

Rebasing a change that has already been submitted does more: the branch a reviewer is reading
cannot be rewritten under them, so a replacement branch is opened on the current head, the whole
submitted set is replayed onto it, and it is published. The branch it replaces is retired once its
successor is established. Where the branch carries work the set does not account for — promoted
content, most often — the rebase is refused and says what it found, because a replacement would
not carry it.

&nbsp;

## Taking a change back

**Discard** ends a change and keeps the record. A change that is still a draft is taken back
directly.

A change already on a published branch is not: taking it back here would not take it off the
branch a reviewer is reading. Discard the submission first — the branch goes, and the changes it
carried return to `draft`, where each can be revised or discarded normally.

&nbsp;

## Integration

Whether upstream has taken up a change is decided by **content against `origin/main`**, never by a
commit id, so a squash or rebase merge is handled like any other. When the enterprise artifact
carries a change's effect, the change closes as integrated on the next reconciliation. A review
branch is taken down once upstream holds everything on it.

A change still submitted when no branch is published — a reviewer merged part of a set, or closed
the review without merging — returns to `draft`. It was not rejected and it was not accepted; it is
simply no longer in front of anybody, and you can revise it or send it again.

&nbsp;

## Where this does not apply

An **admin deployment** writes the enterprise repository directly, and editing promoted content
there changes it rather than recording anything. The change-proposal path is for a deployment that
holds no authority over enterprise content, which is the ordinary engagement.

Every operation is available on all three surfaces — the GUI, the REST API, and the MCP tools
(`artifact_list_changes`, `artifact_submit_changes`, `artifact_rebase_change`,
`artifact_discard_change`).

&nbsp;

*Next: [Views & exploration →](views-and-exploration.md)*
