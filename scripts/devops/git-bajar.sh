#!/usr/bin/env bash
# =============================================================================
# git-bajar.sh — Trae cambios de GitHub al repo local con auto-stash.
# Equivalente a bajar.bat de CVS-Web.
# =============================================================================
set -u
cd "$(dirname "$0")/../.." || exit 1

echo
echo "============================================"
echo "  BAJAR CAMBIOS DE GITHUB"
echo "============================================"
echo

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "ERROR: esta carpeta no es un repositorio git."
    exit 1
fi

echo "Comprobando cambios remotos..."
if ! git fetch; then
    echo "ERROR al hacer fetch. Revisa tu conexion o el acceso al repo."
    exit 1
fi

BEHIND=$(git rev-list --count 'HEAD..@{u}' 2>/dev/null || echo 0)
if [ "$BEHIND" = "0" ]; then
    echo "Ya estas al dia con el remoto. Nada que bajar."
    exit 0
fi
echo "Hay $BEHIND commit(s) nuevo(s) en GitHub:"
echo "--------------------------------------------"
git --no-pager log --oneline 'HEAD..@{u}'
echo "--------------------------------------------"
echo

# Detectar archivos untracked locales que chocarian con el pull.
COLISIONES=()
while IFS= read -r f; do
    [ -z "$f" ] && continue
    if [ -e "$f" ] && ! git ls-files --error-unmatch "$f" >/dev/null 2>&1; then
        COLISIONES+=("$f")
    fi
done < <(git diff --name-only --diff-filter=A 'HEAD..@{u}' 2>/dev/null)

if [ "${#COLISIONES[@]}" -gt 0 ]; then
    echo
    echo "AVISO: archivos locales sin rastrear que el pull sobrescribiria:"
    echo "--------------------------------------------"
    printf '  %s\n' "${COLISIONES[@]}"
    echo "--------------------------------------------"
    echo
    echo "Suele pasar cuando creaste el mismo archivo aqui y en otra maquina."
    echo "Si confirmas, se borraran los locales y se traeran los del remoto."
    read -r -p "Eliminarlos antes del pull? [s/N]: " BORRAR
    if [ "${BORRAR,,}" != "s" ] && [ "${BORRAR,,}" != "si" ]; then
        echo "Cancelado. Mueve o renombra esos archivos manualmente."
        exit 1
    fi
    for f in "${COLISIONES[@]}"; do
        [ -e "$f" ] && rm -f "$f"
    done
fi

# Auto-stash si hay cambios locales sin commit.
STASHED=0
if ! git diff --quiet --cached || ! git diff --quiet; then
    STASHED=1
    echo "Tienes cambios locales sin commit. Guardando en stash temporal..."
    if ! git stash push -u -m "auto-stash bajar.bat"; then
        echo "ERROR al hacer stash."
        exit 1
    fi
fi

echo
echo "Descargando cambios (pull --rebase)..."
if ! git pull --rebase; then
    echo
    echo "ERROR durante el rebase (probables conflictos)."
    if [ "$STASHED" = "1" ]; then
        echo "NOTA: tus cambios locales siguen guardados en 'git stash list'."
        echo "Resuelve los conflictos del rebase, luego: git rebase --continue"
        echo "Por ultimo: git stash pop"
    fi
    exit 1
fi

if [ "$STASHED" = "1" ]; then
    echo
    echo "Restaurando tus cambios locales del stash..."
    if ! git stash pop; then
        echo
        echo "CONFLICTO al restaurar el stash. Tus cambios siguen en 'git stash list'."
        echo "Resuelve los conflictos manualmente y luego: git stash drop"
        exit 1
    fi
fi

echo
echo "============================================"
echo "OK - Repositorio al dia con GitHub."
echo "============================================"
