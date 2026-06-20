# Public History Cleanup

The current `main` tree should not contain private planning artifacts. If a private file was already pushed, removing it in a later commit only fixes the current tree; earlier commits, remote caches, forks, and local clones can still retain it.

Use this runbook only after maintainer coordination:

1. Rotate any exposed secrets or credentials first.
2. Announce a short freeze for pushes to the repository.
3. Make a fresh mirror clone outside the working copy.
4. Rewrite history to remove the private file path from every commit.
5. Verify the rewritten history no longer contains the path or sensitive strings.
6. Force-push the rewritten branches and tags.
7. Ask collaborators to reclone or hard-reset from the rewritten remote.
8. Request cache invalidation from the hosting provider when needed.

The exact rewrite command depends on the maintainer-approved tool. `git filter-repo` is preferred when available because it is purpose-built for path purges. Do not run a force-push from an active development checkout without explicit approval.
