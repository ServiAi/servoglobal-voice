import Link from 'next/link';
import { ArrowLeft } from 'lucide-react';

export default function PrivacyPolicyPage() {
  return (
    <main className="min-h-screen bg-white dark:bg-zinc-950 transition-colors duration-300">
      <div className="container mx-auto px-4 md:px-6 py-20 max-w-4xl">
        
        <Link 
          href="/" 
          className="inline-flex items-center gap-2 text-sm text-zinc-500 hover:text-violet-600 dark:hover:text-violet-400 mb-12 transition-colors"
        >
          <ArrowLeft className="size-4" />
          Volver al Inicio
        </Link>

        <div className="space-y-8 text-zinc-600 dark:text-zinc-400">
          <div>
            <h1 className="text-4xl font-bold text-zinc-900 dark:text-white mb-4 tracking-tight">Política de Privacidad</h1>
            <p className="text-lg">Última actualización: {new Date().toLocaleDateString('es-ES')}</p>
          </div>

          <section className="space-y-4">
            <h2 className="text-2xl font-semibold text-zinc-900 dark:text-white mt-12 mb-4">1. Introducción</h2>
            <p>
              En <strong>ServiGlobal IA</strong>, valoramos su privacidad y estamos comprometidos con la protección de sus datos personales. 
              Esta política explica cómo recopilamos, usamos, compartimos y protegemos la información cuando interactúa con nuestra 
              plataforma web y solicita nuestros servicios de <strong>Preconsultoría e Implementación de Agentes de Voz y Omnicanales</strong>.
            </p>
            <p>
              ServiGlobal IA no opera como una plataforma de autoservicio (SaaS DIY), sino como una firma consultora y desarrolladora. 
              Por lo tanto, la información recopilada está orientada exclusivamente a diagnosticar, cotizar e implementar soluciones a medida.
            </p>
          </section>

          <section className="space-y-4">
            <h2 className="text-2xl font-semibold text-zinc-900 dark:text-white mt-8 mb-4">2. ¿Qué información recogemos?</h2>
            <p>A través de nuestros formularios (como Cal.com o demos interactivos) y procesos de contacto, recopilamos los siguientes datos:</p>
            <ul className="list-disc pl-6 space-y-2">
              <li><strong>Datos de Contacto Profesional:</strong> Nombre del representante, empresa, cargo y país/ciudad.</li>
              <li><strong>Información Operativa del Negocio:</strong> Modelo de negocio (ventas, soporte, cobranzas, etc.), volumen de interacciones mensuales y canales principales (Voz, WhatsApp, etc.).</li>
              <li><strong>Infraestructura Tecnológica:</strong> Sistemas actuales con los que requiere integración (CRMs, Google Calendar, PBX/Asterisk, sistemas VoIP).</li>
              <li><strong>Datos de Interacción en Demos:</strong> Todo audio o texto introducido al probar nuestro Simulador/Demo en tiempo real es procesado momentáneamente para exhibir la capacidad tecnológica de los agentes con Inteligencia Artificial.</li>
              <li><strong>Datos de Navegación:</strong> Direcciones IP, análisis de interacción mediante herramientas estándar de analítica web y medidas de seguridad (ej. Cloudflare Turnstile).</li>
            </ul>
          </section>

          <section className="space-y-4">
            <h2 className="text-2xl font-semibold text-zinc-900 dark:text-white mt-8 mb-4">3. ¿Por qué lo hacemos? (Uso de la Información)</h2>
            <p>Utilizamos la información recopilada para fines operacionales y comerciales estrictamente ligados a la provisión de nuestras soluciones:</p>
            <ul className="list-disc pl-6 space-y-2">
              <li><strong>Diagnóstico de Preconsultoría:</strong> Para diseñar el mapa de flujos y la propuesta técnica (Fase 1 de nuestro modelo) basado en su volumen y modelo de negocio.</li>
              <li><strong>Agendamiento:</strong> Para coordinar reuniones de diagnóstico a través de integraciones.</li>
              <li><strong>Personalización de Implementación:</strong> Adaptar herramientas (backend en Python, LangGraph, etc.) a su infraestructura existente (PBX, CRM).</li>
              <li><strong>Demostraciones en vivo:</strong> Operar el agente interactivo de voz o texto mostrado en la página de inicio.</li>
              <li><strong>Mejora del Servicio:</strong> Analizar la efectividad de nuestra página web y prevenir abusos usando tecnologías de verificación anti-bots.</li>
            </ul>
          </section>

          <section className="space-y-4">
            <h2 className="text-2xl font-semibold text-zinc-900 dark:text-white mt-8 mb-4">4. ¿Con quién se comparte?</h2>
            <p>ServiGlobal IA <strong>nunca vende, alquila ni comercializa</strong> su información a terceros para fines publicitarios. La información solo se comparte con proveedores de infraestructura tecnológica (Subprocesadores) estrictamente necesarios para brindar el servicio:</p>
            <ul className="list-disc pl-6 space-y-2">
              <li><strong>Proveedores de Agendamiento e Infraestructura:</strong> Herramientas como Cal.com, Google Workspace, y plataformas cloud para gestionar las consultorías.</li>
              <li><strong>Proveedores de Modelos de Inteligencia Artificial:</strong> Para los demos en vivo o la posterior implementación, utilizamos APIs (ej. OpenAI, Anthropic, Ultravox, Retell AI, Vapi, LiveKit). Los audios de los demos locales no se utilizan para reentrenar modelos fundamentales según los acuerdos enterprise de estos proveedores.</li>
              <li><strong>Seguridad y Rendimiento:</strong> Usamos herramientas como Cloudflare Turnstile para verificar que el tráfico es humano y proteger el acceso.</li>
              <li><strong>Requisitos Legales:</strong> Únicamente revelaremos información si es requerido por ley o procesos legales vigentes.</li>
            </ul>
          </section>

          <section className="space-y-4">
            <h2 className="text-2xl font-semibold text-zinc-900 dark:text-white mt-8 mb-4">5. ¿Cómo se protege su información?</h2>
            <p>La seguridad de sus datos es primordial. Implementamos múltiples niveles de protección:</p>
            <ul className="list-disc pl-6 space-y-2">
              <li><strong>Cifrado en tránsito y en reposo:</strong> Toda interacción en el sitio web está protegida mediante encriptación SSL/TLS de extremo a extremo.</li>
              <li><strong>Control de Acceso:</strong> Sólo el personal autorizado (consultores e ingenieros de ServiGlobal IA) tiene acceso a los datos del prospecto para elaborar la propuesta técnica.</li>
              <li><strong>Seguridad de la Infraestructura:</strong> Los servicios de demostración y backend están enrutados a través de proveedores seguros con certificaciones de cumplimiento internacional.</li>
            </ul>
          </section>

          <section className="space-y-4">
            <h2 className="text-2xl font-semibold text-zinc-900 dark:text-white mt-8 mb-4">6. Derechos del Usuario</h2>
            <p>
              Usted tiene derecho a solicitar el acceso, corrección o eliminación de toda información compartida durante el contacto inicial o la demo interactiva. 
              Para ejercer estos derechos, o si tiene dudas sobre cómo manejamos la protección de datos e integraciones con su ecosistema telefónico, 
              puede enviarnos un correo electrónico a nuestro departamento legal o mencionarlo a su consultor asignado.
            </p>
          </section>

          <div className="mt-16 pt-8 border-t border-zinc-200 dark:border-white/10 text-sm">
            <p>
              Al utilizar esta plataforma web y agendar una preconsultoría, usted acepta las prácticas descritas en esta política.  
              <br/>
              <strong>ServiGlobal IA — Agentes de Voz a Medida</strong>
            </p>
          </div>
        </div>
      </div>
    </main>
  );
}
