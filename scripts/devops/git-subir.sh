#!/usr/bin/env bash
# =============================================================================
# git-subir.sh — git add + commit + push con rebase automatico si toca.
# Equivalente a subir.bat de CVS-Web.
# =============================================================================
set -u
cd "$(dirname "$0")/../.." || exit 1

echo
echo "============================================"
echo "  SUBIR CAMBIOS A GITHUB"
echo "============================================"
echo

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "ERROR: esta carpeta no es un repositorio git."
    exit 1
fi

echo "Comprobando estado del remoto..."
if ! git fetch; then
    echo "ERROR al hacer fetch. Revisa tu conexion o el acceso al repo."
    exit 1
fi

echo
echo "Estado actual:"
echo "--------------------------------------------"
git status --short --branch
echo "--------------------------------------------"
echo

# Hay cambios locales sin commit?
DIRTY=0
git diff --quiet --cached || DIRTY=1
git diff --quiet || DIRTY=1

if [ "$DIRTY" = "1" ]; then
    read -r -p "Mensaje de commit: " MENSAJE
    if [ -z "$MENSAJE" ]; then
        echo "Cancelado: no se escribio mensaje."
        exit 1
    fi
    git add -A
    if ! git commit -m "$MENSAJE"; then
        echo
        echo "ERROR al crear el commit."
        exit 1
    fi
fi

AHEAD=$(git rev-list --count '@{u}..HEAD' 2>/dev/null || echo 0)
if [ "$AHEAD" = "0" ]; then
    echo "No hay commits pendientes de subir. Repositorio al dia."
    exit 0
fi

BEHIND=$(git rev-list --count 'HEAD..@{u}' 2>/dev/null || echo 0)
if [ "$BEHIND" != "0" ]; then
    echo
    echo "El remoto tiene $BEHIND commit(s) nuevo(s). Rebasando local..."
    if ! git pull --rebase; then
        echo
        echo "ERROR durante el rebase (probablemente conflictos)."
        echo "Resuelvelos manualmente y luego ejecuta:"
        echo "    git rebase --continue"
        echo "    git push"
        exit 1
    fi
fi

OLD_REMOTE=$(git rev-parse '@{u}' 2>/dev/null || echo "")

echo
echo "Subiendo a GitHub..."
if ! git push; then
    echo
    echo "ERROR al hacer push."
    exit 1
fi

git fetch >/dev/null 2>&1
AHEAD2=$(git rev-list --count '@{u}..HEAD' 2>/dev/null || echo 0)
if [ "$AHEAD2" != "0" ]; then
    echo
    echo "************************************************************"
    echo "*** AVISO: tras el push siguen quedando $AHEAD2 commit(s)  ***"
    echo "*** sin subir. Revisa el repositorio antes de cerrar.    ***"
    echo "************************************************************"
    exit 1
fi

echo
echo "============================================"
echo "OK - Commits subidos correctamente:"
echo "============================================"
if [ -n "$OLD_REMOTE" ]; then
    git log --oneline "$OLD_REMOTE..HEAD"
else
    git log --oneline -5
fi
echo
