# WhatsApp + Chatwoot + Python — Arquitectura de Mensajería

> **Proyecto:** Serviglobal IA  
> **Backend:** `https://api.serviglobal-ia.com`  
> **CRM:** `https://crm.serviglobal-ia.com`  
> **Última actualización:** Marzo 2026  

---

## Índice

1. [Visión General](#1-visión-general)
2. [Mensajes Entrantes (Cliente → Agente IA)](#2-mensajes-entrantes-cliente--agente-ia)
3. [Mensajes Salientes (Agente IA → Cliente)](#3-mensajes-salientes-agente-ia--cliente)
4. [Notificaciones de Reserva — Sistema Completo](#4-notificaciones-de-reserva--sistema-completo)
5. [Plantillas de WhatsApp (Templates)](#5-plantillas-de-whatsapp-templates)
6. [Escalamiento a Humano](#6-escalamiento-a-humano)
7. [Configuración de Webhooks](#7-configuración-de-webhooks)
8. [Variables de Entorno](#8-variables-de-entorno)
9. [Referencia de Endpoints](#9-referencia-de-endpoints)
10. [Diagramas de Secuencia](#10-diagramas-de-secuencia)
11. [Notas de Mantenimiento](#11-notas-de-mantenimiento)

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

### Regla de oro de las plantillas

> ⚠️ **Chatwoot NO soporta el envío de templates personalizados vía API.**  
> Por esta razón, **todas las plantillas van directo a Meta Cloud API** y luego  
> se registran como **notas internas (privadas) en Chatwoot CRM** para trazabilidad.

### Stack completo

```
┌──────────────────────────────────────────────────────────────────────┐
│                         CLIENTE FINAL                                │
│                    (WhatsApp en su teléfono)                         │
└─────────────────────────┬────────────────────────────────────────────┘
                          │ WhatsApp
                          ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    META CLOUD API                                     │
│              graph.facebook.com/v23.0/...                            │
│  • Recibe mensajes entrantes del cliente                              │
│  • Envía plantillas aprobadas (templates)                            │
│  • Retransmite eventos a Chatwoot via webhook                        │
└─────────────────────────┬────────────────────────────────────────────┘
                          │ Webhook (entrantes) / API REST (salientes)
                          ▼
┌──────────────────────────────────────────────────────────────────────┐
│                   CHATWOOT CRM                                        │
│              crm.serviglobal-ia.com                                  │
│  • Almacena todas las conversaciones                                  │
│  • Notas internas de plantillas enviadas ← NUEVO                     │
│  • UI para agentes humanos                                            │
│  • Dispara webhooks al Python Backend                                 │
└─────────────────────────┬────────────────────────────────────────────┘
                          │ Webhook POST (eventos) / API REST (mensajes)
                          ▼
┌──────────────────────────────────────────────────────────────────────┐
│                  PYTHON BACKEND (IA)                                  │
│              api.serviglobal-ia.com                                  │
│                                                                      │
│  notification_service.py  ← NUEVO — hub de plantillas                │
│    • alerta_lead_owner    → equipo Serviglobal (3 números)           │
│    • cita_confirmada      → número del cliente                       │
│    • Nota interna en CRM tras cada envío                             │
│                                                                      │
│  chatwoot_service.py — gestión de contactos y conversaciones         │
│  whatsapp_service.py — envío de texto libre via Chatwoot             │
│  chatwoot_webhook.py — IA responde mensajes entrantes                │
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
    │  • Ejecuta lógica de IA (generate_ai_response)
    │
    │ 4. POST crm.serviglobal-ia.com/.../conversations/123/messages
    │    {content: "¡Hola! Puedo ayudarte con...", message_type: "outgoing"}
    ▼
Chatwoot CRM → Meta → Cliente WhatsApp ✅
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
        return {"status": "ignored"}   # ← anti-bucle: ignorar respuestas del bot

    conversation_id = payload["conversation"]["id"]
    message_content = payload["content"]
    contact_name    = payload["contact"]["name"]

    ai_response = await generate_ai_response(message_content, contact_name, conversation_id)
    if ai_response:
        await chatwoot_service.send_message(conversation_id, ai_response)
```

### Payload de Chatwoot (lo que llega a tu Python)

```json
{
  "event": "message_created",
  "message_type": "incoming",
  "content": "Hola, quiero información sobre sus servicios",
  "conversation": { "id": 123, "status": "open", "inbox_id": 1 },
  "contact": {
    "id": 45,
    "name": "Juan García",
    "phone_number": "+573201234567"
  }
}
```

---

## 3. Mensajes Salientes (Agente IA → Cliente)

Para responder a un cliente, el Python backend usa la API de Chatwoot (texto libre).

> ⚠️ **Diferencia clave:** Los mensajes de texto libre se envían vía Chatwoot API.  
> Las **plantillas aprobadas** siempre van directo a Meta (ver Sección 4 y 5).

```python
from app.services.chatwoot_service import chatwoot_service

# Respuesta visible para el cliente
await chatwoot_service.send_message(conversation_id, "¡Hola! ¿En qué te ayudo?", private=False)

# Nota interna (solo agentes la ven)
await chatwoot_service.send_message(conversation_id, "🤖 El bot respondió", private=True)
```

---

## 4. Notificaciones de Reserva — Sistema Completo

> **Archivo:** `app/services/notification_service.py`  
> **Endpoint:** `POST /api/v1/notifications/booking`

Esta es la funcionalidad más importante del sistema de notificaciones.
Cuando se confirma una cita, **se disparan dos plantillas simultáneamente**:

### Las dos plantillas

| Plantilla | Destinatario | Variables |
|---|---|---|
| `alerta_lead_owner` | **Equipo Serviglobal** (3 números fijos) | `{{1}}` name, `{{2}}` date_str, `{{3}}` time_str |
| `cita_confirmada_cliente` | **Número del cliente** (dinámico) | `{{1}}` name, `{{2}}` date_str, `{{3}}` time_str |

### Números fijos del equipo (alerta_lead_owner)

```python
OWNER_PHONES = [
    "+573106666709",   # Tatiana
    "+573014023104",
    "+573178193641",
]
```

### Flujo de notificación de cita

```
evento: cita agendada
    │
    ├── notification_service.notify_new_booking(client_phone, name, date, time)
    │
    ├─── [asyncio.gather] Envío paralelo a los 3 dueños ───────────────────────
    │        │
    │        ├── Meta API: alerta_lead_owner → +573106666709
    │        │       └── Nota interna Chatwoot (solo agentes) ✅
    │        ├── Meta API: alerta_lead_owner → +573014023104
    │        │       └── Nota interna Chatwoot ✅
    │        └── Meta API: alerta_lead_owner → +573178193641
    │                └── Nota interna Chatwoot ✅
    │
    └─── Envío al cliente ───────────────────────────────────────────────────
             │
             ├── Meta API: cita_confirmada_cliente → +57CLIENTE
             │       └── Nota interna Chatwoot + label "cita-confirmada" ✅
             │
             └── El agente ve TODA la actividad en el CRM ✅
```

### Uso desde código Python

```python
from app.services.notification_service import notification_service

# Llamar cuando Cal.com confirma una reserva
results = await notification_service.notify_new_booking(
    client_phone="+573201234567",
    client_name="Juan García",
    date_str="Miércoles 2 de abril de 2026",
    time_str="10:00 AM",
    client_email="juan@empresa.com",   # opcional
)
# results = {
#   "alerta_owners": [{"phone": "+573106666709", "ok": True}, ...],
#   "confirmacion_cliente": {"phone": "+573201234567", "ok": True}
# }
```

### Uso desde HTTP (curl / frontend / n8n / agente)

```bash
curl -X POST https://api.serviglobal-ia.com/api/v1/notifications/booking \
  -H "Content-Type: application/json" \
  -d '{
    "client_phone": "+573201234567",
    "client_name": "Juan García",
    "date_str": "Miércoles 2 de abril de 2026",
    "time_str": "10:00 AM",
    "client_email": "juan@empresa.com"
  }'
```

**Respuesta:**
```json
{
  "status": "ok",
  "results": {
    "alerta_owners": [
      {"phone": "+573106666709", "ok": true},
      {"phone": "+573014023104", "ok": true},
      {"phone": "+573178193641", "ok": true}
    ],
    "confirmacion_cliente": {"phone": "+573201234567", "ok": true}
  }
}
```

### Lo que el agente ve en Chatwoot

Después de cada envío de plantilla, aparece una **nota privada** como esta:

```
📢 Alerta de nuevo lead enviada al equipo
• Cliente: Juan García
• Fecha: Miércoles 2 de abril de 2026
• Hora: 10:00 AM
• Plantilla: alerta_lead_owner
```

```
✅ Confirmación de cita enviada al cliente
• Nombre: Juan García
• Fecha: Miércoles 2 de abril de 2026
• Hora: 10:00 AM
• Plantilla: cita_confirmada_cliente
```

---

## 5. Plantillas de WhatsApp (Templates)

### Por qué las plantillas van directo a Meta (nunca por Chatwoot)

1. Chatwoot **no soporta** el envío de templates personalizados vía API.
2. Las plantillas son mensajes pre-aprobados por Meta con variables fijas.
3. El registro en CRM se hace via nota interna **después** del envío.

### Cuándo usar plantillas vs texto libre

| Situación | Tipo | Servicio |
|---|---|---|
| Responder en <24h al cliente | Texto libre | `chatwoot_service.send_message()` |
| Confirmación de cita nueva | ✅ Plantilla | `notification_service.notify_new_booking()` |
| Alerta al equipo por nuevo lead | ✅ Plantilla | `notification_service.notify_new_booking()` |
| Recordatorio pasadas 24h | ✅ Plantilla | `whatsapp_service.send_template_message()` |
| Nota informativa ad-hoc | Texto libre | `whatsapp_service.send_notification()` |

### Componentes de plantilla (formato Meta)

Las dos plantillas de Serviglobal usan este formato de componentes:

```python
components = [
    {
        "type": "body",
        "parameters": [
            {"type": "text", "text": name},       # {{1}}
            {"type": "text", "text": date_str},   # {{2}}
            {"type": "text", "text": time_str},   # {{3}}
        ],
    }
]
```

---

## 6. Escalamiento a Humano

Cuando el agente IA no puede resolver la consulta:

```python
from app.services.chatwoot_service import chatwoot_service

# Detectar palabras clave en chatwoot_webhook.py
if any(w in message.lower() for w in ["humano", "agente", "persona", "asesor"]):
    await chatwoot_service.send_message(conv_id, "Te conecto con un asesor... 👤")
    await chatwoot_service.add_label(conv_id, ["escalar-a-humano"])
    await chatwoot_service.update_conversation_status(conv_id, "open")
    return None  # No enviar respuesta del bot
```

---

## 7. Configuración de Webhooks

### 7.1 Webhook 1: Meta → Chatwoot

| Campo | Valor |
|---|---|
| URL | `https://crm.serviglobal-ia.com/webhooks/whatsapp/+5732XXXXXXXX` |
| Token | generado por Chatwoot (Settings → Integrations → WhatsApp) |
| Campos | `messages` ✅, `message_deliveries` ✅, `message_reads` (opcional) |

---

### 7.2 Webhook 2: Chatwoot → Python Backend

| Campo | Valor |
|---|---|
| URL | `https://api.serviglobal-ia.com/api/v1/chatwoot/webhook` |
| Eventos | `message_created` ✅, `conversation_created` ✅, `conversation_status_changed` ✅ |

> ⚠️ **Anti-bucle:** filtrar siempre `message_type == "incoming"` en el receptor.  
> Chatwoot envía webhooks también para los mensajes `outgoing` (respuestas del bot).

---

## 8. Variables de Entorno

```env
# ── WhatsApp Cloud API (Meta) ─────────────────────────────────────────
WHATSAPP_API_TOKEN=EAAxxxxxxxxxxxxxx    # System User Token de Meta
WHATSAPP_PHONE_NUMBER_ID=12345678901   # Phone Number ID del número
WHATSAPP_VERIFY_TOKEN=serviglobal_wa_token

# ── Chatwoot CRM ──────────────────────────────────────────────────────
CHATWOOT_API_TOKEN=xxxxxxxxxxxxxx      # Profile → Access Token
CHATWOOT_ACCOUNT_ID=1                  # Settings → General
CHATWOOT_INBOX_ID=1                    # Settings → Inboxes → URL del inbox
```

### Cómo obtener cada credencial

| Variable | Dónde |
|---|---|
| `WHATSAPP_API_TOKEN` | Meta Business Suite → System Users → Generate Token |
| `WHATSAPP_PHONE_NUMBER_ID` | developers.facebook.com → App → WhatsApp → API Setup |
| `CHATWOOT_API_TOKEN` | crm.serviglobal-ia.com → Avatar → Profile Settings → Access Token |
| `CHATWOOT_ACCOUNT_ID` | Settings → General (aparece en la URL: `/accounts/1/`) |
| `CHATWOOT_INBOX_ID` | Settings → Inboxes → click en inbox → número en la URL |

---

## 9. Referencia de Endpoints

### Python Backend

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/api/v1/notifications/webhook` | Verificación handshake Meta |
| `POST` | `/api/v1/notifications/webhook` | Recibe eventos de estado de Meta (delivery/read) |
| `POST` | `/api/v1/notifications/booking` | **🆕 Dispara alerta_lead_owner + cita_confirmada_cliente** |
| `POST` | `/api/v1/chatwoot/webhook` | Recibe eventos de Chatwoot → IA responde |
| `POST` | `/api/v1/calls` | Crea sesión de llamada de voz (Ultravox) |
| `POST` | `/api/v1/call-outbound` | Llamada saliente vía PBX/SIP |
| `GET`  | `/api/v1/availability` | Consulta slots disponibles en Cal.com |
| `POST` | `/api/v1/availability` | Consulta slots (versión POST) |
| `POST` | `/api/v1/bookings` | Crea reserva en Cal.com |
| `GET`  | `/health` | Health check del backend |

### Servicios Python (uso interno)

| Servicio | Archivo | Responsabilidad |
|---|---|---|
| `notification_service` | `services/notification_service.py` | **🆕 Plantillas de citas (templates Meta + notas CRM)** |
| `chatwoot_service` | `services/chatwoot_service.py` | Contactos, conversaciones, mensajes en CRM |
| `whatsapp_service` | `services/whatsapp_service.py` | Texto libre → Chatwoot o Meta (fallback) |

### Chatwoot API (usada por Python)

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/api/v1/accounts/{id}/contacts/search?q=+573...` | Buscar contacto |
| `POST` | `/api/v1/accounts/{id}/contacts` | Crear contacto |
| `GET` | `/api/v1/accounts/{id}/contacts/{cid}/conversations` | Conversaciones del contacto |
| `POST` | `/api/v1/accounts/{id}/conversations` | Crear conversación |
| `POST` | `/api/v1/accounts/{id}/conversations/{cid}/messages` | Enviar mensaje / nota interna |
| `POST` | `/api/v1/accounts/{id}/conversations/{cid}/labels` | Agregar etiquetas |
| `PATCH` | `/api/v1/accounts/{id}/conversations/{cid}` | Actualizar estado |
| `POST` | `/api/v1/accounts/{id}/conversations/{cid}/assignments` | Asignar a agente |

---

## 10. Diagramas de Secuencia

### Mensaje entrante con respuesta automática de IA

```
Cliente     Meta API      Chatwoot       Python (IA)
  │             │              │               │
  │─ "Hola" ──►│              │               │
  │             │─ webhook ──►│               │
  │             │              │─ guarda msg   │
  │             │              │─ webhook ────►│
  │             │              │               │─ genera respuesta
  │             │              │◄─ send_msg ───│
  │             │◄─ API call ──│               │
  │◄─ "¡Hola!" ─│              │               │
```

### Notificación de cita (plantillas) — 🆕

```
Cal.com / Agente     Python (notification_service)    Meta API    Chatwoot    Cliente/Equipo
        │                         │                       │           │             │
        │─ notify_new_booking ───►│                       │           │             │
        │                         │─ template (owner 1) ─►│           │             │
        │                         │                       │────────────────────────►│ +573106666709
        │                         │─ nota interna ────────────────────►│             │
        │                         │─ template (owner 2) ─►│           │             │
        │                         │                       │────────────────────────►│ +573014023104
        │                         │─ template (owner 3) ─►│           │             │
        │                         │                       │────────────────────────►│ +573178193641
        │                         │─ cita_confirmada ────►│           │             │
        │                         │                       │────────────────────────►│ cliente
        │                         │─ nota interna ────────────────────►│             │
        │◄─ results ──────────────│                       │           │             │
```

### Escalamiento a humano

```
Cliente      Chatwoot       Python (IA)     Agente Humano
  │              │               │               │
  │─ "agente" ──►│               │               │
  │              │─ webhook ────►│               │
  │              │               │─ detecta kw   │
  │              │◄─ "te conecto"│               │
  │              │◄─ add_label   │               │
  │◄─ msg ───────│               │               │
  │              │─ notifica ───────────────────►│
  │◄──────────────────────────────── chat directo►│
```

---

## 11. Notas de Mantenimiento

### Agregar un nuevo número al equipo (alerta_lead_owner)

Editar `app/services/notification_service.py`:

```python
OWNER_PHONES: list[str] = [
    "+573106666709",
    "+573014023104",
    "+573178193641",
    "+57XXXXXXXXXX",   # ← agregar aquí
]
```

### Agregar una nueva plantilla

1. Crear y aprobar la plantilla en **Meta Business Manager**
2. Agregar método en `notification_service.py` (copiar patrón de `_send_alerta_lead_owner`)
3. Exponer en el endpoint correspondiente de `notifications.py`

### Si las plantillas fallan (error 190 de Meta)

```
[Template:alerta_lead_owner] Error HTTP 400 — {"error": {"code": 190, ...}}
```
→ El token de Meta expiró. Regenerar en Meta Business Suite → System Users.

### Si las notas no aparecen en Chatwoot

- Verificar `CHATWOOT_API_TOKEN` en `.env` del servidor
- Verificar `CHATWOOT_INBOX_ID` (debe coincidir con el inbox WhatsApp)
- Revisar logs: `docker logs backend-container --tail=50 | grep CRM`

### Si dejan de llegar mensajes del cliente al Python

1. Verificar webhook activo en Chatwoot: Settings → Integrations → Webhooks
2. Probar endpoint manualmente:
```bash
curl -X POST https://api.serviglobal-ia.com/api/v1/chatwoot/webhook \
  -H "Content-Type: application/json" \
  -d '{"event":"test"}'
```

---

*Documentación actualizada — Serviglobal IA — Marzo 2026*  
*Commit: `13520a1` — feat(notifications): booking templates + Chatwoot CRM logging*
