# Prompt: adapt the checks to another language or CI

The baseline's app checks are for Python, and its CI is GitHub Actions. Most of the security stack doesn't depend on either. To carry it to another language, toolchain or CI system, paste the prompt below into your coding agent, in a clone of your repository, and fill in the brackets.

```text
Adapt this repository's checks to [the language and toolchain, such as TypeScript with pnpm] [and/or the CI system, such as Azure Pipelines].

Read first: AGENTS.md; docs/checks-inventory.md (every check, its type and how a new repository adopts it); docs/security-setup-prompt.md (the procedure, its decisions and its rules); docs/stack.md.

Then, one step at a time:
1. Sort the inventory's checks into three groups, and show me the table before changing anything:
   - neutral, carried over as they are: the agent guard, the git hooks for secrets, keys and blocked names, the gate, the ruleset and the GitHub settings check;
   - language-specific: the Python checks (lint, format, types, tests, coverage, dependencies, dead code, known vulnerabilities, the file-length hook);
   - CI-specific: the trusted workflow, its required checks and how they're protected.
2. For each language-specific check, propose the equivalent tool, pinned to a version, that blocks and fails closed. List the inline markers that silence the new tools (the equivalents of noqa and type-ignore), so the gate can refuse them.
3. For another CI system, keep the decisions in docs/security-setup-prompt.md: required checks come from the default branch, never from the pull request; tools install pinned by hash before any pull request code is on disk; the gate's and the guard's tests run against the pull request's code; and nobody bypasses the branch protection. Say plainly where the new system can't meet one, and what that costs.
4. Change one group per pull request. Every check you add, change or remove gets its row in docs/checks-inventory.md in the same pull request, with its type and how a new repository adopts it.

The checks and their configuration are enforcement files, so changes need my approval. Never lower a check to get a change through.
```
