# Changelog

What changed in the baseline, newest first. Versions are tagged `vMAJOR.MINOR.PATCH`.

## v0.1.0: the first public release

### Added

- **The security and governance stack.**
  - Five required checks come from a workflow a pull request can't edit: `security-critical-gate`, `secret-scan`, `precommit`, `selftest` and `python`.
  - The pre-commit chain runs at every commit and again in CI.
  - The agent guard runs in Claude Code.
  - Changes to enforcement need the owner's approval.
  - Blocked names are refused.
  - The tools are pinned by hash and the actions by SHA.
- **The Python toolchain.** uv with a hash-pinned lockfile and a seven-day cooldown. It checks lint, format, strict types, tests, changed-line coverage, dependencies, dead code and known vulnerabilities.
- **The Azure foundation.** Resource groups, a region lock, a budget, and a deploy identity with keyless CI sign-in.
- **The generic architecture and stack documents,** with the restaurant use case as the worked example.
- **The rules and the inventory.** The checks inventory, `AGENTS.md` and `CLAUDE.md`, and the "locked down by default" posture.
- **The enterprise-level gaps list,** with caveats for anyone adopting the baseline.
- **A guide to runtime enforcement across coding agents,** four prompt templates (set up a new repository, port the guard, adapt the checks, harden the workstation), the path to protect the owner's own sign-ins, and the MIT license.
- **The use-case template.**
- **The GitHub settings check.** `scripts/github_settings.py` compares the repository's GitHub settings with the baseline, and `--apply` raises what falls short without lowering anything stricter.
- **An owner's switch to let Dependabot's bumps merge on green.** With `github.dependabot_merges_on_green` on, the agent approves and merges a Dependabot PR without asking, but only if Dependabot is the only one who has pushed to it and every enforcement-file change just moves an action pin or a dependency version. The switch is off in the baseline, and turning it on is a recorded lowering.
- **Review threads must be resolved before a pull request merges.** It's a ruleset rule, inventory check 67.
- **Tests for the secret-scan step.** `tests/gate/test_secret_scan_step.py` runs the step's own script against a throwaway repository.
- **Hook pins are full commit hashes.** The gate refuses a pre-commit hook pinned by a tag, a branch or a short hash, which can be moved to other code after review.
- **The agent guard in GitHub Copilot Chat (VS Code).** `.github/hooks/agent-guard.json` runs the guard before each tool call by Copilot Chat's agent. The guard checks Copilot's tools as the Claude Code tools that do the same, and refuses where Claude Code would ask. A guard that can't start, or runs out of time, blocks. The Copilot CLI and the Copilot cloud agent aren't covered.
- **Defenses against instructions hidden in what agents read.** Claude Code's deny rules keep the owner's sign-ins and `.env` files out of its reads in every permission mode. The guard refuses commands that read them or print a token, and asks before data leaves: a request that sends data, a site off the allowlist in `.claude/security-stack.json`, a push to another remote, a gist, or code that opens a network connection. `AGENTS.md` treats what agents read as data, and says how to stop: with a recommendation, and when the owner must switch to default mode. It's also shorter.
- **Control and AI risk mappings.** `docs/control-mapping.md` maps every check to SOC 2, ISO/IEC 27001 and NIST CSF 2.0. `docs/ai-risk-mapping.md` maps the baseline to the FINOS AI Governance Framework's 23 mitigations and 23 risks, and names what keeps each Partial from In place: four open items, and two limits of the guard.
- **An OWASP view of the AI risk mapping.** `docs/ai-risk-mapping.md` arranges its statuses by the OWASP Top 10 for LLM Applications 2026 and the OWASP Top 10 for Agentic Applications. For each entry it gives what's in place, the gap and the method that closes it, with a crosswalk from the 2025 numbers FINOS uses.

### Changed

- The guard keeps every `az` command in the project's Azure tenant, and asks the owner before any Azure change.
- `.claude/security-stack.json`, `AGENTS.md` and `CLAUDE.md` are enforcement files.
- The pull request's secret scan checks the files the PR adds or changes. The full scan of every file runs on `main` after each merge and daily.
- Every workflow job runs on a pinned runner image, `ubuntu-24.04`.
- Dependabot waits seven days before proposing a new GitHub Actions version, as it already did for Python packages. Security updates don't wait.
- VS Code's settings are enforcement: the workspace's `.vscode/` folder and workspace files, in CODEOWNERS, and the user settings, which can switch Copilot Chat's hooks off.
- The gate refuses a removed test name in any of its four test files, not only the gate's and the guard's, and a removed or changed Copilot Chat registration.
- The GitHub settings check covers review-thread resolution and the extra approval for unattributed changes, and `--apply` raises both.

### Fixed

- A file named like an option, such as `--help`, could make either secret scan exit without scanning. Both scans now end the scanner's options with `--`.
- The guard's merge check didn't see a file renamed away from an enforcement path. It now counts the old name too.
- On Windows, the guard read `gh`'s output with the system's default encoding, so it failed closed on any Dependabot PR whose description had emoji. It reads UTF-8 now.
- The guard could miss a command. It read only the first line of a command on several lines; a redirect in front of a command (`>/dev/null git push upstream`) hid it; `&>`, `>&` and `>|` split one command in two; and a command inside backticks, or inside `$( )` within double quotes, wasn't read. A trailing redirect was taken for a copy's destination, and a git command's own redirects weren't checked (`git show HEAD:x > .claude/settings.json`). The guard now reads every line, joins continued ones, reads substituted commands, and reads redirects the way the shell does, wherever they stand. Harmless redirects, such as `git push 2>&1` and PowerShell's `2>$null`, no longer ask.
- What a substitution prints could stand in for a path or a program the guard never saw: `rm $(printf .github/CODEOWNERS)` removed an enforcement file, and `$(printf git) push upstream` pushed elsewhere, without the owner. The guard now reads a substitution as a value it can't read: a path, redirect target or folder built from one counts as a protected one, and a program that comes from one asks. A folder named by any value it can't read, such as `cd "$UNSET"`, is taken to be a protected one too.

### Decided

- **How the agent answers within the asker's permissions.** Its tools query Azure SQL as that person, through Entra's on-behalf-of flow.
- **How search honours roles.** Each indexed document carries the groups allowed to read it in full, and every search filters on them. Document types with masked fields are never indexed.
- **How answers resist instructions hidden in documents.** Document text is data whoever wrote it: it's marked as untrusted and screened by prompt shields, and a document they flag, or can't screen, never reaches the model. Answers show only citations to the project's own records, never external links or images. Two eval sets check it: screening must catch documents carrying injected instructions, and attacks run past screening must give the same answer, tool calls, scope and citations as a clean copy.
