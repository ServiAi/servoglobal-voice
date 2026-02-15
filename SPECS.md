# SPEC — Agentes de Voz + Omnicanal + Click-to-IA-Call (Producto + Landing)

> Documento único que consolida: (A) Especificación de Producto/Servicio y (B) Especificación de Landing Page.
> Restricciones aplicadas: no mencionar herramientas específicas, no explicar implementación, no mencionar multitenancy.

---

# A) SPEC (Producto) — Agentes de Voz + Omnicanal + Click-to-IA-Call

## A0) Enfoque del servicio

- **Tipo de oferta:** consultoría + implementación personalizada (no autoservicio).
- **Mercados:** Colombia / LATAM / USA.
- **Objetivo:** habilitar agentes de voz/omnicanal integrados al negocio del cliente, con énfasis en **cierre** (agendamiento, venta, resolución de tickets, cobranza).

---

## A1) Definiciones clave

- **Click-to-IA-Call (Core):** experiencia donde el usuario abre una URL/widget, completa un formulario por embudo, y queda conectado con un agente de IA **con contexto previo**.
- **IA te llama ahora (Modo Callback):** variante donde el usuario deja su número y el sistema dispara una llamada para iniciar conversación con contexto.
- **Context Pack:** paquete estructurado con los datos del formulario + metadata (vertical, campaña, idioma, intención) entregado al agente antes de hablar.
- **Outcome (Resultado de llamada):** estado final verificable de la interacción (agendado, ticket, escalado, etc.).

---

## A2) Oferta base (qué se entrega)

### A2.1 Preconsultoría (Diagnóstico)

- Levantamiento de proceso (AS-IS), objetivos (TO-BE), riesgos, métricas y restricciones.
- Entregables mínimos:
  - Mapa de flujo (alto nivel + variantes)
  - Lista de campos del embudo (formulario) por vertical
  - Definición de outcomes y handoff
  - Propuesta técnica/operativa (alto nivel)

### A2.2 Implementación (Setup + Piloto)

- **Setup es obligatorio y siempre se cobra** (trabajo personalizado).
- Piloto funcional con:
  - Flujos conversacionales por vertical (alcance acordado)
  - Embudo Click-to-IA-Call con Context Pack
  - Reglas de handoff humano (voz o mensajería) según decisión del cliente
  - Registro de outcomes

### A2.3 Producción y Optimización

- Monitoreo de calidad, iteración de flujos y optimización por métricas.
- Soporte según plan.

---

## A3) Reglas funcionales del Core: Click-to-IA-Call

### A3.1 Regla: “Formulario antes de llamada”

- Toda llamada originada desde Click-to-IA-Call **debe** iniciar con un formulario.
- El formulario **no puede** omitirse salvo autorización explícita del cliente.

### A3.2 Regla: embudo por vertical

- El sistema debe tener embudos configurables por modelo de negocio (vertical).
- Cada embudo define:
  - **Campos obligatorios (3–7)**
  - Campos condicionales
  - Intención primaria (agendar / vender / ticket / cobranza / reclutamiento)
  - Validaciones mínimas (formato, obligatoriedad, consistencia)

### A3.3 Regla: Context Pack obligatorio

- Antes de iniciar conversación, el agente recibe el **Context Pack**.
- El agente debe:
  - Confirmar 1–2 datos clave (sin repetir todo el formulario)
  - Ir directo al objetivo (cierre) con mínima fricción

### A3.4 Regla: duración promedio de conversación (operativo)

- El diseño conversacional debe apuntar a **interacciones promedio de 3–5 minutos** para el flujo estándar (sin sacrificar calidad).

---

## A4) Outcomes (resultados) y trazabilidad

**A4.1 — Outcomes mínimos soportados (obligatorio):**

1. Agendado
2. Lead calificado (no agenda)
3. Ticket creado/actualizado
4. Pago / promesa de pago
5. Escalado a humano
6. No contactado / abandono

**A4.2 — Registro mínimo por interacción:**

- Fecha/hora, vertical, campaña, duración, outcome final, razón de escalamiento (si aplica).

---

## A5) Mensajería para agendamiento (confirmación + recordatorio)

**A5.1 — Secuencia mínima:**

- 1. Confirmación inmediata del agendamiento
- 2. Recordatorio (configurable: 24h / 2h antes u otra regla del cliente)

**A5.2 — Mensaje con contexto:**

- Debe incluir: fecha/hora, canal de contacto, opción de reprogramación/cancelación (si el cliente lo requiere).

> Nota: En mercados como USA, las reglas de consentimiento pueden ser más estrictas. Siempre capturar consentimiento cuando aplique.

---

## A6) Handoff a humano (decisión del cliente)

**A6.1 — Modalidades:**

- Handoff por **llamada** (infraestructura del cliente o equivalente)
- Handoff por **mensajería/CRM** (según preferencia del cliente)

**A6.2 — Transferencia con contexto:**

- Todo handoff debe adjuntar:
  - Resumen corto (1–3 bullets)
  - Datos del embudo (Context Pack)
  - Motivo del handoff

---

## A7) Analítica y exportación (opcional)

**A7.1 — Es opcional por cliente:**

- Si el cliente lo solicita, se habilita exportación de métricas para análisis propio.

**A7.2 — Métricas recomendadas:**

- Conversión formulario→llamada, llamada→outcome, tasa de agendamiento, tasa de handoff, duración promedio, razones de abandono.

---

## A8) Servicio adicional: habilitación/configuración de infraestructura de voz del cliente

**A8.1 — Servicio consultivo adicional:**

- Si el cliente tiene infraestructura de voz propia, se ofrece acompañamiento/configuración para integrarla con los agentes.

**A8.2 — Alcance siempre por diagnóstico:**

- El alcance depende del estado actual, restricciones, seguridad y objetivos operativos del cliente.

---

## A9) “Super Plus” (Add-On Premium) — definición

**Super Plus** es un paquete premium orientado a aumentar conversión y control del embudo Click-to-IA-Call.

**A9.1 — Incluye (mínimo):**

- Widget/URL Click-to-IA-Call con personalización por campañas
- Embudos avanzados por vertical (ramificación, scoring, campos dinámicos)
- Tracking de conversión por campaña (campaign_id / UTM)
- Controles anti-abuso (rate limit, validaciones, protección de spam)
- Ruteo inteligente hacia humano (según reglas del cliente)

---

## A10) Precios (Carta de precios) — Setup + mensual + consumo

> El pricing debe presentarse siempre como: **Setup (obligatorio) + Mensualidad + Consumo variable**.

### A10.1 Reglas de cobro

- **Setup obligatorio:** se cobra siempre (implementación personalizada).
- **Mensualidad:** operación, soporte, mantenimiento y mejoras menores (según plan).
- **Consumo variable:** minutos de conversación y mensajería (según canal y país).

### A10.2 Tabla recomendada (editable)

| Plan    | Ideal para                | Incluye (resumen)                                    |      Mensual |        Setup |
| ------- | ------------------------- | ---------------------------------------------------- | -----------: | -----------: |
| Starter | 1 vertical / bajo volumen | Click-to-IA-Call base + flujos esenciales + outcomes |   Desde $299 |   Desde $900 |
| Growth  | 2–3 verticales            | + automatizaciones + reporting                       |   Desde $699 | Desde $1.800 |
| Scale   | alto volumen              | + optimización continua + soporte avanzado           | Desde $1.499 | Desde $3.500 |

**Add-On Super Plus:**

- Mensual: Desde $199
- Setup adicional: Desde $600

**Overage (consumo):**

- Minutos extra y mensajería adicional se facturan por encima del bundle del plan.

---

## A11) Cumplimiento y consentimiento (especialmente USA)

**A11.1 — Consentimiento explícito:**

- Para callbacks (“IA te llama ahora”) el formulario debe capturar consentimiento del usuario final para ser contactado.
- Debe registrar el origen del consentimiento (fecha/hora + evidencia disponible).

**A11.2 — Preferencias de contacto:**

- El usuario final debe poder elegir canal (llamada/mensajería) si el cliente lo exige por compliance.

---

---

# B) SPEC (Landing) — Página comercial con Pricing + Demo Click-to-IA-Call

## B1) Objetivo del landing

1. **Convertir a preconsultoría** (diagnóstico + propuesta).
2. **Demostrar el core:** Click-to-IA-Call (formulario → llamada IA con contexto).
3. **Convertir demo → agendamiento o lead calificado**.

---

## B2) Mensaje principal (above the fold)

**B2.1 — En 7 segundos el usuario entiende:**

- Implementación de **Agentes de Voz + Omnicanal**.
- Servicio **personalizado** (no autoservicio).
- **Click-to-IA-Call:** formulario inteligente → llamada con IA con contexto → cierre.
- Integración con operación existente del cliente.

**B2.2 — Hero (copy recomendado):**

- Titular: “Agentes de Voz con IA para atender, vender y resolver — integrados a tu operación.”
- Subtítulo: “Activa Click-to-IA-Call: formulario inteligente → llamada con IA con contexto → cierre (agenda/venta/ticket).”
- CTAs visibles:
  1. “Agendar preconsultoría”
  2. “Probar IA ahora”

---

## B3) Sección “Elige tu caso de uso” (7 verticales)

Tarjetas o tabs (obligatorio):

1. Atención al Cliente
2. Call Centers y Soporte Técnico
3. Cobranza y Recuperación de Pagos
4. Ventas y Generación de Leads
5. Reclutamiento y Selección
6. Reservaciones y Agendamiento
7. E-commerce y Tiendas Online

**B3.1 — Cada tarjeta incluye:**

- Resultado esperado (1 línea)
- 3 tareas automatizables
- CTA “Agendar diagnóstico para [vertical]”
- Botón “Probar IA ahora para [vertical]” (abre formulario específico)

---

## B4) Demo: Click-to-IA-Call (sección obligatoria)

**B4.1 — El demo NO es genérico:**

- Siempre es un embudo por vertical.
- Siempre captura contexto mínimo y luego inicia llamada IA.

**B4.2 — Formulario del demo (mínimo común):**

- Nombre
- Empresa
- Objetivo (agendar/venta/ticket/cobranza/otro)
- Canal preferido (llamada o mensajería)
- Detalle breve (1–2 frases)
- Consentimiento de contacto (especialmente para callback)

**B4.3 — Cierre obligatorio del demo:**

- Al terminar la interacción:
  - “Agendar preconsultoría” (primario)
  - o “Dejar datos para contacto” (fallback)

**B4.4 — Mensaje de expectativa:**

- “Esto es un ejemplo. En la preconsultoría diseñamos tu flujo real con tus reglas e integraciones.”

---

## B5) Beneficios (bloque obligatorio)

**B5.1 — Formato:** Resultado + por qué

- “Reduce tiempos de resolución porque el agente inicia con contexto del formulario.”
- “Mejora conversiones porque elimina fricción y acelera el cierre.”
- “Escala sin aumentar personal en tareas repetitivas.”

**B5.2 — Datos operativos (permitido):**

- “Interacciones promedio: 3–5 minutos (según caso).”
- “Agendamiento por mensajería: confirmación + recordatorio.”

---

## B6) Confianza y objeciones (obligatorio)

**B6.1 — “Por qué confiar” (mínimo):**

- Experiencia comprobable en soluciones de voz/call centers.
- Integración con infraestructura existente del cliente.
- Implementación acompañada (no DIY).

**B6.2 — FAQ mínimo:**

- ¿Esto reemplaza a mi equipo?
- ¿Se integra con lo que ya tengo?
- ¿Cuánto tarda?
- ¿Qué pasa si el caso es complejo?
- ¿Puedo escalar a humano por llamada o mensajería?

---

## B7) Pricing (carta de precios en landing) — Setup + mensual + consumo

**B7.1 — La landing sí muestra pricing:**

- Debe incluir:
  - Setup obligatorio (desde)
  - mensualidad (desde)
  - consumo (minutos/mensajería) como variable

**B7.2 — Tabla recomendada (editable):**
| Plan | Ideal para | Mensual | Setup |
|------|------------|--------:|------:|
| Starter | 1 vertical / bajo volumen | Desde $299 | Desde $900 |
| Growth | 2–3 verticales | Desde $699 | Desde $1.800 |
| Scale | alto volumen | Desde $1.499 | Desde $3.500 |

**B7.3 — Add-On “Super Plus” (sección destacada):**

- “Super Plus: Click-to-IA-Call avanzado para campañas y embudos complejos”
- Mensual: Desde $199
- Setup adicional: Desde $600

**B7.4 — Nota de consumo (sin detalles técnicos):**

- “El consumo (minutos y mensajería) varía por país y volumen. Se factura según el plan y uso real.”

---

## B8) CTAs (reglas estrictas)

1. CTA primario persistente: “Agendar preconsultoría”
2. CTA secundario persistente: “Probar IA ahora”
3. CTA terciario: “Quiero que me contacten”

**B8.1 — Microcopy obligatorio:**

- “Diagnóstico 15–30 min.”
- “Prueba el embudo: formulario → llamada IA con contexto → cierre.”

---

## B9) Reglas de diseño UX (alto impacto)

- Sticky header con anchors: Casos / Demo / Pricing / Agendar
- Mobile-first: CTA fijo inferior
- Evitar fricción: demo en 30–60 segundos máximo para iniciar llamada

---
