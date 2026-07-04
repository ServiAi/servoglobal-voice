# Reglas de ramas y merge - Sprint 3

## Rama estable

La rama estable de integracion es:

```text
develop
```

Ningun agente puede trabajar directamente sobre `develop`.

## Ramas obligatorias

Codex para WhatsApp debe usar:

```text
feature/sprint-3a-whatsapp-crm-actions-codex
```

Antigravity para Voz debe usar:

```text
feature/sprint-3b-voice-integration-antigravity
```

## Crear rama

Siempre partir de `develop` actualizado:

```bash
git fetch origin --prune
git checkout develop
git pull origin develop
git checkout -b <nombre-rama>
```

## Sincronizacion durante desarrollo

Cada rama debe sincronizarse con `develop` de forma frecuente:

```bash
git fetch origin
git merge origin/develop
```

Usar merge, no rebase, salvo autorizacion explicita.

No hacer force push a `develop`.

No resolver conflictos automaticamente.

Si hay conflicto, detenerse y reportar:

* Archivo afectado.
* Causa probable.
* Bloque en conflicto.
* Recomendacion de resolucion.

## Pull Request obligatorio

Cada integracion debe tener su propio PR:

```text
Sprint 3A - WhatsApp CRM Actions reales
Base: develop
Head: feature/sprint-3a-whatsapp-crm-actions-codex
```

```text
Sprint 3B - Voice CRM Actions reales
Base: develop
Head: feature/sprint-3b-voice-integration-antigravity
```

Cada PR debe incluir:

* Que se implemento.
* Archivos principales.
* Endpoints nuevos.
* Migraciones.
* Tests ejecutados.
* Riesgos.
* Confirmacion de archivos no tocados.
* Screenshots si hay UI.
* Flujo manual validado.

## Orden recomendado de merge

Orden recomendado:

1. Mergear WhatsApp primero.
2. Actualizar rama de Voz con `develop`.
3. Resolver conflictos de Voz.
4. Ejecutar tests completos.
5. Mergear Voz.

## Merge a develop

Solo mergear cuando:

* Tests backend pasen.
* Lint frontend pase.
* Typecheck frontend pase.
* Build frontend pase.
* `git diff --check` pase.
* No haya secretos.
* No haya cambios en `.env`.
* No haya cambios en `opencode.jsonc`.
* No haya multiples heads de Alembic.

Usar:

```bash
git checkout develop
git pull origin develop
git merge --no-ff <rama> -m "merge: <descripcion>"
git push origin develop
```

## Alembic

Cada integracion debe tener migracion propia.

WhatsApp:

```text
202607030001_integrations_3a_whatsapp_crm_actions.py
```

Voz:

```text
202607030002_integrations_3b_voice_crm_actions.py
```

Antes de mergear:

```bash
cd backend
alembic heads
```

Debe existir una sola head.

Si hay multiples heads, detenerse y reportar.
