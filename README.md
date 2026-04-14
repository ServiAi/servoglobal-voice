# ServiGlobal · IA - Landing de Servi-IA

Landing page comercial para presentar **Servi-IA**, la solución de agentes de voz e IA de **ServiGlobal · IA**. La página está enfocada en convertir visitantes mediante demos, explicación de implementación guiada, preconsultoría y rutas comerciales claras según el tipo de operación.

## Enfoque Comercial Actual

- **ServiGlobal · IA** funciona como marca paraguas.
- **Servi-IA** es la solución implementada para cada cliente.
- El primer paso comercial es una **preconsultoría gratuita de 20-30 minutos**.
- La oferta se comunica como implementación guiada, operación mensual y consumo adicional según uso.
- La landing prioriza tres resultados:
  - agendamiento inteligente;
  - captación y calificación de leads;
  - atención automatizada y triage.

## Funcionalidades Implementadas

### 1. Hero Section

- Mensaje de valor para agentes de voz con IA integrados a la operación del cliente.
- CTAs principales hacia preconsultoría y demo.
- Animación visual para reforzar la experiencia de agente de voz.

### 2. Resultados y Casos de Uso

- La sección de soluciones prioriza resultados de negocio antes que industrias.
- Resultados principales:
  - **Agendamiento inteligente:** disponibilidad, confirmaciones, reprogramaciones y contexto para citas.
  - **Captación y calificación de leads:** formularios inteligentes, llamadas con contexto y priorización comercial.
  - **Atención automatizada / triage:** clasificación de solicitudes, respuestas repetitivas y escalamiento cuando corresponde.
- Las industrias quedan como ejemplos de aplicación: atención, soporte, cobranza, ventas, reclutamiento, reservas y e-commerce.

### 3. Demos de Agentes de Voz

- **Clic para llamar (Inbound/Web):** formulario y conexión desde navegador con Servi-IA.
- **Servi-IA te llama (Outbound/Callback):** formulario para solicitar llamada inmediata o programada con contexto previo.
- Ambos formularios incluyen consentimiento visible para tratamiento de datos antes de iniciar la interacción.
- La demo inbound usa la integración existente con Ultravox y la outbound conserva el flujo actual hacia el backend.

### 4. Implementación Guiada

- La página comunica un proceso de acompañamiento:
  - preconsultoría y diagnóstico;
  - implementación / piloto;
  - producción, soporte y optimización.
- El posicionamiento evita vender una plataforma autoservicio y enfatiza diseño, integración y operación acompañada.

### 5. Integraciones

La landing presenta compatibilidad con canales y sistemas existentes, sin exigir reemplazar la operación actual:

- telefonía / PBX / VoIP;
- CRM y herramientas de operación;
- calendarios;
- mensajería y WhatsApp;
- formularios web y canales digitales.

### 6. Pricing

El pricing está alineado con tres rutas comerciales:

- **Web Conversion:** para captación y conversión digital inteligente. Incluye formulario inteligente WebRTC, clic para llamar, leads web/campañas/redes y callback con contexto.
- **Voice Cloud / PBX:** para operación de voz real, PSTN, PBX e integración telefónica.
- **Enterprise:** ruta a medida para alto volumen, múltiples agentes o integraciones críticas.

Condiciones visibles en landing:

- setup visible por plan;
- fee mensual como operación del servicio;
- bolsa inicial de 2,000 minutos IA en planes base;
- minuto IA adicional de USD 0.20;
- consultoría o cambio adicional de USD 60;
- segundo agente sin setup sujeto a complejidad, con descuento mensual;
- costos de Meta / WhatsApp a cargo del cliente;
- valores en USD con TRM vigente al día y exentos de IVA.

### 7. Internacionalización

- Soporte multi-idioma con `next-intl`.
- Traducciones en `frontend/messages/es.json` y `frontend/messages/en.json`.
- Los textos visibles de pricing, casos de uso, demos y consentimiento se manejan desde archivos de traducción.

## Infraestructura y Despliegue

### Stack Tecnológico

- **Frontend:** Next.js 15, React, Tailwind CSS, Framer Motion, Lucide React, next-intl.
- **Backend:** FastAPI (Python), Docker.
- **IA/Voz:** Ultravox en la demo inbound existente.

### CI/CD y Hosting

- **Hosting:** VPS en Hostinger.
- **Orquestación:** Dokploy.
- **CI/CD:** GitHub Actions (`dokploy_deploy.yml`) para despliegue mediante webhooks de Dokploy.

## Estructura del Proyecto

- `/frontend`: aplicación Next.js.
  - `/components/landing`: secciones de la landing (`Hero`, `UseCases`, `Pricing`, `VoiceDemo`, `Booking`, etc.).
  - `/messages`: archivos de traducción (`es.json`, `en.json`).
- `/backend`: API FastAPI existente.
- `.github/workflows`: flujos de CI/CD.

## Cómo Ejecutar Localmente

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```
