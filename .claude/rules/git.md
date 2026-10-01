# Git
*Norma del owner, 2026-10-01 (D7).*

- Conventional Commits en inglés con scope: `feat(gui): ...`, `fix(worker): ...`, `fix(mhl): ...`, `docs(rules): ...`, `chore(release): vX.Y.Z`, `test(cli): ...`, `ci(...)`. Cuerpo en prosa explicando el porqué, citando `Dn`, `Hn` o `#issue`.
- Un commit por tarea. El repo nunca se deja roto: `make ci` verde antes de cada commit.
- SemVer. La primera versión es `v0.1.0`, que se taggea cuando la CI esté verde (no en el arranque); después, SemVer normal: parche para correcciones, menor para funcionalidad nueva. No hay hitos numerados. Tags anotados `vX.Y.Z`; nunca se reescribe un tag publicado.
- Ramas: `feat/<issue#>-slug`, `fix/...`, `docs/...`. PR con `Closes #N`. Las ramas integradas se borran sin preguntar (`gh pr merge --delete-branch`). Hasta `v0.1.0` se puede commitear directo a `main`.
- Sin trailers de atribución (`Co-Authored-By`, `Signed-off-by`): `includeCoAuthoredBy: false` en `.claude/settings.json`.
- Nunca `git push --force` a `main`.

**Por qué:** historial legible por humanos y por `git log --grep`, y releases reproducibles desde el tag.
