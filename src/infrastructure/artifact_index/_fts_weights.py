"""How each searchable kind's fts5 columns rank against one another.

One module because one omission in one of these lists is silent: fts5 accepts a weight list shorter
than the table's column count, treats the missing trailing weights as nothing, and ranks anyway. So
each list is written next to the column order it applies to, and
`tests/architecture/test_fts_weights_match_their_columns.py` reads *this* file against the DDL.

The lists order results *within* a kind. Nothing here decides how kinds rank against each other —
that is `_rank_balanced`, and the two must not be confused: bm25 scores and the token-match
supplement are on scales that say nothing about each other.
"""

from __future__ import annotations

# Entity name column (position 1) gets 15× weight over content_text (0.5).
#
# `host_diagram_id` is weighted at nothing and is UNINDEXED: it is carried on the table so the
# visibility filter can run inside the per-kind LIMIT, never so a query can match on it. Nine values
# for nine columns — the gate next door exists because fts5 accepts a short list and silently shifts
# every later weight onto the wrong column.
# Columns: artifact_id(UNINDEXED), name, artifact_type, domain, subdomain, keywords, content_text,
#          display_label, host_diagram_id(UNINDEXED)
ENTITY_WEIGHTS = "0, 15.0, 1.0, 1.0, 1.0, 4.0, 0.5, 4.0, 0"

# A note's title matters most, but only about as much as an entity's *keywords* do — the ranking
# guarantee is in `_rank_balanced`, and these weights only order notes against one another.
#
# Seven values for seven columns. There were six, and the list omitted `scratchpad_id`: every weight
# after it landed on the wrong column, so the UNINDEXED id absorbed the title's 4.0, the title took
# the body's 0.5, and `scratchpad_name` got nothing. fts5 accepts a short list without complaint, so
# the only symptom was a ranking nobody could explain — a note matched on its scratchpad's *name*
# outranking one matched on its own title, both at ~1e-7.
#
# `scratchpad_name` is weighted at nothing, deliberately. A pad is a container and its notes are what
# search returns, so matching the container's name answers with notes that contain none of the query —
# "Q3 platform thinking" returning a note called "AI-Assisted and Agentic Development". Finding the pad
# is a different question and needs a pad-shaped result, not its contents.
# Columns: artifact_id(UNINDEXED), scratchpad_id(UNINDEXED), title, body, element_type, domain,
#          scratchpad_name
NOTE_WEIGHTS = "0, 0, 4.0, 0.5, 1.0, 1.0, 0"

# A diagram is discoverable by its title, its type, and the names of the entities it draws. Ranked
# rather than left at fts5's flat 1.0 per column, because those are not equally strong evidence: a
# diagram *named* for what you searched is a better answer than one that merely draws something of
# that name, and the flat default made the two indistinguishable.
# Columns: artifact_id(UNINDEXED), name, diagram_type, artifact_type, member_names
DIAGRAM_WEIGHTS = "0, 8.0, 2.0, 1.0, 2.0"

# A pad's name is what someone typed to look for it; its description is prose they wrote about it. The
# name is weighted as a document's title is, and the description a little above a document's body,
# because a pad's description is two sentences of intent rather than pages of content.
#
# Nothing here lifts a pad above committed content — `rank_balanced` draws subordinate kinds last, and
# these weights only order pads against one another.
# Columns: artifact_id(UNINDEXED), name, description
SCRATCHPAD_WEIGHTS = "0, 4.0, 1.0"
