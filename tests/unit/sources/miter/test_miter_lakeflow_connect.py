"""Tests for ``MiterLakeflowConnect``.

Default mode runs against the in-process source simulator described by
``source_simulator/specs/miter/`` — no credentials, no network.

Live mode against the real API::

    CONNECTOR_TEST_MODE=live \\
      CONNECTOR_TEST_CONFIG_JSON='{"api_token":"...",
                                   "base_url":"https://api.staging.miter.com/api/v2"}' \\
      pytest tests/unit/sources/miter/ -v

``base_url`` must be supplied for a staging token — the connector defaults
to the production root, which rejects a staging token with 401.

Two test classes, because the connector serves both read paths:

``TestMiterConnector``
    ``is_partitioned`` is true for every Miter table, so the standard
    suite routes all read coverage through ``get_partitions`` /
    ``read_partition`` and skips ``read_table``.

``TestMiterSequentialFallback``
    Re-runs the same suite with partitioning disabled, which is the only
    way to reach ``read_table`` — the sliding-window fallback the
    interface still requires (``LakeflowConnect.read_table`` is abstract)
    and that the framework uses when partitioned reads are off.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from databricks.labs.community_connector.sources.miter.miter import (
    MiterLakeflowConnect,
)
from databricks.labs.community_connector.sources.miter.miter_schemas import (
    LEDGER_LINE_ITEMS,
    SUPPORTED_TABLES,
)
from databricks.labs.community_connector.source_simulator import MODE_SIMULATE
from tests.unit.sources.test_partition_suite import (
    SupportsPartitionedStreamTests,
)
from tests.unit.sources.test_suite import (
    LakeflowConnectTests,
    _resolve_env_mode_for_simulator,
)

# Stand-in credentials for simulate mode. The simulator never validates
# them; it matches on URL *path* only, so ``base_url`` simply has to end
# in the ``/api/v2`` root that the spec paths assume.
_REPLAY_CONFIG = {
    "api_token": "miter-simulator-fake-token",
    "base_url": "https://api.staging.miter.com/api/v2",
}


class TestMiterConnector(LakeflowConnectTests, SupportsPartitionedStreamTests):
    connector_class = MiterLakeflowConnect
    simulator_source = "miter"
    sample_records = 50
    replay_config = _REPLAY_CONFIG


class _MiterSequentialReader(MiterLakeflowConnect):
    """Miter with partitioning switched off.

    ``read_table`` is unreachable while ``is_partitioned`` returns true,
    so the suite would otherwise never exercise the connector's
    sliding-window read, its record cap, or its empty-window skip.
    """

    def is_partitioned(self, table_name: str) -> bool:
        return False


class TestMiterSequentialFallback(LakeflowConnectTests):
    connector_class = _MiterSequentialReader
    simulator_source = "miter"
    sample_records = 200
    replay_config = _REPLAY_CONFIG

    # One window wide enough to span the whole corpus, so the suite's
    # single-call read tests (notably the column-coverage invariant, which
    # samples exactly one ``read_table`` call) see every record. The
    # window-stepping behaviour is covered separately below with a
    # deliberately narrow window.
    #
    # ``page_size: 2`` forces every one of those reads through the
    # ``data.next_page`` cursor loop rather than a single page. It is left
    # off ``ledger_line_items`` on purpose: that table's options also
    # govern the unbounded parent-listing call, and the simulator's
    # future-record clones reuse their template's ``id``, so a cursor walk
    # over the unbounded list would stall on a repeated cursor.
    table_configs = {
        table: (
            {"window_seconds": "31536000"}
            if table == LEDGER_LINE_ITEMS
            else {"window_seconds": "31536000", "page_size": "2"}
        )
        for table in SUPPORTED_TABLES
    }

    # Tables whose ``read_table`` walk yields each record exactly once.
    # ``ledger_line_items`` is excluded: it fans out over parent ledger
    # entries, and the simulator serves every parent the same corpus, so
    # ids legitimately repeat across parents.
    _WALKABLE_TABLES = tuple(t for t in SUPPORTED_TABLES if t != LEDGER_LINE_ITEMS)

    def test_read_table_walk_is_lossless_and_converges(self):
        """A narrow-window, one-record-per-batch walk loses nothing.

        Drives the paths the wide-window suite tests cannot reach: the
        ``max_records_per_batch`` early stop, resumption from the returned
        cursor, and the empty-window skip that jumps the offset forward to
        the next row that actually exists instead of stepping through every
        intervening window.
        """
        self._require_simulate()
        narrow = {"window_seconds": "86400", "max_records_per_batch": "1"}
        errors: List[str] = []
        for table in self._WALKABLE_TABLES:
            expected = self._read_all_ids(table, self._opts(table))
            assert expected, (
                f"[{table}] wide-window read returned nothing — corpus or "
                "spec is misaligned, fix that before reading this failure."
            )
            walked = self._walk(table, narrow, errors)
            if walked is None:
                continue
            if set(walked) != expected or len(walked) != len(expected):
                errors.append(
                    f"[{table}] narrow-window walk did not return every record "
                    f"exactly once.\n"
                    f"  missing: {sorted(expected - set(walked))}\n"
                    f"  extra:   {sorted(set(walked) - expected)}\n"
                    f"  duplicated: {sorted({i for i in walked if walked.count(i) > 1})}\n"
                    "  Fix: read_table() must advance its offset strictly past "
                    "the last record it emitted, and must not re-emit the "
                    "boundary row on the next call."
                )
        if errors:
            pytest.fail("\n\n".join(errors))

    def test_cursor_pagination_returns_every_page(self):
        """One record per page yields the same set as a single page.

        Miter's ``data.next_page`` is an opaque cursor carrying the last
        record's id, not an offset, so a mis-read cursor silently truncates
        or re-serves a page instead of erroring.
        """
        self._require_simulate()
        table = "ledger_accounts"
        base = self._opts(table)
        single_page = self._read_all_ids(table, {**base, "page_size": "1000"})
        assert len(single_page) > 1, (
            f"[{table}] corpus has {len(single_page)} record(s) — too few to "
            "paginate; add records to the simulator corpus."
        )
        paged = self._read_all_ids(table, {**base, "page_size": "1"})
        assert paged == single_page, (
            f"[{table}] a one-record-per-page walk returned a different set "
            f"than a single-page read.\n"
            f"  missing when paged: {sorted(single_page - paged)}\n"
            f"  extra when paged:   {sorted(paged - single_page)}\n"
            "  Fix: the connector must replay data.next_page verbatim as "
            "'page' and stop only when it comes back null."
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _require_simulate(self) -> None:
        """Both walks below assert on the *fixed* corpus.

        A live tenant's ledger volume is whatever it happens to be — the
        staging tenant these were written against holds no ledger accounts
        at all — so the assertions only mean something against the
        simulator.
        """
        if _resolve_env_mode_for_simulator(self.simulator_source) != MODE_SIMULATE:
            pytest.skip("Corpus-shaped invariant only enforced in simulate mode")

    def _read_all_ids(self, table: str, opts: Dict[str, Any]) -> set:
        iterator, _ = self.connector.read_table(table, {}, opts)
        return {rec["id"] for rec in iterator}

    def _walk(
        self, table: str, opts: Dict[str, Any], errors: List[str]
    ) -> List[str] | None:
        """Loop ``read_table`` to convergence, returning every id emitted."""
        seen: List[str] = []
        offset: Dict[str, Any] = {}
        for i in range(self.read_termination_max_iterations):
            iterator, next_offset = self.connector.read_table(table, offset, opts)
            seen.extend(rec["id"] for rec in iterator)
            if next_offset == offset:
                return seen
            offset = next_offset
        errors.append(
            f"[{table}] narrow-window walk did not converge in "
            f"{self.read_termination_max_iterations} iterations "
            f"(last offset: {offset}).\n"
            "  Fix: an empty window must skip ahead to the next row that "
            "exists, and the final offset must settle on the init-time cap."
        )
        return None
