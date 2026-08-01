"""Response contract for the confidential store's own lifecycle — configuration and lock state.

Its own module rather than an addition to ``assurance_signals``: that one is about the *content* of the
store, and this is about whether the store can be opened at all. The two are read by different
surfaces at different times — the status banner asks this on every page load, whether or not anything
is unlocked — and ``assurance_signals`` is already at the module-size limit.
"""

from __future__ import annotations

from typing import Literal

from src.infrastructure.rest.contracts.wire_shape import Closed


class AssuranceStoreStatusResponse(Closed):
    """Whether the confidential store is configured, and whether it is open.

    Always answerable, unlocked or not — this is the one assurance read that must work while the store
    is locked, because it is what tells a client *that* it is locked. So it carries no store content
    and needs no exposure filtering.

    ``status`` is the field to branch on; the three booleans are the reasons behind it, and they do not
    collapse into one. *Configured* means a database file exists and a key for it is in the credential
    store. *Unlocked* means this process has been authorised to open it — a separate fact, because the
    activation policy is ``manual`` and a restarted backend starts locked with the key still present.
    A client that conflated them would tell the user to initialise a store that already exists.
    """

    #: A database file exists *and* its key is retrievable. Either alone is a broken installation.
    configured: bool
    #: This process holds the key and can read the store right now.
    unlocked: bool
    #: The file is on disk. False with ``key_in_keychain`` true means a key outlived its store.
    db_exists: bool
    #: The key is retrievable from the OS credential store. False with ``db_exists`` true is the
    #: key-loss shape: the ciphertext survives and nothing can open it.
    key_in_keychain: bool
    #: The state a client renders, derived from the three above so every caller derives it the same way.
    status: Literal["unlocked", "locked", "not_initialised"]
    #: Which module class this store belongs to. Constant today; declared because the status banner
    #: keys its wording off it and a second confidential module would otherwise change it silently.
    module_class: str
