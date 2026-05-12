#!/usr/bin/env bash
# =============================================================================
# git-estado.sh — Estado del repo de KRONOS frente a GitHub.
# Equivalente a estado.bat de CVS-Web, pero corriendo en WSL.
# =============================================================================
set -u
cd "$(dirname "$0")/../.." || exit 1

echo
echo "============================================"
echo "  ESTADO DEL REPOSITORIO"
echo "============================================"
echo

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "ERROR: esta carpeta no es un repositorio git."
    exit 1
fi

echo "Consultando GitHub..."
if ! git fetch >/dev/null 2>&1; then
    echo "AVISO: no se pudo hacer fetch (revisa conexion). Datos locales."
fi
echo

echo "--- Working tree ---"
git status --short --branch
echo

AHEAD=$(git rev-list --count '@{u}..HEAD' 2>/dev/null || echo 0)
BEHIND=$(git rev-list --count 'HEAD..@{u}' 2>/dev/null || echo 0)

if [ "$AHEAD" != "0" ]; then
    echo "--- $AHEAD commit(s) sin SUBIR a GitHub (haz subir.bat) ---"
    git log --oneline '@{u}..HEAD'
    echo
fi

if [ "$BEHIND" != "0" ]; then
    echo "--- $BEHIND commit(s) sin BAJAR de GitHub (haz bajar.bat) ---"
    git log --oneline 'HEAD..@{u}'
    echo
fi

DIRTY=0
git diff --quiet --cached || DIRTY=1
git diff --quiet || DIRTY=1

if [ "$AHEAD" = "0" ] && [ "$BEHIND" = "0" ] && [ "$DIRTY" = "0" ]; then
    echo "Repositorio totalmente sincronizado con GitHub."
    echo
fi

STASHCOUNT=$(git stash list 2>/dev/null | wc -l)
if [ "$STASHCOUNT" != "0" ]; then
    echo "--- $STASHCOUNT stash(es) guardado(s) (git stash list) ---"
    git stash list
    echo
fi
