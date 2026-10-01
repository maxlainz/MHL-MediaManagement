# Git
*Norma del owner, 2026-10-01 (D7, D15).*

- Conventional Commits en inglés con scope: `feat(gui): ...`, `fix(worker): ...`, `fix(mhl): ...`, `docs(rules): ...`, `chore(release): vX.Y.Z`, `test(cli): ...`, `ci(...)`. Cuerpo en prosa explicando el porqué, citando `Dn`, `Hn` o `#issue`.
- Un commit por tarea. El repo nunca se deja roto: `make ci` verde antes de cada commit.
- SemVer. La primera versión es `v0.1.0`, que se taggea cuando la CI esté verde (no en el arranque); después, SemVer normal: parche para correcciones, menor para funcionalidad nueva. No hay hitos numerados. Tags anotados `vX.Y.Z`; nunca se reescribe un tag publicado.
- **Nunca se commitea en `main`** (D15; un hook `PreToolUse` deniega `git commit`, `merge`, `rebase` y `cherry-pick` con `main` activa). Todo cambio, también docs y bitácora, va en una rama `feat/<issue#>-slug`, `fix/...`, `docs/...`, `chore/...` y entra por PR con `Closes #N` cuando resuelve un issue. `main` está protegida en GitHub: PR obligatorio, check `ci` verde, historial lineal (squash o rebase), sin force-push ni borrado, también para admins; sin revisor obligatorio mientras escriba una sola persona. Las ramas integradas se borran solas al mergear (`delete_branch_on_merge`).
- Flujo: `git checkout -b <rama>` al empezar la tarea → commits → `make ci` → `git push -u origin <rama>` → `gh pr create` → CI verde → `gh pr merge --squash` (o `--rebase` si los commits son limpios y quieren conservarse) → `git checkout main && git pull --ff-only`.
- Releases: el commit `chore(release): vX.Y.Z` también entra por PR; el tag anotado se pone sobre `main` ya mergeada.
- Sin trailers de atribución (`Co-Authored-By`, `Signed-off-by`): `includeCoAuthoredBy: false` en `.claude/settings.json`.
- Nunca `git push --force` a `main`.

**Por qué:** historial legible por humanos y por `git log --grep`, y releases reproducibles desde el tag.
