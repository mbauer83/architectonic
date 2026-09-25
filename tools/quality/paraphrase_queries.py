"""Queries written by a person to find a model element by what it is, without using its name.

This is the question retrieval by meaning exists for: someone remembers what a thing does or is for,
not what it is called. Nothing the repository states answers it, because every description the model
holds shares its element's own vocabulary, so these are written for the purpose. Each one:

- describes the element's role in everyday words, as a reader looking for it might;
- uses none of the words in the element's name, and avoids copying its description;
- has exactly one intended answer.

Keyed by the rename-stable part of the id (`PREFIX@epoch.random`), so renaming an element never
breaks its query; an element that has been deleted drops its query, and the suite reports how many
remain. The set spans the element types the self-model holds rather than favouring one.
"""

from __future__ import annotations

PARAPHRASES: tuple[tuple[str, str], ...] = (
    # requirements
    ("REQ@1712870400.5PPAX3", "means for people to write and change what the model contains"),
    ("REQ@1712870400.JTRw1x", "checking that the model is correct and internally consistent"),
    (
        "REQ@1712870400.kOU3al",
        "keep organisation-wide reusable content apart from project-specific work, at separate levels",
    ),
    ("REQ@1777371979.W-G4L5", "a table in the browser showing model elements that can be narrowed by domain and type"),
    ("REQ@1780655839.kjBJrh", "every safety or security analysis must point at the model element it examines"),
    ("REQ@1784532460.n0Qwax", "colours computed from vulnerability findings must not be saved into files"),
    (
        "REQ@1786111532.2RiwRh0",
        "store the documents describing an intended modification, linking each to the elements it alters",
    ),
    ("REQ@1790305394.1bkWD0Y", "put company logos on the boxes in a picture of the model"),
    (
        "REQ@1789640735.7Qke86l",
        "one command that upgrades an installation to a new release and puts everything back if it fails",
    ),
    (
        "REQ@1781976357.A5WgC8",
        "each kind of drawing contributes its own checks and its own way of being drawn, as an extension",
    ),
    # functions
    (
        "FNC@1712870400.B_F-Sq",
        "checking that the property values in an element's table are allowed fields of the right kind",
    ),
    ("FNC@1776633708.n_JYA2", "turning a long identifier into the short handle used inside PlantUML source"),
    ("FNC@1777390496.Z2rrfP", "choosing which items to move up into the organisation-wide copy"),
    ("FNC@1777399928.tRAV0x", "publishing a prepared and checked batch of file changes into the live working copy"),
    (
        "FNC@1786225282.foobGD2",
        "turning notes from the sketching canvas into real elements and relationships in one transaction",
    ),
    ("FNC@1784532426.gvj-dp", "exposing computed posture numbers so that views can colour elements by them"),
    # application components
    ("APP@1712870400.JOmFWy", "builds the searchable database of everything the markdown files hold"),
    ("APP@1712870400.v9LvfK", "answers full-text searches and walks the relationships between elements"),
    ("APP@1776633697.SCKD2U", "sets up the skeleton of a new drawing from a list of chosen elements"),
    ("APP@1777399924.5n_KQJ", "runs many creates and edits together as one all-or-nothing operation"),
    ("APP@1780656431.E0fzqZ", "the encrypted database holding safety and security analyses"),
    ("APP@1780783708.Ne0utf", "the stdio process an agent host launches for query-only access through the backend"),
    ("APP@1780783992.Je9pmw", "the remote service such as GitHub or GitLab where the shared copies live"),
    ("APP@1782080485.uTC8zx", "serialises every change to the encrypted safety database, one at a time"),
    ("APP@1784017465.SZJSV5", "works out indirect relations from chains of existing connections"),
    ("APP@1790305394.r5k14Kq", "keeps uploaded logos, cleans SVG files and stores them as small pictures"),
    (
        "APP@1789640743.3hRHTJT",
        "moves an installation to a newer release after checking signatures, and rolls it back on failure",
    ),
    ("APP@1777293136.yaxrWl", "turns textual drawing source into SVG and PNG images"),
    # data objects
    ("DOB@1712870400.3rilik", "the database file of metadata rebuilt from the markdown files"),
    ("DOB@1777239791.4Z28xK", "the .puml text file a picture of the model is kept in"),
    ("DOB@1777293139.UjyXG3", "the YAML files that define which element and relationship kinds exist"),
    ("DOB@1777399930.hExrX3", "what lets a long batch job be resumed or retried without doing it twice"),
    ("DOB@1780656431.p04R7k", "where SBOM components and vulnerability findings are kept"),
    ("DOB@1784712071.M6gx2l", "the local copy of imported method advice kept under the user's config directory"),
    ("DOB@1790305394.OQBkE5f", "a logo stored as a text file, with who owns the mark"),
    # business objects
    ("BOB@1712870400.6Uok0b", "the organisation-wide collection of reusable models shared by every project"),
    ("BOB@1777237431.55sMuE", "a text with required sections and a frontmatter schema, such as a decision record"),
    ("BOB@1777390173.lt7iFm", "settings saying where the project copy and the organisation copy are located"),
    ("BOB@1780656241.mY4fte", "a chain of hashes proving that no change to safety evidence was hidden"),
    ("BOB@1783870959.LvpBTq", "a stored recipe for which elements to pick and how to present them"),
    ("BOB@1780656241.H-uAJl", "analysis of an accident after it happened, with its causes and fixes"),
    # value streams
    ("VS@1784483073.shr_q3", "moving checked project work up into the shared organisation baseline"),
    ("VS@1784483036.S4ZTiY", "identifying what could go wrong: losses, unsafe control actions and attack paths"),
    ("VS@1784483005._fm4gq", "agreeing what a piece of work is meant to achieve before starting it"),
    # outcomes
    ("OUT@1712870400.AlZjX8", "less time spent on design reviews and approvals thanks to agents"),
    ("OUT@1776629112.edEkJa", "solutions that worked in one project get reused by others"),
    # processes
    ("PRC@1776635649.vlE-5j", "checking whether what was built matches the intended design"),
    ("PRC@1777409610.wqtZ0P", "making sure nobody sees half-applied updates, by queueing them"),
    ("PRC@1712870400.0Rz5Ex", "copying chosen items from a project into the organisation's shared copy"),
    # services
    ("SRV@1712870400.Ij6Kl6", "offers checks of a single file or of the whole model to callers"),
    ("SRV@1712870400.e5MCiF", "reads and merges settings files from the organisation and project levels"),
    ("SRV@1712870400.Qr8St8", "search, lookup and counts over what is in the model"),
    # artifacts
    ("ART@1712870400.YsLpM8", "the version-controlled folder of markdown files holding the whole model"),
    ("ART@1780656477.tkNvK_", "the SQLCipher file behind the confidential safety knowledge base"),
    ("ART@1780547760.NKi5Hz", "a folder whose path says which collection an item belongs to"),
    # goals
    ("GOL@1712870400.Lm2Bn2", "many teams drafting at once and publishing through explicit steps"),
    ("GOL@1776628205.kCcPph", "decisions and patterns from one project should be usable in others"),
    # application interfaces
    ("AIF@1712870400.KxvY-B", "commands typed in a terminal, for scripts and pipelines"),
    ("AIF@1712870400.wuleEe", "the protocol through which AI agents call into the repository"),
    ("AIF@1776149386.Ua50xU", "browser pages for exploring and editing the model"),
    # stakeholders
    ("STK@1712870400.4oprPM", "the person running deployment pipelines and infrastructure"),
    ("STK@1712870400.Zp8Lm4", "the person who decides priorities and checks what is being built against needs"),
    # drivers
    ("DRV@1712870400.Ui5Op3", "systems keep growing and depend on each other more and more"),
    ("DRV@1780655839.52-qYT", "startups and personal projects lack experts for compliance and risk work"),
    # technology nodes
    ("NOD@1712870400.4EFX7z", "the laptop where someone runs the tools locally"),
    ("NOD@1786915205.Yx71j_C", "the single docker process serving the web UI, the API and the agent endpoints"),
    ("NOD@1786915451.IwBEhEm", "mounted storage for the home folder that holds the keys"),
    # system software
    ("SSW@1712870400.o7a0ad", "the interpreter all the tooling runs on"),
    ("SSW@1780656477.OCX11y", "the operating system's secret storage for the encryption key"),
    ("SSW@1712870400.xVrBYD", "the jar that draws pictures from text source"),
    # principles
    ("PRI@1780655839.YwzivI", "harm prevention cannot be traded away for cost or schedule"),
    ("PRI@1780655839.hVWaYW", "safety analyses are encrypted and restricted unless deliberately published"),
    ("PRI@1780220699.kWgVgr", "people in the browser and AI tools work with the same meanings and the same safeguards"),
    # capabilities
    (
        "CAP@1784482403.pLMHKe",
        "capturing and organising what we know about our systems as a checkable, searchable model",
    ),
    ("CAP@1784482442.0kQIHh", "answering questions from the model and drawing pictures of it: coverage and impact"),
    # courses of action
    ("COA@1784483697.FI0Xbj", "using the product to describe its own design before shipping features"),
)
