# Motivation coverage: what "covered" actually means

Most coverage questions get answered *existentially*: "does this goal have anything realizing
it?" That question is easy to satisfy and easy to mislead yourself with. A goal that fans out
into three outcomes, where only one of them has any requirements underneath, still answers
"yes — something realizes me". The report comes back green while a third of the intent has no
implementation at all.

The `motivation-coverage` viewpoint answers a stricter question: **is every modeled branch
complete?** A goal counts as covered only when *each* of its outcomes leads to requirements,
and *each* of those requirements is realized by something that is permitted to realize it.
One incomplete branch makes the whole row a gap, and the row tells you which branch.

This page explains the semantics. For the YAML shape see
[Viewpoints — schema reference](../reference/viewpoints-schema.md); for viewpoints generally
see [Viewpoints](viewpoints.md).

&nbsp;

## The false green this prevents

Take a goal with two outcomes:

```text
Goal: Enable fast feedback from implementation to architecture
├── Outcome: Changes validated against architecture before implementation
│     └── (no requirements)
└── Outcome: Implementation changes fed back, reviewed, promoted
      └── (no requirements)
```

An existential check reports this goal as **realized** — it has outcomes, and reachability
from the goal succeeds. Branch-complete evaluation reports it as a **gap** with
`incomplete_branch`, naming both outcomes and stating that the expected next node is a
`requirement`.

The distinction matters most on the *nearly* complete rows. A goal with 26 branch obligations
where 25 are satisfied is still a gap — and that one missing branch is exactly the thing a
green summary would have hidden.

&nbsp;

## Obligations, including ones for things that don't exist

Coverage is a ratio, and a ratio needs a denominator. The subtlety: **a denominator built only
from nodes that exist cannot measure a node that is missing.** If an outcome has no
requirements, there is no requirement row to mark uncovered — the branch simply vanishes from
the count, and the percentage looks better for it.

So evaluation enumerates *obligations*, some of which stand for absent nodes:

| Obligation | Means | Verdict |
| --- | --- | --- |
| `requirement` | a real requirement to be realized | covered or uncovered |
| `shortcut` | a requirement wired straight to the goal, skipping the outcome | always a gap, flagged |
| `missing-requirement` | an outcome exists, but nothing refines it into requirements | always a gap |
| `missing-outcome` | a goal with no outcomes and no shortcut at all | always a gap |

A requirement realizing two different outcomes produces **two** obligations, even though one
realizer satisfies both — because the two branches are separately meaningful. Duplicate paths
to the *same* obligation collapse; distinct obligations never do.

A row is a gap when any obligation is uncovered, or when any `missing-*` obligation exists.
Zero expected branches is a gap, never a vacuous pass.

&nbsp;

## Shortcuts and ambiguous links

A requirement connected *directly* to a goal with an influence relationship is a **shortcut**:
real modeling intent, but it skips the outcome layer, so the chain cannot be checked the way a
full branch can. It is reported with status `shortcut` and counts as a gap — visible, not
silently accepted.

A plain association between a requirement and a goal is treated differently again. Association
carries no realization semantics, so reading it as coverage would be inventing intent the model
never expressed. It is reported as `ambiguous_link` — surfaced so you can model it properly,
without the view asserting anything on your behalf.

&nbsp;

## Authoritative verdicts vs. diagnostic observations

The table has two kinds of column, and conflating them is the most common way a coverage report
becomes wrong.

**Authoritative** columns decide the row verdict:

- `motivation` — are the branches complete?
- `overall_realization` — does each terminal requirement have a realizer that the ontology
  actually permits to realize a requirement? The eligible set is derived from the ontology's
  own relationship rules, spanning every family (application, business, technology, physical,
  strategy, implementation), minus motivation-internal refinements and structural helpers like
  junctions and groupings.

**Diagnostic** columns observe, and never judge:

- `behavior_coverage`, `business_coverage`, `application_coverage`

A diagnostic column reads `observed` or `none_observed`. **`none_observed` is not a gap.** There
is no rule that every requirement must be realized in every layer — an application-only
requirement is perfectly well modeled, and flagging it as a business-layer failure would produce
systematic false gaps. So the diagnostics tell you *where* realization was found, while the
verdict rests solely on the authoritative columns.

This is why the table shows text, not just color: `none_observed` and `gap` mean entirely
different things and must never be distinguishable only by a shade.

&nbsp;

## Direct edges for branches, derived chains for leaves

Two different traversals, deliberately:

- **Branch enumeration walks direct, stored connections only.** Derived relationships compose
  and collapse paths — exactly the wrong behavior when the question is "is *this modeled
  branch* complete?" A derived edge could bypass the very outcome whose absence you are trying
  to detect.
- **Leaf coverage is existential over direct *and* derived realization chains**, up to a bounded
  number of hops. Here composition is what you want: a requirement realized by a component that
  is part of a larger system is genuinely realized.

If the bounded search is cut short by its budget, the view says so — coverage is then a lower
bound, not a final verdict.

&nbsp;

## Scope, groups, and status

- **Rows** are goals, outcomes, and requirements — selectable with the `scope` parameter.
- **`gaps_only`** filters to failing rows, applied *after* evaluation, so a gap beyond the page
  limit still counts in the totals.
- **`group`** restricts rows to particular model groups. Omit it and every group is reported;
  naming a group that doesn't exist yields an empty result rather than an error, so a saved
  filter survives the model changing underneath it.
- **Deprecated and retired entities are excluded** as rows *and* as branches. An obligation
  whose only realizer is retired is therefore a gap — which is the honest answer.
- Rows carry their tier, so engagement and enterprise content stay distinguishable.

&nbsp;

## Relationship to requirements coverage

[`requirements-coverage-gaps`](viewpoints.md) answers the narrower, per-requirement question:
*does this requirement have any incoming realization?* It remains the right tool for a quick
sweep over requirements alone.

`motivation-coverage` answers the chain question across goals, outcomes, and requirements, and
distinguishes *incomplete* from *unrealized*. The two agree on whether a given requirement has a
realizer; they differ in that only the coverage view can tell you a branch is missing entirely.

&nbsp;

## Reading a result

Each row states its worst status, and the failing obligations are listed (capped, with an
overflow count) so the output stays readable on a large model. Rows are ordered worst-verdict
first, so the top of the table is a work list rather than an alphabetical index.

Exports carry the same information: one column group per pattern, with the authoritative and
diagnostic roles kept in separate column shapes, plus a `param:` column per bound parameter so
an exported file records exactly the execution a shared URL would reproduce.
