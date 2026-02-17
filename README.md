# ServiGlobal · IA - Agentes de Voz e IA Omnicanal

Esta landing page está diseñada para ofrecer servicios de consultoría e implementación de agentes de voz IA y soluciones omnicanal. Enfocada en la conversión a través de demos interactivas y agendamiento de pre-consultorías.

## Funcionalidades Implementadas

### 1. Hero Section

- Mensaje de valor claro: **"Atiende el 100% de tus llamadas, 24/7"**.
- Branding actualizado a **Servi-IA**.
- Llamadas a la acción (CTAs) principales: Agendar Preconsultoría y Probar Servi-IA Ahora.
- Animación autónoma y reactiva (ondas sinusoidales) para mayor dinamismo.

### 2. Soluciones por Industria (Antes Casos de Uso)

- Visualización de 7 verticales de negocio:
  - Atención al Cliente
  - Soporte Técnico
  - Cobranza
  - Ventas
  - Reclutamiento
  - Reservas
  - E-commerce
- Contenido dinámico y específico para cada vertical.

### 3. Demos de Agentes de Voz (Simulación UI)

- **Clic para Llamar (Inbound):** Simulación de llamada desde el navegador con visualización de ondas de audio y estados de llamada.
- **Servi-IA te llama (Outbound):** Formulario para solicitar una llamada (“Callback”), simulando el flujo de contacto de un agente con contexto previo.
- Integración real con **Ultravox** (experimental/demo).

### 4. Beneficios y Seguridad

- **8 Beneficios Clave:** Incluyendo "Seguridad Empresarial" para sectores regulados (Banca, Salud).
- Enfoque en reducción de costos, omnicanalidad y cierre de ventas.

### 5. Integraciones

- Showcase de compatibilidad con herramientas populares (CRM, Calendarios, VoIP, WhatsApp).

### 6. Agendamiento y Contacto

- **Modal de Contacto:** Acceso rápido a información de contacto (WhatsApp, Teléfono, Email, Ubicación) desde el Header y Footer.
- Integración para agendar citas directamente.

### 7. Precios v2.0

- Estrategia de **Bolsas de Minutos** (Llamadas Web + Número Virtual).
- Planes: Starter, Growth, Enterprise.
- Add-ons: **Clic para Llamar con Servi-IA** y Servicios Profesionales (BYO PBX).

### 8. Internacionalización (i18n)

- Soporte multi-idioma (Español/Inglés) con `next-intl`.
- **Localización completa en Español:** Se han eliminado términos en inglés (Setup -> Configuración, DID -> Número Virtual, etc.) para una experiencia nativa.

## Infraestructura y Despliegue

### Stack Tecnológico

- **Frontend:** Next.js 14, Tailwind CSS, Framer Motion, Lucide React.
- **Backend:** FastAPI (Python), Docker.
- **IA/Voz:** Ultravox (Integración de agentes de voz).

### CI/CD y Hosting

- **Hosting:** VPS en Hostinger.
- **Orquestación:** Dokploy (Alternativa a Vercel/Heroku self-hosted).
- **CI/CD:** GitHub Actions (`dokploy_deploy.yml`).
  - Despliegue automático a producción (rama `main` o `develop`) mediante Webhooks de Dokploy.

## Estructura del Proyecto

- `/frontend`: Aplicación Next.js.
  - `/components`: Componentes de UI (`Hero`, `UseCases`, `VoiceDemo`, `ContactModal`, etc.).
  - `/messages`: Archivos de traducción (`es.json`, `en.json`).
- `/backend`: API FastAPI.
- `.github/workflows`: Flujos de trabajo de CI/CD.

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
# Crear entorno virtual y activar
pip install -r requirements.txt
uvicorn app.main:app --reload
```
