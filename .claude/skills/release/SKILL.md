---
name: release
description: Cut a version of MHL MediaManagement - make ci, version bump in pyproject.toml, changelog, vault notes, bitácora, CLAUDE.md, leak-check, annotated tag, CI on the tag.
---

# release

A release is: `version` bumped, changelog, bitácora entry, `CLAUDE.md` updated, vault notes written (rule `obsidian.md`), annotated tag. First version is `v0.1.0`, then plain SemVer (rule `git.md`). There is no Python package to publish and no Docker image: the deliverable is `mhl_pull.py` installed in Resolve with `make install`. In this order:

1. `make ci` green (leak-check + lint + test) and everything committed on `main` (or the PR merged). `gh issue list` read; issues closed by this release referenced in the commit body.
2. Bump `version` in `pyproject.toml` (single source of truth for the version). Then `uv sync` so `uv.lock` follows.
3. `CHANGELOG.md`: move `[Unreleased]` into `## [X.Y.Z] - YYYY-MM-DD`; keep an empty `[Unreleased]` with the six categories available (Añadido / Cambiado / Corregido / Decidido / Medido / Eliminado).
4. Vault: every new concept of the release has a `#concepto #archivo` note, linked from `Archivo` and, if the project note `MHL MediaManagement` exists, from it (skill `obsidian-vault`). If the vault does not answer, stop and tell the owner (rule `vault-accesible.md`).
5. `docs/bitacora/NN-*.md` entry with TL;DR and the notes written; `CLAUDE.md` state + next step.
6. `make leak-check` once more (rule `repo-publico.md`).
7. Commit `chore(release): vX.Y.Z` (body: what the release delivers, `Dn`/`Hn`/`#issue` cited), then `git tag -a vX.Y.Z -m "MHL MediaManagement vX.Y.Z" && git push && git push --tags`.
8. Check CI: `gh run list --limit 3`, `gh run view <id>`. If it goes red, fix forward with a new patch version; never move the tag.

Never tag with CI red. Never rewrite a pushed tag. Never bump `ascmhl` in the same release as other changes (rule `conformidad-mhl.md`: it needs its own `Dn`). The GUI cannot be tested in CI: before tagging, ask the owner to run the new version once inside Resolve (rule `resolve-y-stdlib.md`).
