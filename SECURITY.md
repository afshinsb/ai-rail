# Security

AI Rail is local-first.

It does not send project files or source code to any remote service by itself.

It may invoke:

- `git`
- GitHub CLI `gh`
- local shell commands configured in `.rail/config.json`

Review `.rail/config.json` before running checks from an untrusted project.
