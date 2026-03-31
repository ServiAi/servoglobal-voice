# Chatwoot en Dokploy — Guía de Instalación y Configuración

> **Proyecto:** Serviglobal IA — CRM  
> **URL de producción:** `https://crm.serviglobal-ia.com`  
> **Servidor:** Dokploy en VPS  
> **Fecha:** Marzo 2026  

---

## Índice

1. [Requisitos Previos](#1-requisitos-previos)
2. [Configuración docker-compose.yml](#2-configuración-docker-composeyml)
3. [Despliegue Inicial](#3-despliegue-inicial)
4. [Configuración de Base de Datos](#4-configuración-de-base-de-datos)
5. [Solución de Problemas Conocidos](#5-solución-de-problemas-conocidos)
6. [Comandos de Verificación y Testing](#6-comandos-de-verificación-y-testing)
7. [Post-instalación — Onboarding](#7-post-instalación--onboarding)
8. [Mantenimiento](#8-mantenimiento)

---

## 1. Requisitos Previos

- Dokploy instalado y corriendo en el servidor
- Docker y Docker Compose disponibles
- Dominio configurado con DNS apuntando al servidor (`crm.serviglobal-ia.com`)
- Certificado SSL (gestionado por Dokploy/Traefik automáticamente)

> **⚠️ IMPORTANTE:** Chatwoot requiere PostgreSQL con la extensión **pgvector** (para funcionalidades de IA).  
> No usar la imagen estándar `postgres:14` — usar `pgvector/pgvector:pg14`.

---

## 2. Configuración docker-compose.yml

Ruta en el servidor: `/etc/dokploy/compose/chatwoot-crm-dfqxo1/code/docker-compose.yml`

```yaml
version: "3"

services:
  app:
    image: chatwoot/chatwoot:latest
    depends_on:
      - postgres
      - redis
    ports:
      - "3001:3000"
    environment:
      - RAILS_ENV=production
      - SECRET_KEY_BASE=${SECRET_KEY_BASE}
      - FRONTEND_URL=https://crm.serviglobal-ia.com
      - DEFAULT_LOCALE=es
      - FORCE_SSL=true
      - ENABLE_ACCOUNT_SIGNUP=false
      # Base de datos
      - DATABASE_URL=postgresql://chatwoot:${POSTGRES_PASSWORD}@postgres:5432/chatwoot_production
      # Redis
      - REDIS_URL=redis://redis:6379
      # Email (SMTP)
      - MAILER_SENDER_EMAIL=${MAILER_SENDER_EMAIL}
      - SMTP_ADDRESS=${SMTP_ADDRESS}
      - SMTP_PORT=${SMTP_PORT}
      - SMTP_USERNAME=${SMTP_USERNAME}
      - SMTP_PASSWORD=${SMTP_PASSWORD}
      - SMTP_AUTHENTICATION=plain
      - SMTP_ENABLE_STARTTLS_AUTO=true
    volumes:
      - chatwoot_storage:/app/storage
    entrypoint: docker/entrypoints/rails.sh
    command: ["bundle", "exec", "rails", "s", "-p", "3000", "-b", "0.0.0.0"]
    restart: unless-stopped

  sidekiq:
    image: chatwoot/chatwoot:latest
    depends_on:
      - postgres
      - redis
    environment:
      - RAILS_ENV=production
      - SECRET_KEY_BASE=${SECRET_KEY_BASE}
      - FRONTEND_URL=https://crm.serviglobal-ia.com
      - DATABASE_URL=postgresql://chatwoot:${POSTGRES_PASSWORD}@postgres:5432/chatwoot_production
      - REDIS_URL=redis://redis:6379
    volumes:
      - chatwoot_storage:/app/storage
    entrypoint: docker/entrypoints/sidekiq.sh
    command: ["bundle", "exec", "sidekiq", "-C", "config/sidekiq.yml"]
    restart: unless-stopped

  postgres:
    # ⚠️ CRÍTICO: usar pgvector — NO usar postgres:14 estándar
    image: pgvector/pgvector:pg14
    environment:
      - POSTGRES_USER=chatwoot
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
      - POSTGRES_DB=chatwoot_production
    volumes:
      - chatwoot_postgres:/var/lib/postgresql/data
    restart: unless-stopped

  redis:
    image: redis:alpine
    volumes:
      - chatwoot_redis:/data
    restart: unless-stopped

volumes:
  chatwoot_storage:
  chatwoot_postgres:
  chatwoot_redis:
```

### Variables de entorno requeridas (.env)

```env
SECRET_KEY_BASE=<clave_aleatoria_64_chars>  # rails secret
POSTGRES_PASSWORD=<password_seguro>
MAILER_SENDER_EMAIL=noreply@serviglobal-ia.com
SMTP_ADDRESS=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=<tu_email@gmail.com>
SMTP_PASSWORD=<app_password_gmail>
```

> Generar `SECRET_KEY_BASE`: `openssl rand -hex 64`

---

## 3. Despliegue Inicial

### 3.1 Levantar servicios de infraestructura

```bash
cd /etc/dokploy/compose/chatwoot-crm-dfqxo1/code

# Levantar postgres y redis primero
docker compose -p chatwoot-crm-dfqxo1 up -d postgres redis

# Esperar que postgres esté listo
sleep 10 && docker exec chatwoot-crm-dfqxo1-postgres-1 pg_isready -U chatwoot
```

### 3.2 Preparar la base de datos

```bash
# Opción A: Preparación completa (primera vez)
docker compose -p chatwoot-crm-dfqxo1 run --rm app bundle exec rails db:chatwoot_prepare

# Opción B: Solo migraciones (si la BD ya existe)
docker compose -p chatwoot-crm-dfqxo1 run --rm app bundle exec rails db:migrate

# Opción C: Seed de datos iniciales
docker compose -p chatwoot-crm-dfqxo1 run --rm app bundle exec rails db:seed
```

### 3.3 Levantar todos los servicios

```bash
docker compose -p chatwoot-crm-dfqxo1 up -d
```

---

## 4. Configuración de Base de Datos

### Habilitar extensión pgvector manualmente

Si la extensión `vector` no está habilitada automáticamente:

```bash
docker exec chatwoot-crm-dfqxo1-postgres-1 psql -U chatwoot -d chatwoot_production -c \
  "CREATE EXTENSION IF NOT EXISTS vector;"
```

### Verificar extensión instalada

```bash
docker exec chatwoot-crm-dfqxo1-postgres-1 psql -U chatwoot -d chatwoot_production -c \
  "SELECT name, installed_version FROM pg_available_extensions WHERE name = 'vector';"
```

**Resultado esperado:**
```
  name  | installed_version
--------+-------------------
 vector | 0.8.2
```

---

## 5. Solución de Problemas Conocidos

### ❌ Bug: Migración `20231211010807` falla con `ActsAsTaggableOn`

**Error:**
```
NameError: uninitialized constant ActsAsTaggableOn::Taggable::Cache
```

**Causa:** Incompatibilidad de la gema `acts-as-taggable-on` con la versión de Chatwoot.

**Fix manual:**
```bash
docker exec chatwoot-crm-dfqxo1-postgres-1 psql -U chatwoot -d chatwoot_production -c "
  ALTER TABLE conversations ADD COLUMN IF NOT EXISTS cached_label_list character varying;
  INSERT INTO schema_migrations (version) VALUES ('20231211010807') ON CONFLICT DO NOTHING;
"

# Continuar migraciones
docker compose -p chatwoot-crm-dfqxo1 run --rm app bundle exec rails db:migrate
```

---

### ❌ Error: `could not open extension control file... vector.control`

**Causa:** Se está usando la imagen `postgres:14` estándar sin soporte de pgvector.

**Fix:**
1. Actualizar `docker-compose.yml` — cambiar la imagen de postgres:
   ```yaml
   # Incorrecto
   image: postgres:14
   
   # Correcto
   image: pgvector/pgvector:pg14
   ```

2. Recrear el contenedor de postgres:
   ```bash
   docker compose -p chatwoot-crm-dfqxo1 stop postgres
   docker compose -p chatwoot-crm-dfqxo1 rm -f postgres
   docker compose -p chatwoot-crm-dfqxo1 up -d postgres
   ```

> **⚠️ ADVERTENCIA:** Si Dokploy revierte la configuración, verificar que el archivo en  
> `/etc/dokploy/compose/chatwoot-crm-dfqxo1/code/docker-compose.yml` tenga la imagen correcta  
> **antes** de ejecutar el redeploy desde el dashboard.

---

### ❌ Volúmenes en conflicto por proyectos duplicados

Si existen volúmenes bajo el proyecto `code` (temporal) además del proyecto `chatwoot-crm-dfqxo1`:

```bash
# Verificar volúmenes
docker volume ls | grep chatwoot

# Limpiar volúmenes del proyecto temporal "code"
docker compose -p code down -v
```

---

## 6. Comandos de Verificación y Testing

### 6.1 Estado general

```bash
# Estado de todos los contenedores
docker compose -p chatwoot-crm-dfqxo1 ps

# Resultado esperado: app, sidekiq, postgres, redis en Status "Up"
```

### 6.2 Verificación de base de datos

```bash
# Contar tablas (esperado: ~90-115)
docker exec chatwoot-crm-dfqxo1-postgres-1 psql -U chatwoot -d chatwoot_production -c \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';"

# Verificar extensión pgvector
docker exec chatwoot-crm-dfqxo1-postgres-1 psql -U chatwoot -d chatwoot_production -c \
  "SELECT name, installed_version FROM pg_available_extensions WHERE name = 'vector';"

# Verificar migraciones pendientes (no debe mostrar ninguna "down")
docker compose -p chatwoot-crm-dfqxo1 run --rm app bundle exec rails db:migrate:status 2>&1 | grep "down"

# Imagen del contenedor postgres
docker inspect chatwoot-crm-dfqxo1-postgres-1 --format '{{.Config.Image}}'
# Esperado: pgvector/pgvector:pg14
```

### 6.3 Verificación de la aplicación

```bash
# Logs de la app (últimas 50 líneas)
docker compose -p chatwoot-crm-dfqxo1 logs --tail=50 app

# Logs de sidekiq
docker compose -p chatwoot-crm-dfqxo1 logs --tail=50 sidekiq

# Test de conectividad HTTP (debe responder 200 o 302)
curl -I https://crm.serviglobal-ia.com

# Test de health check interno
curl -s http://localhost:3001/auth/sign_in | head -c 200
```

### 6.4 Verificación de Redis

```bash
# Ping a Redis
docker exec chatwoot-crm-dfqxo1-redis-1 redis-cli ping
# Esperado: PONG

# Ver estadísticas de Redis
docker exec chatwoot-crm-dfqxo1-redis-1 redis-cli info | grep connected_clients
```

### 6.5 Script de verificación completa

```bash
#!/bin/bash
echo "=== CHATWOOT HEALTH CHECK ==="
echo ""

echo "--- Contenedores ---"
docker compose -p chatwoot-crm-dfqxo1 ps --format "table {{.Name}}\t{{.Status}}"

echo ""
echo "--- PostgreSQL: imagen ---"
docker inspect chatwoot-crm-dfqxo1-postgres-1 --format '{{.Config.Image}}'

echo ""
echo "--- PostgreSQL: extensión vector ---"
docker exec chatwoot-crm-dfqxo1-postgres-1 psql -U chatwoot -d chatwoot_production -c \
  "SELECT name, installed_version FROM pg_available_extensions WHERE name = 'vector';" 2>/dev/null

echo ""
echo "--- PostgreSQL: tablas ---"
docker exec chatwoot-crm-dfqxo1-postgres-1 psql -U chatwoot -d chatwoot_production -c \
  "SELECT count(*) AS total_tablas FROM information_schema.tables WHERE table_schema='public';" 2>/dev/null

echo ""
echo "--- Redis ---"
docker exec chatwoot-crm-dfqxo1-redis-1 redis-cli ping

echo ""
echo "--- HTTP Status ---"
curl -s -o /dev/null -w "HTTP Status: %{http_code}\n" https://crm.serviglobal-ia.com

echo ""
echo "=== FIN DEL HEALTH CHECK ==="
```

Guardar como `/root/chatwoot-health-check.sh` y ejecutar con:
```bash
chmod +x /root/chatwoot-health-check.sh && /root/chatwoot-health-check.sh
```

---

## 7. Post-instalación — Onboarding

Una vez que todos los servicios están `Up`, completar el onboarding en:

```
https://crm.serviglobal-ia.com/installation/onboarding
```

**Pasos del wizard:**
1. Crear cuenta de administrador (nombre, email, contraseña)
2. Configurar nombre de la empresa (`Serviglobal IA`)
3. Crear primer inbox (WhatsApp Business / Email)

**Información útil para el onboarding:**
- Tener a mano las credenciales de WhatsApp Business API
- Tener la App Password de Gmail para SMTP
- El primer usuario creado será el Super Admin

---

## 8. Mantenimiento

### Actualizar Chatwoot

```bash
# Bajar servicios
docker compose -p chatwoot-crm-dfqxo1 down

# Actualizar imagen
docker pull chatwoot/chatwoot:latest

# Levantar y migrar
docker compose -p chatwoot-crm-dfqxo1 up -d postgres redis
sleep 10
docker compose -p chatwoot-crm-dfqxo1 run --rm app bundle exec rails db:migrate
docker compose -p chatwoot-crm-dfqxo1 up -d
```

### Backup de base de datos

```bash
# Crear backup
docker exec chatwoot-crm-dfqxo1-postgres-1 pg_dump -U chatwoot chatwoot_production \
  > /root/backups/chatwoot_$(date +%Y%m%d_%H%M%S).sql

# Restaurar backup
docker exec -i chatwoot-crm-dfqxo1-postgres-1 psql -U chatwoot chatwoot_production \
  < /root/backups/chatwoot_YYYYMMDD_HHMMSS.sql
```

### Ver logs en tiempo real

```bash
# Todos los servicios
docker compose -p chatwoot-crm-dfqxo1 logs -f

# Solo app
docker compose -p chatwoot-crm-dfqxo1 logs -f app

# Solo sidekiq
docker compose -p chatwoot-crm-dfqxo1 logs -f sidekiq
```

### Reiniciar servicios

```bash
# Reiniciar todo
docker compose -p chatwoot-crm-dfqxo1 restart

# Reiniciar solo un servicio
docker compose -p chatwoot-crm-dfqxo1 restart app
docker compose -p chatwoot-crm-dfqxo1 restart sidekiq
```

---

## Resumen del Stack

| Servicio | Imagen | Puerto | Función |
|---|---|---|---|
| `app` | `chatwoot/chatwoot:latest` | 3001→3000 | Rails app (UI + API) |
| `sidekiq` | `chatwoot/chatwoot:latest` | — | Background jobs |
| `postgres` | `pgvector/pgvector:pg14` | 5432 | Base de datos + vectores |
| `redis` | `redis:alpine` | 6379 | Cache + colas de Sidekiq |

---

*Documentación generada durante la instalación de Chatwoot para Serviglobal IA — Marzo 2026*
