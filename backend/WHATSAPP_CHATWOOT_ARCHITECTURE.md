# WhatsApp + Chatwoot + Python — Arquitectura de Mensajería

> **Proyecto:** Serviglobal IA  
> **Backend:** `https://api.serviglobal-ia.com`  
> **CRM:** `https://crm.serviglobal-ia.com`  
> **Fecha:** Marzo 2026  

---

## Índice

1. [Visión General](#1-visión-general)
2. [Mensajes Entrantes (Cliente → Agente IA)](#2-mensajes-entrantes-cliente--agente-ia)
3. [Mensajes Salientes (Agente IA → Cliente)](#3-mensajes-salientes-agente-ia--cliente)
4. [Notificaciones Proactivas (Backend → Cliente)](#4-notificaciones-proactivas-backend--cliente)
5. [Plantillas de WhatsApp (Templates)](#5-plantillas-de-whatsapp-templates)
6. [Escalamiento a Humano](#6-escalamiento-a-humano)
7. [Configuración de Webhooks](#7-configuración-de-webhooks)
8. [Variables de Entorno](#8-variables-de-entorno)
9. [Referencia de Endpoints](#9-referencia-de-endpoints)
10. [Diagramas de Secuencia](#10-diagramas-de-secuencia)

---

## 1. Visión General

### La arquitectura en una línea

```
WhatsApp ←──── Meta Cloud API ────── Chatwoot CRM ────── Python Backend (IA)
```

### Por qué Chatwoot es el hub central

| Sin Chatwoot (directo) | Con Chatwoot (hub) |
|---|---|
| Mensajes no quedan en CRM | ✅ Todo registrado en CRM |
| Sin escalamiento a humano | ✅ 1 clic para escalar |
| Tú manejas tokens de Meta | ✅ Chatwoot los gestiona |
| Sin historial de contactos | ✅ Historial completo |
| Sin métricas | ✅ Dashboard incluido |

### Stack completo

```
┌──────────────────────────────────────────────────────────────────────┐
│                         CLIENTE FINAL                                │
│                    (WhatsApp en su teléfono)                         │
└─────────────────────────┬────────────────────────────────────────────┘
                          │ HTTPS / WebSocket
                          ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    META CLOUD API                                     │
│              graph.facebook.com/v23.0/...                            │
│  • Recibe mensajes entrantes del cliente                             │
│  • Envía mensajes salientes al cliente                               │
│  • Gestiona tokens de acceso y plantillas                            │
└─────────────────────────┬────────────────────────────────────────────┘
                          │ Webhook POST (mensajes entrantes)
                          │ API REST  (mensajes salientes)
                          ▼
┌──────────────────────────────────────────────────────────────────────┐
│                   CHATWOOT CRM                                        │
│              crm.serviglobal-ia.com                                  │
│  • Almacena todas las conversaciones                                  │
│  • Gestiona contactos                                                 │
│  • UI para agentes humanos                                            │
│  • Dispara webhooks al Python Backend                                 │
└─────────────────────────┬────────────────────────────────────────────┘
                          │ Webhook POST (eventos de conversación)
                          │ API REST  (envío de mensajes)
                          ▼
┌──────────────────────────────────────────────────────────────────────┐
│                  PYTHON BACKEND (IA)                                  │
│              api.serviglobal-ia.com                                  │
│  • Lógica de respuesta automática                                     │
│  • Integración con Cal.com (agendamiento)                             │
│  • Integración con Ultravox (voz)                                     │
│  • Notificaciones proactivas (citas, recordatorios)                  │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 2. Mensajes Entrantes (Cliente → Agente IA)

Cuando un cliente envía un mensaje de WhatsApp, recorre este camino:

### Flujo paso a paso

```
Cliente WhatsApp
    │
    │ 1. Escribe "Hola, quiero información"
    ▼
Meta Cloud API
    │
    │ 2. POST https://crm.serviglobal-ia.com/webhooks/whatsapp/+5732...
    │    {mensaje, número, timestamp}
    ▼
Chatwoot CRM
    │  • Crea/actualiza el contacto
    │  • Guarda el mensaje en la conversación
    │  • Muestra en UI para agentes ✅
    │
    │ 3. POST https://api.serviglobal-ia.com/api/v1/chatwoot/webhook
    │    {event: "message_created", content: "Hola...", conversation_id: 123}
    ▼
Python Backend
    │  • Detecta que es mensaje "incoming"
    │  • Ejecuta lógica de IA (respuesta automática)
    │
    │ 4. POST crm.serviglobal-ia.com/api/v1/accounts/1/conversations/123/messages
    │    {content: "¡Hola! Puedo ayudarte con...", message_type: "outgoing"}
    ▼
Chatwoot CRM
    │  • Guarda la respuesta en la conversación ✅
    │
    │ 5. Envía via Meta Cloud API al cliente
    ▼
Cliente WhatsApp
    • Recibe la respuesta del agente IA ✅
```

### Código: Endpoint que recibe el webhook de Chatwoot

**Archivo:** `app/api/endpoints/chatwoot_webhook.py`

```python
@router.post("/api/v1/chatwoot/webhook")
async def chatwoot_webhook(request: Request):
    payload = await request.json()

    # Solo procesar mensajes entrantes del cliente
    if payload.get("event") != "message_created":
        return {"status": "ignored"}
    if payload.get("message_type") != "incoming":
        return {"status": "ignored"}

    conversation_id = payload["conversation"]["id"]
    message_content = payload["content"]
    contact_name    = payload["contact"]["name"]

    # Lógica de IA → genera respuesta
    ai_response = await generate_ai_response(message_content, contact_name, conversation_id)

    # Envía respuesta por Chatwoot (queda en CRM + llega al cliente)
    await chatwoot_service.send_message(conversation_id, ai_response)
```

### Payload de Chatwoot (lo que llega a tu Python)

```json
{
  "event": "message_created",
  "message_type": "incoming",
  "content": "Hola, quiero información sobre sus servicios",
  "conversation": {
    "id": 123,
    "status": "open",
    "inbox_id": 1
  },
  "contact": {
    "id": 45,
    "name": "Juan García",
    "phone_number": "+573201234567",
    "email": "juan@empresa.com"
  },
  "inbox": {
    "id": 1,
    "channel": "Channel::Whatsapp",
    "name": "WhatsApp Serviglobal"
  }
}
```

---

## 3. Mensajes Salientes (Agente IA → Cliente)

Para responder a un cliente, el Python backend usa la API de Chatwoot.

### Por qué NO usar Meta API directo para respuestas

| Respuesta via Chatwoot API | Respuesta via Meta API directo |
|---|---|
| ✅ Visible en CRM | ❌ No visible en CRM |
| ✅ Agente humano puede ver historial | ❌ Agente no sabe qué respondió el bot |
| ✅ Cuenta en métricas | ❌ No cuenta |
| ✅ Un solo lugar para auditar | ❌ Conversación fragmentada |

### Código: Enviar mensaje de respuesta

```python
from app.services.chatwoot_service import chatwoot_service

# Enviar texto simple
await chatwoot_service.send_message(
    conversation_id=123,
    content="¡Hola! ¿En qué te puedo ayudar?",
    private=False,  # False = el cliente lo ve | True = solo agentes (nota interna)
)

# Agregar etiqueta a la conversación
await chatwoot_service.add_label(123, ["lead-caliente", "agendado"])

# Escalar a agente humano
await chatwoot_service.assign_conversation(123, assignee_id=5)
await chatwoot_service.update_conversation_status(123, "open")
```

### API de Chatwoot usada internamente

```
POST /api/v1/accounts/{account_id}/conversations/{conversation_id}/messages

Headers:
  api_access_token: tu_token_aqui
  Content-Type: application/json

Body:
{
  "content": "texto del mensaje",
  "message_type": "outgoing",
  "private": false
}
```

---

## 4. Notificaciones Proactivas (Backend → Cliente)

Una notificación proactiva es cuando **tu backend inicia** la conversación 
(sin que el cliente haya escrito primero). Ejemplo: confirmación de cita, recordatorio.

### Flujo de notificación proactiva

```
Python Backend
    │
    │ 1. Evento disparador (cita agendada, recordatorio, etc.)
    │
    │ 2. whatsapp_service.send_notification(phone, mensaje, nombre)
    ▼
ChatwootService.send_notification()
    │
    │ 3. get_or_create_contact("+573201234567", "Juan")
    │    → Busca en Chatwoot, crea si no existe
    │
    │ 4. get_or_create_conversation(contact_id)
    │    → Reutiliza conversación abierta o crea nueva
    │
    │ 5. send_message(conversation_id, "Tu cita es mañana a las 10am")
    ▼
Chatwoot CRM
    │  • Guarda notificación en la conversación ✅
    │  • Agentes pueden ver el contexto ✅
    │
    │ 6. Envía vía Meta Cloud API al cliente
    ▼
Cliente WhatsApp
    • Recibe la notificación ✅
```

### Código: Enviar notificación proactiva

```python
from app.services.whatsapp_service import whatsapp_service

# Confirmación de cita (visible en CRM)
await whatsapp_service.send_notification(
    to="+573201234567",
    message=(
        "¡Hola Juan! 📅\n\n"
        "Tu preconsultoría con *Serviglobal IA* está confirmada:\n"
        "📅 Fecha: Miércoles 2 de abril\n"
        "🕙 Hora: 10:00 AM (Colombia)\n"
        "🔗 Enlace: https://meet.google.com/xxx\n\n"
        "Si necesitas reprogramar, responde este mensaje."
    ),
    name="Juan García",
    email="juan@empresa.com",
    labels=["cita-confirmada"],
)
```

### Decisión automática de canal

```python
# En WhatsAppService.send_notification():

if CHATWOOT_API_TOKEN configurado:
    → Envía via Chatwoot  ✅ visible en CRM
else:
    → Envía directo a Meta  ⚠️ no visible en CRM (fallback)
```

---

## 5. Plantillas de WhatsApp (Templates)

Las plantillas son mensajes pre-aprobados por Meta para iniciar conversaciones 
cuando han pasado más de 24h desde el último mensaje del cliente.

### Cuándo usar plantillas vs texto libre

| Situación | Tipo de mensaje |
|---|---|
| Responder en menos de 24h | ✅ Texto libre (send_message) |
| Iniciar conversación nueva | ✅ Plantilla (send_template_message) |
| Recordatorio después de 24h | ✅ Plantilla |
| Notificación de cita (primera vez) | ✅ Plantilla |

### Flujo de plantillas

```
Python Backend
    │
    │ whatsapp_service.send_template_message(phone, "cita_confirmada")
    ▼
Meta Cloud API (directo)
    │  • Las plantillas van directamente a Meta
    │  • Chatwoot no soporta templates via API en todas versiones
    │
    └→ Nota interna en Chatwoot (para registro en CRM) ✅
    ▼
Cliente WhatsApp
    • Recibe la plantilla formateada ✅
```

### Código: Enviar plantilla

```python
from app.services.whatsapp_service import whatsapp_service

# Plantilla simple (sin variables)
await whatsapp_service.send_template_message(
    to="+573201234567",
    template_name="hello_world",
    language_code="en",
    name="Juan García",  # para nota en CRM
)

# Plantilla con variables (componentes)
await whatsapp_service.send_template_message(
    to="+573201234567",
    template_name="cita_confirmada",
    language_code="es",
    name="Juan García",
    components=[
        {
            "type": "body",
            "parameters": [
                {"type": "text", "text": "Juan"},           # {{1}} nombre
                {"type": "text", "text": "2 de abril"},     # {{2}} fecha
                {"type": "text", "text": "10:00 AM"},       # {{3}} hora
            ]
        }
    ]
)
```

---

## 6. Escalamiento a Humano

Cuando el agente IA no puede resolver la consulta, escala a un agente humano.

### Código: Escalar

```python
from app.services.chatwoot_service import chatwoot_service

# Opción A: Escalar a agente específico
await chatwoot_service.assign_conversation(
    conversation_id=123,
    assignee_id=5,  # ID del agente en Chatwoot (Settings → Agents)
)

# Opción B: Dejar en cola (sin asignar) y notificar al equipo
await chatwoot_service.update_conversation_status(123, "open")
await chatwoot_service.add_label(123, ["escalar-a-humano"])

# Dejar nota interna para el agente que tome la conv
await chatwoot_service.send_message(
    123,
    "🤖 El cliente solicitó hablar con un humano. Contexto: quiere negociar precio.",
    private=True,  # nota interna — solo agentes la ven
)
```

### Trigger desde el webhook

```python
# En chatwoot_webhook.py → generate_ai_response()

if any(w in message.lower() for w in ["humano", "agente", "persona", "asesor"]):
    # Notificar al cliente
    await chatwoot_service.send_message(conv_id,
        "Entendido, te conectaré con un asesor. Un momento... 👤"
    )
    # Escalar
    await chatwoot_service.add_label(conv_id, ["escalar-a-humano"])
    await chatwoot_service.update_conversation_status(conv_id, "open")
    return None  # No enviar respuesta automática adicional
```

---

## 7. Configuración de Webhooks

### 7.1 Webhook 1: Meta → Chatwoot

**Quién lo configura:** En el portal de Facebook Developers  
**Dónde:** `developers.facebook.com` → Tu App → WhatsApp → Configuration

```
URL de callback:    https://crm.serviglobal-ia.com/webhooks/whatsapp/+5732XXXXXXXX
Token verificación: 0d099b5484eaa4f5356b7a209d0bdc7a   (generado por Chatwoot)

Campos suscritos:
  ✅ messages              (mensajes entrantes — OBLIGATORIO)
  ✅ message_deliveries    (confirmaciones de entrega)
  ✅ message_reads         (confirmaciones de lectura — opcional)
```

**Verificación:** Meta envía un GET con `hub.challenge` → Chatwoot responde con el challenge ✅

---

### 7.2 Webhook 2: Chatwoot → Python Backend

**Quién lo configura:** En el CRM de Chatwoot  
**Dónde:** `crm.serviglobal-ia.com` → Settings → Integrations → Webhooks

```
URL:    https://api.serviglobal-ia.com/api/v1/chatwoot/webhook

Eventos a suscribir:
  ✅ message_created           (nuevo mensaje, entrante o saliente)
  ✅ conversation_created      (nueva conversación iniciada)
  ✅ conversation_status_changed (cambios de estado: open/resolved/pending)
  ☐ contact_created           (contacto nuevo — opcional)
  ☐ conversation_updated      (cambios generales — opcional)
```

**Nota:** Chatwoot NO envía un challenge de verificación. El endpoint siempre 
debe responder `200 OK` con `{"status": "ok"}`.

---

### 7.3 Endpoint Python: Receptor del webhook de Chatwoot

**Archivo:** `app/api/endpoints/chatwoot_webhook.py`  
**Ruta:** `POST /api/v1/chatwoot/webhook`

```python
@router.post("/api/v1/chatwoot/webhook")
async def chatwoot_webhook(request: Request):
    payload = await request.json()
    event_type   = payload.get("event")          # "message_created"
    message_type = payload.get("message_type")   # "incoming" | "outgoing" | "activity"

    # IMPORTANTE: ignorar mensajes salientes para evitar bucle infinito
    if message_type != "incoming":
        return {"status": "ignored"}

    # Procesar solo eventos de mensaje nuevo
    if event_type != "message_created":
        return {"status": "ignored"}

    # ── Extraer datos ──────────────────────────────────────────────
    conversation_id = payload["conversation"]["id"]
    message_content = payload.get("content", "").strip()
    contact_name    = payload.get("contact", {}).get("name", "Cliente")
    contact_phone   = payload.get("contact", {}).get("phone_number", "")

    # ── IA responde ────────────────────────────────────────────────
    ai_response = await generate_ai_response(message_content, contact_name, conversation_id)

    if ai_response:
        await chatwoot_service.send_message(conversation_id, ai_response)

    return {"status": "ok"}
```

> ⚠️ **Anti-bucle infinito:** Chatwoot envía webhook tanto para mensajes 
> `incoming` (del cliente) como `outgoing` (del bot). Siempre filtrar 
> por `message_type == "incoming"` para no procesar las respuestas del bot.

---

## 8. Variables de Entorno

### Archivo `.env` del backend Python

```env
# ── WhatsApp Cloud API (Meta) ─────────────────────────────────────────
WHATSAPP_API_TOKEN=EAAxxxxxxxxxxxxxx    # System User Token de Meta
WHATSAPP_PHONE_NUMBER_ID=12345678901   # Phone Number ID del número
WHATSAPP_VERIFY_TOKEN=serviglobal_wa_token  # Token para verificar Meta → tu backend (legacy)

# ── Chatwoot CRM ──────────────────────────────────────────────────────
CHATWOOT_API_TOKEN=xxxxxxxxxxxxxx      # Profile → Access Token en Chatwoot
CHATWOOT_ACCOUNT_ID=1                  # Settings → General → Account ID
CHATWOOT_INBOX_ID=1                    # Settings → Inboxes → URL del inbox WhatsApp
```

### Cómo obtener cada credencial

| Variable | Dónde obtenerla |
|---|---|
| `WHATSAPP_API_TOKEN` | Meta Business Suite → System Users → Generate Token |
| `WHATSAPP_PHONE_NUMBER_ID` | developers.facebook.com → App → WhatsApp → API Setup |
| `CHATWOOT_API_TOKEN` | crm.serviglobal-ia.com → Avatar → Profile Settings → Access Token |
| `CHATWOOT_ACCOUNT_ID` | crm.serviglobal-ia.com → Settings → General (aparece en la URL) |
| `CHATWOOT_INBOX_ID` | crm.serviglobal-ia.com → Settings → Inboxes → click en inbox → número en la URL |

### Variables de entorno de Chatwoot (docker-compose)

```yaml
# En /etc/dokploy/compose/chatwoot-crm-dfqxo1/code/docker-compose.yml
environment:
  - FRONTEND_URL=https://crm.serviglobal-ia.com
  - DEFAULT_LOCALE=es
  - ENABLE_ACCOUNT_SIGNUP=false
  - INSTALLATION_NAME=Serviglobal IA
```

---

## 9. Referencia de Endpoints

### Python Backend

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/api/v1/notifications/webhook` | Verificación de webhook Meta (legacy) |
| `POST` | `/api/v1/notifications/webhook` | Recibe eventos directo de Meta (legacy) |
| `POST` | `/api/v1/chatwoot/webhook` | **Recibe eventos de Chatwoot → IA** |
| `POST` | `/api/v1/calls` | Crea sesión de llamada de voz (Ultravox) |
| `POST` | `/api/v1/call-outbound` | Llamada saliente vía PBX/SIP |
| `GET`  | `/api/v1/availability` | Consulta slots disponibles en Cal.com |
| `POST` | `/api/v1/bookings` | Crea reserva en Cal.com |
| `GET`  | `/health` | Health check del backend |

### Chatwoot API (usada por Python)

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/api/v1/accounts/{id}/contacts/search?q=+573...` | Buscar contacto por teléfono |
| `POST` | `/api/v1/accounts/{id}/contacts` | Crear contacto |
| `GET` | `/api/v1/accounts/{id}/contacts/{cid}/conversations` | Conversaciones del contacto |
| `POST` | `/api/v1/accounts/{id}/conversations` | Crear conversación |
| `POST` | `/api/v1/accounts/{id}/conversations/{cid}/messages` | Enviar mensaje |
| `POST` | `/api/v1/accounts/{id}/conversations/{cid}/labels` | Agregar etiquetas |
| `PATCH` | `/api/v1/accounts/{id}/conversations/{cid}` | Actualizar estado |
| `POST` | `/api/v1/accounts/{id}/conversations/{cid}/assignments` | Asignar a agente |

---

## 10. Diagramas de Secuencia

### Mensaje entrante con respuesta automática de IA

```
Cliente     Meta API     Chatwoot       Python (IA)     Cal.com
  │            │             │               │              │
  │─ "Hola" ──►│             │               │              │
  │            │─ webhook ──►│               │              │
  │            │             │─ guarda msg ──│              │
  │            │             │─ webhook ────►│              │
  │            │             │               │─ genera resp │
  │            │             │               │─ ¿agendar? ─►│
  │            │             │               │◄─ slots ─────│
  │            │             │◄─ send_msg ───│              │
  │            │◄─ API call ─│               │              │
  │◄─ "¡Hola!" │             │               │              │
```

### Notificación proactiva (cita confirmada)

```
Cal.com    Python (IA)    Chatwoot       Meta API     Cliente
  │             │              │               │           │
  │─ booking ──►│              │               │           │
  │             │─ get_contact►│               │           │
  │             │◄─ id:45 ─────│               │           │
  │             │─ get_conv ──►│               │           │
  │             │◄─ id:123 ────│               │           │
  │             │─ send_msg ──►│               │           │
  │             │              │─ API call ───►│           │
  │             │              │               │─ msg ────►│
  │             │              │─ guarda msg   │           │
  │             │              │  en CRM ✅    │           │
```

### Escalamiento a humano

```
Cliente     Chatwoot       Python (IA)     Agente Humano
  │             │               │               │
  │─ "agente" ─►│               │               │
  │             │─ webhook ────►│               │
  │             │               │─ detecta kw   │
  │             │◄─ "te conecto"│               │
  │             │◄─ add_label   │               │
  │             │◄─ assign ─────│               │
  │◄─ "te conecto"              │               │
  │             │─ notifica ───────────────────►│
  │             │               │               │─ ve conv │
  │             │               │               │  en CRM  │
  │◄───────────────────────────────────────────►│ (chat directo)
```

---

## Notas de Mantenimiento

### Si dejan de llegar mensajes al Python desde Chatwoot

1. Verificar que el webhook está activo en Chatwoot:
   ```
   Settings → Integrations → Webhooks → buscar la URL → estado ✅
   ```
2. Revisar logs del backend:
   ```bash
   docker logs tu-contenedor-python --tail=50
   ```
3. Verificar que el backend esté respondiendo 200:
   ```bash
   curl -X POST https://api.serviglobal-ia.com/api/v1/chatwoot/webhook \
     -H "Content-Type: application/json" \
     -d '{"event":"test"}'
   ```

### Si los mensajes no llegan de WhatsApp a Chatwoot

1. Verificar webhook en Meta Developers (debe estar verificado ✅)
2. Verificar que el inbox de WhatsApp está activo en Chatwoot
3. Revisar logs de Chatwoot:
   ```bash
   docker compose -p chatwoot-crm-dfqxo1 logs --tail=50 app
   ```

### Si las notificaciones no se ven en el CRM

- Verificar que `CHATWOOT_API_TOKEN` está configurado en el `.env`
- Verificar que `CHATWOOT_INBOX_ID` corresponde al inbox de WhatsApp
- El fallback (sin token) envía directo a Meta sin pasar por Chatwoot

---

*Documentación generada — Serviglobal IA — Marzo 2026*
