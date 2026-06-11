#!/usr/bin/env python3
"""Verify the GoDaNang `villas` table schema matches what the apartment agent writes.

This script does NOT write any data — it only introspects the live table
and compares its columns against the columns the apartment agent's
`_build_insert_payload` and `_build_update_payload` functions produce.

Run after the agent has been deployed to a new environment, or any time
the GoDaNang schema is migrated. Output:

- OK     — column exists with a compatible type/nullability
- WARN   — column exists but type or nullability differs from the agent's
           write; the agent will still attempt to write the value, but
           the server may reject it
- MISSING — the column the agent writes does not exist on the server
- UNEXPECTED — the server has a column the agent never writes; left
           alone, ignored

Usage:

    python scripts/verify_godanang_schema.py
    GODANANG_SUPABASE_URL=https://x.supabase.co \\
      GODANANG_SUPABASE_SERVICE_KEY=ey... \\
      python scripts/verify_godanang_schema.py

The script exits 0 if all agent-written columns are present, 1 if any
are missing.
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any, Optional

import httpx

# Columns the apartment agent writes. The expected type is what
# _build_insert_payload builds in Python — PostgREST will coerce some
# values (e.g. int → bigint) but a type mismatch is a strong signal
# of a schema drift.
AGENT_WRITES: list[dict[str, Any]] = [
    {"name": "slug", "py_type": "str", "nullable": False, "max_len": 200},
    {"name": "name", "py_type": "str", "nullable": False, "max_len": 500},
    {"name": "type", "py_type": "str", "nullable": False, "max_len": 50},
    {"name": "area", "py_type": "str", "nullable": True, "max_len": 200},
    {"name": "capacity", "py_type": "int", "nullable": False},
    {"name": "price", "py_type": "int", "nullable": False},
    {"name": "price_label", "py_type": "str", "nullable": True, "max_len": 200},
    {"name": "description", "py_type": "str", "nullable": True},
    {"name": "amenities", "py_type": "list[str]", "nullable": True},
    {"name": "images", "py_type": "list[str]", "nullable": True},
    {"name": "status", "py_type": "str", "nullable": False, "max_len": 50},
]

# Columns the agent reads via find_existing_villa.
AGENT_READS: list[dict[str, Any]] = [
    {"name": "id"},
    {"name": "images"},
    {"name": "description"},
    {"name": "slug"},
    {"name": "name"},
    {"name": "area"},
    {"name": "price"},
    {"name": "created_at"},
]

# Map Python types to the PostgREST-returned data_type strings. This is
# a soft check — Postgres often accepts multiple aliases.
PY_TO_PG_TYPES: dict[str, tuple[str, ...]] = {
    "str": ("text", "character varying", "varchar", "char"),
    "int": (
        "integer",
        "bigint",
        "smallint",
        "numeric",
        "double precision",
        "real",
    ),
    "list[str]": ("text[]", "jsonb", "json", "ARRAY"),
}


def _check_type(py_type: str, pg_data_type: str) -> tuple[bool, str]:
    allowed = PY_TO_PG_TYPES.get(py_type, ())
    if pg_data_type in allowed:
        return True, "ok"
    # Text→varchar coercion is silent and benign.
    if py_type == "str" and pg_data_type.startswith("character varying"):
        return True, "ok"
    return False, f"agent writes python {py_type}, server has {pg_data_type}"


async def fetch_columns(
    supabase_url: str,
    service_key: str,
    table: str = "villas",
) -> list[dict[str, Any]]:
    """Query information_schema.columns for a table.

    PostgREST does not expose information_schema by default, so we
    instead query the table itself with `limit=0` and read the
    PostgREST-served `Content-Profile` header. If that fails we fall
    back to a HEAD probe that lists the column names from
    `Accept: application/vnd.pgrst.object+json` deserialization.

    For most Supabase projects the easiest path is a `select *` with
    limit 0 and a header inspection — but to keep this script
    dependency-free we just call a small RPC. The cleanest portable
    approach: call /rest/v1/villas?limit=0 and parse the empty
    response shape from the Link header... no, that does not give
    column names either.

    Pragmatic move: query the PostgREST OpenAPI spec endpoint
    `/rest/v1/`. It returns a JSON document with the table schema
    including every column and its PostgreSQL data type. This
    endpoint requires the `apikey` header but no special perms.
    """
    openapi_url = f"{supabase_url.rstrip('/')}/rest/v1/"
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Accept": "application/openapi+json",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(openapi_url, headers=headers)
        resp.raise_for_status()
        spec = resp.json()

    definitions = spec.get("definitions", {})
    table_def = definitions.get(table) or definitions.get(f"public.{table}")
    if not table_def:
        raise RuntimeError(
            f"Table '{table}' not found in PostgREST OpenAPI spec. "
            f"Available: {sorted(definitions.keys())[:10]}..."
        )

    properties = table_def.get("properties", {})
    required = set(table_def.get("required", []))
    columns: list[dict[str, Any]] = []
    for col_name, col_spec in properties.items():
        # OpenAPI 3.0 → {"type": "string"} or {"type": "array", "items": {...}}
        # PostgREST exposes extra metadata via `x-` prefixed keys.
        raw_type = col_spec.get("format") or col_spec.get("type") or "unknown"
        # PostgREST often surfaces the real Postgres type in x-postgres-type
        # or as a description. Best-effort.
        pg_type = (
            col_spec.get("x-postgres-type")
            or col_spec.get("description")
            or raw_type
        )
        if isinstance(col_type_spec := col_spec.get("items"), dict):
            inner = col_type_spec.get("format") or col_type_spec.get("type") or "unknown"
            pg_type = f"ARRAY<{inner}>"
        columns.append(
            {
                "name": col_name,
                "data_type": str(pg_type),
                "is_nullable": "YES" if col_name not in required else "NO",
            }
        )
    return columns


async def main_async() -> int:
    supabase_url = os.getenv("GODANANG_SUPABASE_URL", "").strip()
    service_key = os.getenv("GODANANG_SUPABASE_SERVICE_KEY", "").strip()
    if not supabase_url or not service_key:
        print(
            "ERROR: GODANANG_SUPABASE_URL and GODANANG_SUPABASE_SERVICE_KEY "
            "must be set in env",
            file=sys.stderr,
        )
        return 2

    try:
        columns = await fetch_columns(supabase_url, service_key, "villas")
    except Exception as exc:
        print(f"ERROR: failed to introspect villas table: {exc}", file=sys.stderr)
        return 2

    by_name = {c["name"]: c for c in columns}

    print(f"villas table — {len(columns)} columns on server\n")
    status_counts = {"ok": 0, "warn": 0, "missing": 0, "unexpected": 0}
    for col in columns:
        print(f"  {col['name']:30} {col['data_type']:30} nullable={col['is_nullable']}")

    print("\nAgent writes (must all be present):")
    rc = 0
    for w in AGENT_WRITES:
        name = w["name"]
        if name not in by_name:
            print(f"  MISSING  {name:30} — agent writes this column but it does not exist on server")
            status_counts["missing"] += 1
            rc = 1
            continue
        server = by_name[name]
        type_ok, type_msg = _check_type(w["py_type"], server["data_type"])
        if not type_ok:
            print(
                f"  WARN     {name:30} {type_msg}"
            )
            status_counts["warn"] += 1
            continue
        if w["nullable"] is False and server["is_nullable"] == "YES":
            print(
                f"  WARN     {name:30} agent requires NOT NULL, server allows NULL"
            )
            status_counts["warn"] += 1
            continue
        print(f"  OK       {name:30} {w['py_type']} → {server['data_type']}")
        status_counts["ok"] += 1

    print("\nAgent reads (must all be present):")
    for r in AGENT_READS:
        name = r["name"]
        if name not in by_name:
            print(f"  MISSING  {name:30} — agent reads this column but it does not exist")
            status_counts["missing"] += 1
            rc = 1
        else:
            print(f"  OK       {name:30}")

    print("\nServer columns the agent does not write (informational):")
    written_or_read = {w["name"] for w in AGENT_WRITES} | {r["name"] for r in AGENT_READS}
    for c in columns:
        if c["name"] not in written_or_read:
            print(f"  UNEXPECTED  {c['name']:30} {c['data_type']}")
            status_counts["unexpected"] += 1

    print(
        f"\nSummary: ok={status_counts['ok']} warn={status_counts['warn']} "
        f"missing={status_counts['missing']} unexpected={status_counts['unexpected']}"
    )
    if rc != 0:
        print("\nSchema drift detected. The agent will fail to insert/update rows.")
        print("Either: (a) add the missing columns to villas, or (b) update")
        print("sync._build_insert_payload / _build_update_payload in this repo.")
    return rc


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    sys.exit(main())
