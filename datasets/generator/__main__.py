"""Generate the TraceWeave attack scenario as plain log files.

This module deliberately has no application/engine imports and performs no
database I/O.  It is useful both for demos and for repeatable integration
fixtures.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

BASE = datetime(2026, 1, 15, 8, 0, tzinfo=timezone.utc)


def _stamp(minutes: int, skew: int) -> str:
    return (BASE + timedelta(minutes=minutes, seconds=skew)).isoformat().replace("+00:00", "Z")


def _event(event_id: str, minutes: int, kind: str, **values: Any) -> dict[str, Any]:
    return {"id": event_id, "timestamp": _stamp(minutes, _event.skew), "event": kind, **values}


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def generate(output: str | Path = "datasets/generated", *, clock_skew: int = 0,
             drop_source_window: bool = False, identity_conflict: bool = False,
             benign_noise: bool = True) -> Path:
    """Write scenario logs and ground truth to *output*, returning its path."""
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    _event.skew = int(clock_skew)

    auth = [
        _event("auth-001", 0, "credential_stuffing", username="alice", src_ip="203.0.113.77", success=False, attempts=18),
        _event("auth-002", 12, "login", username="alice", src_ip="203.0.113.77", success=True, mfa=False, new_ip=True),
        _event("auth-003", 13, "token_created", username="alice", src_ip="203.0.113.77", token_id="tok-7f3a"),
    ]
    if identity_conflict:
        auth.append(_event("auth-004", 14, "login", username="alice", account="a.alice", src_ip="203.0.113.77", success=True, mfa=False, identity_conflict=True))

    audit = [
        _event("audit-001", 15, "role_escalation", actor="alice", from_role="user", to_role="admin", target="alice"),
        _event("audit-002", 17, "discovery", actor="alice", action="list_users_and_roles"),
        _event("audit-003", 20, "bulk_export", actor="alice", object="customer_records", records=250000),
        _event("audit-004", 23, "rare_ip_transfer", actor="alice", src_ip="203.0.113.77", destination="198.51.100.42", bytes=987654321),
        _event("audit-005", 27, "log_deletion", actor="alice", target="auth.log", deleted_records=42),
    ]
    if benign_noise:
        audit += [_event("noise-001", 5, "health_check", actor="system", target="api"),
                  _event("noise-002", 10, "scheduled_report", actor="reporter", target="daily_summary"),
                  _event("noise-003", 25, "password_rotation", actor="bob", target="bob")]

    network = [
        {"id": "net-001", "timestamp": _stamp(12, clock_skew), "src_ip": "203.0.113.77", "dst_ip": "10.0.0.10", "protocol": "https", "bytes": 1842},
        {"id": "net-002", "timestamp": _stamp(20, clock_skew), "src_ip": "203.0.113.77", "dst_ip": "10.0.0.10", "protocol": "https", "bytes": 7342},
        {"id": "net-003", "timestamp": _stamp(23, clock_skew), "src_ip": "203.0.113.77", "dst_ip": "198.51.100.42", "protocol": "https", "bytes": 987654321},
    ]
    if drop_source_window:
        network = [row for row in network if row["id"] != "net-002"]

    _write_jsonl(root / "auth.jsonl", auth)
    _write_jsonl(root / "application.audit", audit)
    with (root / "network.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "timestamp", "src_ip", "dst_ip", "protocol", "bytes"])
        writer.writeheader()
        writer.writerows(network)
    truth = {
        "scenario": "credential-compromise-to-exfiltration",
        "clock_skew_seconds": int(clock_skew),
        "options": {"drop_source_window": drop_source_window, "identity_conflict": identity_conflict, "benign_noise": benign_noise},
        "stages": ["credential_stuffing", "successful_new_ip_no_mfa_login", "token_creation", "role_escalation", "discovery", "bulk_export", "rare_ip_transfer", "log_deletion"],
        "attacker": {"user": "alice", "source_ip": "203.0.113.77", "destination_ip": "198.51.100.42"},
        "sources": ["auth.jsonl", "application.audit", "network.csv"],
    }
    (root / "ground_truth.json").write_text(json.dumps(truth, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return root


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate deterministic offline TraceWeave scenario logs")
    parser.add_argument("--output", "--output-dir", dest="output", default="datasets/generated")
    parser.add_argument("--clock-skew", type=int, default=0, metavar="N", help="shift all timestamps by N seconds")
    parser.add_argument("--drop-source-window", action="store_true", help="omit a network observation window")
    parser.add_argument("--identity-conflict", action="store_true", help="include conflicting account identity evidence")
    parser.add_argument("--benign-noise", action="store_true", help="include routine unrelated events (the default)")
    parser.add_argument("--no-benign-noise", action="store_true", help="omit unrelated routine events")
    args = parser.parse_args()
    path = generate(args.output, clock_skew=args.clock_skew, drop_source_window=args.drop_source_window,
                    identity_conflict=args.identity_conflict, benign_noise=not args.no_benign_noise)
    print(f"wrote scenario logs to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
