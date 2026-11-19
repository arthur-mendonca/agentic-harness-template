"""Create, inspect, resume and update managed SDD tasks."""

import argparse
import json
from pathlib import Path
import sys

from harness.config import discover_root, load_config, read_json
from harness.findings import FindingStore
from harness.migration import require_tasks_ready
from harness.sdd_policy import MODES, choose_mode, parse_risks
from harness.specs import KINDS
from harness.tasks import STATES, TaskStore


def _risk_arguments(parser):
    parser.add_argument("--assessed-low", action="store_true", help="Confirm low impact in all unlisted risk dimensions")
    parser.add_argument("--risk", action="append", default=[], metavar="FACTOR=LEVEL",
                        help="Record a risk assessment. Levels are none, low, material and unknown")


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m harness sdd", description=__doc__,
        epilog="auto selects lite or full; off creates no task documents. validate/trace check structure; verify records agent assessments and evidence, not proof of business behavior. Prepare legacy controls with python -m harness update --project PATH.",
    )
    parser.add_argument("--project", help="Exact project root")
    commands = parser.add_subparsers(dest="command", required=True)
    new = commands.add_parser("new", help="Start work in the selected mode")
    new.add_argument("--mode", choices=MODES, help="Explicit mode overrides project policy; auto selects lite/full")
    new.add_argument("--title", required=True)
    _risk_arguments(new)
    finding = commands.add_parser("finding", help="Record an agent-selected out-of-scope finding")
    finding.add_argument("--input", type=Path, required=True, help="JSON finding with evidence and future action")
    finding.add_argument("--mode", choices=("off", "lite", "full"))
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
    policy = commands.add_parser("review-policy", help="Record an explicit per-task independent review decision")
    policy.add_argument("id")
    policy.add_argument("mode", choices=("required", "optional"))
    policy.add_argument("--reason", required=True)
    policy.add_argument("--decided-by", required=True)
    validate = commands.add_parser("validate", help="Validate the full task Markdown contract")
    tracing = commands.add_parser("trace", help="Show requirements, criteria, planned checks and steps")
    verify = commands.add_parser("verify", help="Inspect criterion evidence or record an agent assessment")
    verify.add_argument("--assessment", type=Path, help="JSON assessment to record")
    allocate = commands.add_parser("allocate-id", help="Reserve a document identifier within a full task")
    awaiting = commands.add_parser("await-decision", help="Record that a specification needs a substantive decision")
    approve = commands.add_parser("approve", help="Confirm a specification revision in an interactive terminal")
    for command in (validate, tracing, verify, allocate, awaiting, approve):
        command.add_argument("id")
    allocate.add_argument("kind", choices=KINDS)
    for command in (new, finding, listing, status, resume, mode, change, policy, validate, tracing, verify, allocate, awaiting, approve):
        command.add_argument("--project", default=argparse.SUPPRESS, help="Exact project root")
    args = parser.parse_args(argv)
    try:
        result = _dispatch(args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.command in ("validate", "trace"):
            return 0 if result["valid"] else 1
        if args.command == "verify":
            return 0 if result["ready"] else 1
        return 0
    except (OSError, ValueError) as exc:
        print(f"SDD error: {exc}", file=sys.stderr)
        return 2


def _dispatch(args):
    if args.command == "finding" and args.mode == "off":
        return {"status": "ignored", "reason": "Mode off keeps findings in the conversation"}
    if args.command == "new" and args.mode == "off":
        mode, reason = choose_mode("auto", args.mode, parse_risks(args.risk), assessed_low=args.assessed_low)
        return {"mode": mode, "mode_reason": reason, "path": None}
    root = discover_root(args.project)
    if args.command == "finding":
        config = load_config(root)
        mode = args.mode or config.get("sdd", {}).get("mode", "auto")
        if mode == "off":
            return FindingStore(root).record(None, mode=mode)
        require_tasks_ready(root, config)
        return FindingStore(root).record(read_json(args.input), mode=mode)
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
    if args.command == "review-policy":
        return store.set_review_policy(args.id, args.mode, args.reason, args.decided_by)
    if args.command in ("validate", "trace"):
        contract = store.contract(args.id)
        if args.command == "validate":
            contract.pop("requirements")
        return contract
    if args.command == "verify":
        if args.assessment is None:
            return store.verification(args.id)
        return store.record_assessment(args.id, read_json(args.assessment))
    if args.command == "allocate-id":
        return store.allocate_id(args.id, args.kind)
    if args.command == "await-decision":
        return store.await_decision(args.id)
    if args.command == "approve":
        return store.approve(args.id)
    return store.set_status(args.id, args.status, args.evidence, args.manual_evidence)
