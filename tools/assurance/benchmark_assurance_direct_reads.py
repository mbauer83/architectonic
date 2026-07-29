"""Benchmark prospective direct assurance browse and search queries.

The benchmark uses an encrypted SQLCipher database, one read connection per
worker, and the per-analysis/TLP query shape designed for the assurance GUI.
It writes only to a temporary directory and leaves no plaintext index.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import statistics
import tempfile
import time
from pathlib import Path
from typing import Any

import sqlcipher3  # type: ignore[import-untyped]

_KEY = "assurance-benchmark-key"
_NODE_TYPES = (
    "loss",
    "hazard",
    "control-structure-node",
    "control-action",
    "unsafe-control-action",
    "loss-scenario",
    "assurance-constraint",
    "risk",
    "incident",
    "corrective-action",
    "obligation",
)
_TLPS = ("TLP:WHITE", "TLP:GREEN", "TLP:AMBER", "TLP:RED")


def _connect(path: Path) -> Any:
    conn = sqlcipher3.connect(str(path))
    conn.execute(f"PRAGMA key = '{_KEY}'")
    conn.row_factory = sqlcipher3.Row
    return conn


def _create_store(path: Path, node_count: int, analysis_count: int) -> None:
    conn = _connect(path)
    conn.executescript(
        """
        PRAGMA journal_mode = WAL;
        PRAGMA synchronous = NORMAL;
        CREATE TABLE assurance_nodes (
            node_id TEXT PRIMARY KEY,
            analysis_id TEXT NOT NULL,
            node_type TEXT NOT NULL,
            name TEXT NOT NULL,
            status TEXT NOT NULL,
            tlp TEXT NOT NULL,
            content_text TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX idx_nodes_analysis_browse
            ON assurance_nodes(analysis_id, node_type, created_at);
        CREATE INDEX idx_nodes_analysis_status
            ON assurance_nodes(analysis_id, status);
        """
    )
    rows = (
        (
            f"NOD@{index:08d}",
            f"ANL@{index % analysis_count:04d}",
            _NODE_TYPES[index % len(_NODE_TYPES)],
            f"Assurance finding {index} subsystem {index % 97}",
            ("draft", "active", "accepted")[index % 3],
            _TLPS[index % len(_TLPS)],
            (
                f"Evidence and scenario narrative for subsystem {index % 97}; "
                f"control path {index % 211}; token-{index % 503}."
            ),
            f"2026-06-{(index % 20) + 1:02d}T00:00:00Z",
        )
        for index in range(node_count)
    )
    conn.executemany(
        """
        INSERT INTO assurance_nodes
            (node_id, analysis_id, node_type, name, status, tlp, content_text, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()


def _measure_worker(path: Path, worker: int, iterations: int) -> dict[str, list[float]]:
    conn = _connect(path)
    measurements = {"browse": [], "search": [], "count": []}
    visible_tlps = ("TLP:WHITE", "TLP:GREEN", "TLP:AMBER")
    for iteration in range(iterations):
        analysis_id = f"ANL@{(worker * iterations + iteration) % 100:04d}"
        started = time.perf_counter()
        conn.execute(
            """
            SELECT node_id, node_type, name, status, tlp
            FROM assurance_nodes
            WHERE analysis_id = ? AND node_type = ? AND tlp IN (?, ?, ?)
            ORDER BY created_at LIMIT 100
            """,
            (analysis_id, _NODE_TYPES[iteration % len(_NODE_TYPES)], *visible_tlps),
        ).fetchall()
        measurements["browse"].append((time.perf_counter() - started) * 1000)

        started = time.perf_counter()
        term = f"%token-{iteration % 503}%"
        conn.execute(
            """
            SELECT node_id, node_type, name, status, tlp
            FROM assurance_nodes
            WHERE analysis_id = ? AND tlp IN (?, ?, ?)
              AND (name LIKE ? OR content_text LIKE ?)
            ORDER BY created_at LIMIT 50
            """,
            (analysis_id, *visible_tlps, term, term),
        ).fetchall()
        measurements["search"].append((time.perf_counter() - started) * 1000)

        started = time.perf_counter()
        conn.execute(
            """
            SELECT node_type, COUNT(*)
            FROM assurance_nodes
            WHERE analysis_id = ? AND tlp IN (?, ?, ?)
            GROUP BY node_type
            """,
            (analysis_id, *visible_tlps),
        ).fetchall()
        measurements["count"].append((time.perf_counter() - started) * 1000)
    conn.close()
    return measurements


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(int(len(ordered) * fraction), len(ordered) - 1)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nodes", type=int, default=100_000)
    parser.add_argument("--analyses", type=int, default=100)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--iterations", type=int, default=100)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="assurance-benchmark-") as temp_dir:
        path = Path(temp_dir) / "assurance.db"
        started = time.perf_counter()
        _create_store(path, args.nodes, args.analyses)
        build_seconds = time.perf_counter() - started
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            results = list(
                pool.map(
                    lambda worker: _measure_worker(path, worker, args.iterations),
                    range(args.workers),
                )
            )

    print(
        f"dataset nodes={args.nodes} analyses={args.analyses} "
        f"workers={args.workers} requests={args.workers * args.iterations}"
    )
    print(f"encrypted store build: {build_seconds:.2f}s")
    for operation in ("browse", "search", "count"):
        values = [value for result in results for value in result[operation]]
        print(
            f"{operation:>6}: median={statistics.median(values):.3f}ms "
            f"p95={_percentile(values, 0.95):.3f}ms "
            f"p99={_percentile(values, 0.99):.3f}ms "
            f"max={max(values):.3f}ms"
        )


if __name__ == "__main__":
    main()
