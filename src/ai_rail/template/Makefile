# AI Rail shortcut Makefile
# Prefer direct CLI commands when portability matters.

r := rail

.PHONY: status resume next verify ship snapshot handoff export export-dry-run start prompt review checks done sync issues log report

status:
	$(r) status

resume:
	$(r) resume

next:
	$(r) next --copy

verify:
	$(r) verify --copy

ship:
	$(r) ship "$(M)"

snapshot:
	$(r) snapshot

handoff:
	$(r) handoff --for generic --copy

export:
	$(r) export

export-dry-run:
	$(r) export --dry-run

start:
	$(r) start $(N)

prompt:
	$(r) prompt codex --copy

review:
	$(r) review

checks:
	$(r) checks

done:
	$(r) done

sync:
	$(r) sync

issues:
	$(r) issue-list

log:
	$(r) log

report:
	$(r) report
