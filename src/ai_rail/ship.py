from __future__ import annotations

import argparse
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass
class ShipContext:
    active: Callable[[], dict[str, Any] | None]
    append_flag: Callable[[list[str], bool, str], None]
    branch_exists_remotely: Callable[[str], bool]
    can_update_stale_default_node_check: Callable[[list[Any], str, str], bool]
    cfg: Callable[[], dict[str, Any]]
    check_block_reason: Callable[[], str | None]
    check_output_mentions_missing_npm_script: Callable[[str, str], bool]
    checks_path: Callable[[], Path]
    checks_result: Callable[[], str]
    cmd_done: Callable[[list[str]], int]
    configured_check_commands: Callable[..., list[str]]
    configured_default_branch: Callable[[], str]
    current_branch: Callable[[], str]
    delegate: Callable[..., int]
    git_safety_preflight: Callable[[], dict[str, Any]]
    git_state_blocks_new_work: Callable[[dict[str, Any]], bool]
    git_ref_exists: Callable[[str], bool]
    local_py: Callable[[], Path]
    mark_project_issue_completed: Callable[[Any, str | None, str | None], bool]
    missing_npm_check_recovery: Callable[[list[Any], str], tuple[str, str] | None]
    npm_run_script: Callable[[str], str | None]
    package_json_scripts: Callable[[], dict[str, Any]]
    print_ship_phase_progress: Callable[[], None]
    rail_dir: Callable[[], Path]
    rail_icon: Callable[[str], str]
    rail_print: Callable[[str], None]
    rail_runtime_tracked_on_branch: Callable[[str], bool]
    refresh_review_and_check_artifacts: Callable[[], None]
    run: Callable[..., subprocess.CompletedProcess[str]]
    validate_verify_snapshot: Callable[..., tuple[bool, str]]
    verified_path: Callable[[], Path]
    write_json: Callable[[Path, Any], None]
    write_verify_snapshot: Callable[[list[str], str], None]


def print_rail_untracked_pause(ctx: ShipContext) -> None:
    ctx.rail_print(f"{ctx.rail_icon('warning')} Ship paused: `.rail/` is not tracked on the default branch.")
    ctx.rail_print(f"{ctx.rail_icon('info')} Checkout/sync could remove AI Rail runtime files.")
    ctx.rail_print(f"{ctx.rail_icon('tip')} Recommended next action: commit `.rail/` on the default branch, then rerun rail ship.")


def print_merge_conflict_pause(ctx: ShipContext, issue_branch: str, default_branch: str, *, issue_branch_pushed: bool) -> None:
    push_state = "pushed to origin" if issue_branch_pushed else "committed locally but not pushed because --no-push was used"
    ctx.rail_print(f"{ctx.rail_icon('warning')} Ship paused: merge into default branch has conflicts.")
    ctx.rail_print(f"{ctx.rail_icon('warning')} Ship paused: merging issue branch `{issue_branch}` into default branch `{default_branch}` has conflicts.")
    ctx.rail_print(f"{ctx.rail_icon('info')} Issue branch state: {push_state}.")
    ctx.rail_print(f"{ctx.rail_icon('info')} GitHub issue is still open, and active state was preserved.")
    ctx.rail_print(f"{ctx.rail_icon('info')} `.rail/PROJECT.md` may already be marked `[x]` for this issue on `{issue_branch}`.")
    ctx.rail_print(f"{ctx.rail_icon('warning')} Do not run `rail import` while this merge is conflicted.")
    ctx.rail_print(f"{ctx.rail_icon('warning')} Do not run `rail ship` again until the conflict is resolved or aborted.")
    ctx.rail_print(f"{ctx.rail_icon('tip')} First run `git status --short`, resolve the conflicted files, and `git add ...` them.")
    ctx.rail_print(f"{ctx.rail_icon('tip')} Resolve path: fix conflicts, run focused checks, `git add ...`, `git commit`, `git push origin {default_branch}`, then `rail issue-close --commit && rail done && rail sync`.")
    ctx.rail_print(f"{ctx.rail_icon('tip')} Abort path: `git merge --abort`, then `git checkout {issue_branch}` to return to the issue branch.")


def print_no_merge_warning(ctx: ShipContext) -> None:
    ctx.rail_print(f"{ctx.rail_icon('warning')} rail ship --no-merge did not integrate this issue branch into the default branch.")
    ctx.rail_print(f"{ctx.rail_icon('info')} This is an advanced/manual compatibility path; branch-only work is not fully shipped.")


def print_git_state_blocked(ctx: ShipContext, state: dict[str, Any]) -> None:
    ctx.rail_print(f"{ctx.rail_icon('error')} rail ship is blocked because Git has unresolved state.")
    if state.get("unmerged_files"):
        ctx.rail_print(f"{ctx.rail_icon('warning')} Unresolved files:")
        for item in state["unmerged_files"]:
            ctx.rail_print(f"- {item}")
    active_ops = []
    if state.get("merge_active"):
        active_ops.append("merge")
    if state.get("rebase_active"):
        active_ops.append("rebase")
    if state.get("cherry_pick_active"):
        active_ops.append("cherry-pick")
    if state.get("revert_active"):
        active_ops.append("revert")
    if active_ops:
        ctx.rail_print(f"{ctx.rail_icon('warning')} Active Git operation: {', '.join(active_ops)}")
    ctx.rail_print(f"{ctx.rail_icon('tip')} Run: git status --short")
    ctx.rail_print(f"{ctx.rail_icon('tip')} To finish a merge: resolve conflicts, `git add ...`, `git commit`, then run `rail issue-close --commit && rail done && rail sync` if the issue was already integrated.")
    ctx.rail_print(f"{ctx.rail_icon('tip')} To abort: `git merge --abort`")


def prepare_default_branch_ref(ctx: ShipContext, default_branch: str) -> tuple[bool, str]:
    if ctx.git_ref_exists(default_branch):
        return True, default_branch
    remote_ref = f"origin/{default_branch}"
    if ctx.git_ref_exists(remote_ref):
        return True, remote_ref
    if ctx.branch_exists_remotely(default_branch):
        fetch = ctx.run(["git", "fetch", "origin", default_branch], timeout=120)
        if fetch.returncode != 0:
            print(fetch.stderr.strip() or fetch.stdout.strip())
            return False, remote_ref
        if ctx.git_ref_exists(remote_ref):
            return True, remote_ref
    return False, remote_ref


def checkout_default_branch(ctx: ShipContext, default_branch: str, source_ref: str) -> int:
    if ctx.git_ref_exists(default_branch):
        checkout = ctx.run(["git", "checkout", default_branch], timeout=120)
    else:
        checkout = ctx.run(["git", "checkout", "-b", default_branch, source_ref], timeout=120)
    if checkout.returncode != 0:
        print(checkout.stderr.strip() or checkout.stdout.strip())
        return checkout.returncode or 1
    if checkout.stdout.strip() or checkout.stderr.strip():
        print(checkout.stdout.strip() or checkout.stderr.strip())
    return 0


def integrate_issue_branch_into_default(ctx: ShipContext, issue_branch: str, *, push: bool) -> int:
    if not shutil.which("git"):
        ctx.rail_print(f"{ctx.rail_icon('error')} git is required to integrate the issue branch into the default branch.")
        return 1
    if not issue_branch or issue_branch == "unknown":
        ctx.rail_print(f"{ctx.rail_icon('error')} Could not detect the issue branch. Issue was not closed.")
        return 1

    default_branch = ctx.configured_default_branch()
    exists, source_ref = prepare_default_branch_ref(ctx, default_branch)
    if not exists:
        ctx.rail_print(f"{ctx.rail_icon('warning')} Ship paused: configured default branch `{default_branch}` was not found.")
        ctx.rail_print(f"{ctx.rail_icon('info')} Issue was not closed and active state was kept.")
        return 1

    if not ctx.rail_runtime_tracked_on_branch(source_ref):
        print_rail_untracked_pause(ctx)
        return 1

    ctx.rail_print(f"{ctx.rail_icon('info')} Integrating `{issue_branch}` into `{default_branch}`...")
    rc = checkout_default_branch(ctx, default_branch, source_ref)
    if rc != 0:
        ctx.rail_print(f"{ctx.rail_icon('warning')} Ship paused before issue close; default branch checkout failed.")
        return rc

    pull = ctx.run(["git", "pull", "--ff-only", "origin", default_branch], timeout=120)
    if pull.returncode != 0:
        print(pull.stderr.strip() or pull.stdout.strip())
        ctx.rail_print(f"{ctx.rail_icon('warning')} Ship paused before issue close; default branch pull failed.")
        return pull.returncode or 1
    if pull.stdout.strip() or pull.stderr.strip():
        print(pull.stdout.strip() or pull.stderr.strip())

    merge = ctx.run(["git", "merge", "--no-ff", issue_branch, "-m", f"Merge {issue_branch}"], timeout=120)
    if merge.returncode != 0:
        print(merge.stderr.strip() or merge.stdout.strip())
        print_merge_conflict_pause(ctx, issue_branch, default_branch, issue_branch_pushed=push)
        return merge.returncode or 1
    if merge.stdout.strip() or merge.stderr.strip():
        print(merge.stdout.strip() or merge.stderr.strip())

    if not ctx.local_py().exists():
        ctx.rail_print(f"{ctx.rail_icon('warning')} Ship paused: .rail/rail.py is missing after merge. Issue was not closed.")
        return 1

    if push:
        push_result = ctx.run(["git", "push", "origin", default_branch], timeout=120)
        if push_result.returncode != 0:
            print(push_result.stderr.strip() or push_result.stdout.strip())
            ctx.rail_print(f"{ctx.rail_icon('warning')} Ship paused before issue close; default branch push failed.")
            return push_result.returncode or 1
        print(push_result.stdout.strip() or push_result.stderr.strip() or f"Pushed {default_branch}.")
    else:
        ctx.rail_print(f"{ctx.rail_icon('warning')} --no-push used; default branch merge was not pushed.")

    return 0


def run_ship(ns: argparse.Namespace, ctx: ShipContext) -> int:
    state = ctx.git_safety_preflight()
    default_branch = str(state.get("default_branch") or ctx.configured_default_branch())
    current = str(state.get("current_branch") or ctx.current_branch())
    if ctx.git_state_blocks_new_work(state):
        print_git_state_blocked(ctx, state)
        ctx.rail_print(f"{ctx.rail_icon('info')} Ship stopped before updating .rail/PROJECT.md, committing, pushing, closing issues, or syncing.")
        return 1
    head = ctx.run(["git", "rev-parse", "--verify", "HEAD"], timeout=15)
    has_head = head.returncode == 0
    manual_local_ship = (
        getattr(ns, "no_merge", False)
        or (
            getattr(ns, "no_push", False)
            and getattr(ns, "no_close", False)
            and getattr(ns, "no_done", False)
            and getattr(ns, "no_sync", False)
        )
    )
    if has_head and current == default_branch and not manual_local_ship:
        ctx.rail_print(f"{ctx.rail_icon('error')} Ship expects an issue branch, but you are on the default branch `{default_branch}`.")
        ctx.rail_print(f"{ctx.rail_icon('info')} Ship stopped before updating .rail/PROJECT.md, committing, pushing, closing issues, or syncing.")
        ctx.rail_print(f"{ctx.rail_icon('tip')} Checkout the issue branch and rerun `rail ship`, or use manual close/sync commands if the merge was already completed.")
        return 1
    active_before_ship = ctx.active()
    project_path = ctx.rail_dir() / "PROJECT.md"
    project_memory_before_ship: str | None = None
    project_memory_existed_before_ship = project_path.exists()
    if project_memory_existed_before_ship and project_path.is_file():
        project_memory_before_ship = project_path.read_text(encoding="utf-8", errors="replace")

    def run_ship_checks(configured_checks: list[str], reason: str) -> int:
        if reason == "--recheck requested":
            ctx.rail_print(f"{ctx.rail_icon('info')} --recheck requested. Running checks now...")
        else:
            ctx.rail_print(f"{ctx.rail_icon('info')} Last checks are {reason}. Running checks now...")
        checks_rc = ctx.delegate(["checks"], stream=True)
        if checks_rc != 0:
            config = ctx.cfg()
            configured_values = config.get("checks") or []
            check_output = ctx.checks_path().read_text(encoding="utf-8", errors="replace") if ctx.checks_path().exists() else ""
            recovery = ctx.missing_npm_check_recovery(configured_values, check_output)
            if recovery:
                failed_command, replacement = recovery
                print(f"[rail] Configured check `{failed_command}` is not available.")
                print(f"[rail] Found available project check: `{replacement}`.")
                print("[rail] Running replacement check now...")
                checks_rc = ctx.delegate(["checks", replacement], stream=True)
                if checks_rc == 0 and ctx.can_update_stale_default_node_check(configured_values, failed_command, replacement):
                    config["checks"] = [replacement]
                    ctx.write_json(ctx.rail_dir() / "config.json", config)
                    print(f"[rail] Updated .rail/config.json checks to `{replacement}`.")
            elif configured_values:
                missing_npm_commands = [
                    command for command in configured_values
                    if isinstance(command, str)
                    and (script := ctx.npm_run_script(command))
                    and script not in ctx.package_json_scripts()
                    and ctx.check_output_mentions_missing_npm_script(check_output, script)
                ]
                if missing_npm_commands and ctx.package_json_scripts():
                    print(f"[rail] Configured check `{missing_npm_commands[0]}` is not available.")
                    print("[rail] No usable npm check script was found in package.json.")

            if checks_rc != 0:
                ctx.rail_print(f"{ctx.rail_icon('error')} Checks still failed. Ship stopped.")
                ctx.rail_print(f"{ctx.rail_icon('tip')} Fix checks and rerun `rail ship`, or use `--force` only if you intentionally accept the risk.")
                return checks_rc or 1
        ctx.rail_print(f"{ctx.rail_icon('success')} Checks passed. Continuing ship.")
        ctx.write_verify_snapshot(ctx.configured_check_commands(), ctx.checks_result())
        ctx.refresh_review_and_check_artifacts()
        return 0

    if not ns.force:
        check_commands = ctx.configured_check_commands()
        verified, verify_message = ctx.validate_verify_snapshot(check_commands=check_commands)
        if verified:
            print(verify_message)
            if ns.recheck:
                rc = run_ship_checks(check_commands, "--recheck requested")
                if rc != 0:
                    return rc
            else:
                ctx.rail_print(f"{ctx.rail_icon('success')} Checks already passed in last verify. Skipping recheck.")
        else:
            reason = ctx.check_block_reason()
            explicit_check_bypass = (
                (reason in {"missing", "unknown"} and ns.allow_missing_checks)
                or (reason == "stale" and ns.allow_stale)
            )
            if explicit_check_bypass:
                pass
            else:
                can_use_legacy_recovery = (
                    reason is not None
                    and (not ctx.verified_path().exists() or ns.recheck)
                )
                if can_use_legacy_recovery:
                    rc = run_ship_checks(check_commands, reason)
                    if rc != 0:
                        return rc
                else:
                    print(verify_message)
                    return 1

    if active_before_ship:
        issue = active_before_ship.get("issue", {})
        try:
            ctx.rail_print(f"{ctx.rail_icon('info')} Updating .rail/PROJECT.md for completed issue #{issue.get('number')}.")
            updated = ctx.mark_project_issue_completed(issue.get("number"), issue.get("title"), issue.get("body"))
            if updated:
                ctx.rail_print(f"{ctx.rail_icon('success')} Updated .rail/PROJECT.md for completed issue; it will be included in the ship commit.")
                ctx.refresh_review_and_check_artifacts()
        except Exception as exc:
            ctx.rail_print(f"{ctx.rail_icon('warning')} Could not update .rail/PROJECT.md before ship: {exc}")
            ctx.rail_print(f"{ctx.rail_icon('tip')} Recovery: mark the completed issue in .rail/PROJECT.md manually.")

    commit_args = ["commit", ns.message]
    ctx.append_flag(commit_args, ns.no_push, "--no-push")
    ctx.append_flag(commit_args, ns.amend, "--amend")
    ctx.append_flag(commit_args, ns.force, "--force")
    ctx.append_flag(commit_args, ns.allow_missing_checks, "--allow-missing-checks")
    ctx.append_flag(commit_args, ns.allow_stale, "--allow-stale")

    ctx.rail_print(f"{ctx.rail_icon('info')} Committing...")
    head_before_commit = ctx.run(["git", "rev-parse", "HEAD"], timeout=15)
    head_before = head_before_commit.stdout.strip() if head_before_commit.returncode == 0 else None
    rc = ctx.delegate(commit_args, extra_env={"AI_RAIL_SUPPRESS_COMMIT_NEXT": "1"})
    if rc != 0:
        if active_before_ship:
            try:
                if project_memory_existed_before_ship:
                    if project_memory_before_ship is not None:
                        project_path.write_text(project_memory_before_ship, encoding="utf-8")
                elif project_path.exists():
                    if project_path.is_file():
                        project_path.unlink()
                print("[rail] Restored .rail/PROJECT.md because ship commit failed.")
            except Exception as exc:
                print(f"[rail] Warning: could not restore .rail/PROJECT.md after ship commit failed: {exc}")
        ctx.rail_print(f"{ctx.rail_icon('error')} Ship stopped during commit; no later ship steps ran.")
        return rc
    head_after_commit = ctx.run(["git", "rev-parse", "HEAD"], timeout=15)
    head_after = head_after_commit.stdout.strip() if head_after_commit.returncode == 0 else None
    if head_before and head_after and head_before == head_after:
        ctx.rail_print(f"{ctx.rail_icon('warning')} No new commit was created, so ship is paused.")
        ctx.rail_print(f"{ctx.rail_icon('info')} Issue was not closed, and active state was kept.")
        return 1

    issue_branch = ctx.current_branch()
    if ns.no_sync:
        default_branch = ctx.cfg().get("default_branch", "main")
        ctx.rail_print(f"{ctx.rail_icon('warning')} Ship paused: --no-sync prevented default-branch integration.")
        ctx.rail_print(f"{ctx.rail_icon('info')} Issue branch `{issue_branch}` was committed, but the issue was not closed and active state was kept.")
        ctx.rail_print(f"{ctx.rail_icon('tip')} Next: merge and push `{issue_branch}` into `{default_branch}`, then run `rail issue-close --commit && rail done && rail sync`.")
        return 1
    if ns.no_merge:
        print_no_merge_warning(ctx)
        ctx.rail_print(f"{ctx.rail_icon('info')} Issue was not closed, and active state was kept.")
        ctx.rail_print(f"{ctx.rail_icon('tip')} Next: merge and push `{issue_branch}` into the default branch before closing or marking done.")
        return 1
    else:
        default_branch = ctx.cfg().get("default_branch", "main")
        if issue_branch == default_branch:
            ctx.rail_print(f"{ctx.rail_icon('error')} Ship expects an issue branch, but you are already on the default branch `{default_branch}`.")
            ctx.rail_print(f"{ctx.rail_icon('info')} Issue was not closed, and active state was kept.")
            return 1
        rc = integrate_issue_branch_into_default(ctx, issue_branch, push=not ns.no_push)
        if rc != 0:
            return rc
        if ns.no_push:
            ctx.rail_print(f"{ctx.rail_icon('warning')} Default branch was merged locally but not pushed.")
            ctx.rail_print(f"{ctx.rail_icon('info')} Issue was not closed, and active state was kept.")
            ctx.rail_print(f"{ctx.rail_icon('tip')} Next: inspect `{default_branch}`, push it with `git push origin {default_branch}`, then run `rail issue-close --commit && rail done && rail sync`.")
            return 1

    if not ns.no_close:
        rc = ctx.delegate(["issue-close", "--commit"])
        if rc != 0:
            ctx.rail_print(f"{ctx.rail_icon('warning')} Ship stopped after commit succeeded; issue close failed.")
            ctx.rail_print(f"{ctx.rail_icon('info')} Active state was kept.")
            ctx.rail_print(f"{ctx.rail_icon('tip')} Recovery: manually close the GitHub issue or fix `gh auth login`, then run: rail done && rail sync")
            return rc

    if not ns.no_done:
        done_args: list[str] = []
        ctx.append_flag(done_args, ns.keep_active, "--keep-active")
        ctx.append_flag(done_args, ns.force, "--force")
        rc = ctx.cmd_done(done_args)
        if rc != 0:
            ctx.rail_print(f"{ctx.rail_icon('warning')} Ship stopped after commit and issue-close succeeded; done failed.")
            return rc

    ctx.print_ship_phase_progress()
    ctx.rail_print(f"{ctx.rail_icon('success')} Ship complete.")
    ctx.rail_print(f"{ctx.rail_icon('tip')} Recommended next action: rail phase --copy")
    return 0
