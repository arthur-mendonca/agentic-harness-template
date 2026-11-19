"""Create, inspect, resume and update managed SDD tasks."""

import argparse
import json
import sys

from harness.config import discover_root, load_config
from harness.migration import require_tasks_ready
from harness.sdd_policy import MODES, choose_mode, parse_risks
from harness.specs import KINDS
from harness.tasks import STATES, TaskStore


def _risk_arguments(parser):
    parser.add_argument("--assessed-low", action="store_true", help="Confirm low impact in all unlisted risk dimensions")
    parser.add_argument("--risk", action="append", default=[], metavar="FACTOR=LEVEL",
                        help="Record a risk assessment. Levels are none, low, material and unknown")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m harness sdd", description=__doc__)
    parser.add_argument("--project", help="Exact project root")
    commands = parser.add_subparsers(dest="command", required=True)
    new = commands.add_parser("new", help="Start work in the selected mode")
    new.add_argument("--mode", choices=MODES)
    new.add_argument("--title", required=True)
    _risk_arguments(new)
    listing = commands.add_parser("list", help="List managed tasks")
    status = commands.add_parser("status", help="Read task metadata")
    status.add_argument("id")
    resume = commands.add_parser("resume", help="Resume an existing task and recover interrupted transitions")
    resume.add_argument("id")
    mode = commands.add_parser("mode", help="Change the operating mode of an existing task")
    mode.add_argument("id")
    mode.add_argument("mode", choices=MODES)
    _risk_arguments(mode)
    change = commands.add_parser("set-status", help="Record the execution state of an existing task")
    change.add_argument("id")
    change.add_argument("status", choices=STATES)
    change.add_argument("--evidence", action="append", default=[], metavar="PATH")
    change.add_argument("--manual-evidence", action="append", default=[], metavar="PATH")
    validate = commands.add_parser("validate", help="Validate the full task Markdown contract")
    tracing = commands.add_parser("trace", help="Show requirements, criteria, planned checks and steps")
    allocate = commands.add_parser("allocate-id", help="Reserve a document identifier within a full task")
    awaiting = commands.add_parser("await-decision", help="Record that a specification needs a substantive decision")
    approve = commands.add_parser("approve", help="Confirm a specification revision in an interactive terminal")
    for command in (validate, tracing, allocate, awaiting, approve):
        command.add_argument("id")
    allocate.add_argument("kind", choices=KINDS)
    for command in (new, listing, status, resume, mode, change, validate, tracing, allocate, awaiting, approve):
        command.add_argument("--project", default=argparse.SUPPRESS, help="Exact project root")
    args = parser.parse_args(argv)
    try:
        result = _dispatch(args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if args.command in ("validate", "trace") and not result["valid"] else 0
    except (OSError, ValueError) as exc:
        print(f"SDD error: {exc}", file=sys.stderr)
        return 2


def _dispatch(args):
    if args.command == "new" and args.mode == "off":
        mode, reason = choose_mode("auto", args.mode, parse_risks(args.risk), assessed_low=args.assessed_low)
        return {"mode": mode, "mode_reason": reason, "path": None}
    root = discover_root(args.project)
    store = TaskStore(root)
    if args.command in ("new", "mode"):
        config = load_config(root)
        configured = config.get("sdd", {}).get("mode", "auto")
        mode, reason = choose_mode(configured, args.mode, parse_risks(args.risk), assessed_low=args.assessed_low)
        if args.command == "mode":
            return store.change_mode(args.id, mode, reason)
        if mode == "off":
            return {"mode": mode, "mode_reason": reason, "path": None}
        require_tasks_ready(root, config)
        return store.new(args.title, mode, reason)
    if args.command == "list":
        return store.list()
    if args.command == "status":
        return store.status(args.id)
    if args.command == "resume":
        return store.resume(args.id)
    if args.command in ("validate", "trace"):
        contract = store.contract(args.id)
        if args.command == "validate":
            contract.pop("requirements")
        return contract
    if args.command == "allocate-id":
        return store.allocate_id(args.id, args.kind)
    if args.command == "await-decision":
        return store.await_decision(args.id)
    if args.command == "approve":
        return store.approve(args.id)
    return store.set_status(args.id, args.status, args.evidence, args.manual_evidence)
