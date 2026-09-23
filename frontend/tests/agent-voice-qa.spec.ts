import { expect, test } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import path from 'node:path';

const root = path.resolve(__dirname, '..');

test('QA action sends tenant-safe context and distinct WebRTC/SIP contracts', async () => {
  const source = await readFile(
    path.join(root, 'app/[locale]/(tenant)/voice-ai/agents/actions.ts'),
    'utf8'
  );
  expect(source).toContain("purpose: 'qa'");
  expect(source).toContain('qa_context_mode: input.context_mode');
  expect(source).toContain("channel: input.transport");
  expect(source).toContain("input.transport === 'sip' ? 'outbound' : 'internal'");
  expect(source).toContain("const hasPreloadedContext = input.context_mode === 'preloaded'");
  expect(source).toContain('caller_phone: hasPreloadedContext ? input.caller_phone');
  expect(source).toContain('contact_id: hasPreloadedContext ? input.contact_id');
  expect(source).toContain('lead_id: hasPreloadedContext ? input.lead_id');
  expect(source).toContain('variables: hasPreloadedContext ? input.variables ?? {} : undefined');
  expect(source).toContain("to_phone: input.transport === 'sip' ? input.to_phone : undefined");
  expect(source).not.toContain('tenant_id:');
});

test('QA dialog keeps transport and context mode as independent choices', async () => {
  const source = await readFile(
    path.join(root, 'components/crm/agents/AgentVoiceTest.tsx'),
    'utf8'
  );
  expect(source).toContain("useState<QaContextMode>('preloaded')");
  expect(source).toContain('aria-label="Modo de contexto QA"');
  expect(source).toContain('Con contexto precargado');
  expect(source).toContain('Sin contexto precargado');
  expect(source).toContain("contextMode === 'conversation'");
  expect(source).toContain("transport === 'sip' ? <label");
  expect(source).toContain('Teléfono del caller (contexto)');
  expect(source).toContain('Contact ID manual');
  expect(source).toContain('Variables JSON controladas');
});

test('conversation mode omits CRM context, skips lead lookup and explains WebRTC limits', async () => {
  const source = await readFile(
    path.join(root, 'components/crm/agents/AgentVoiceTest.tsx'),
    'utf8'
  );
  expect(source).toContain("contextMode === 'conversation') return");
  expect(source).toContain('caller_phone: hasPreloadedContext ? callerPhone.trim()');
  expect(source).toContain('contact_id: hasPreloadedContext ? contactId.trim()');
  expect(source).toContain('lead_id: hasPreloadedContext ? leadId');
  expect(source).toContain('variables: hasPreloadedContext ? variables : {}');
  expect(source).toContain('El agente iniciará sin contexto de negocio precargado.');
  expect(source).toContain('Esta prueba no modifica el prompt ni agrega instrucciones ocultas');
  expect(source).toContain('En WebRTC no existe una identidad telefónica confiable de transporte.');
  expect(source).toContain('Para probar el flujo completo de creación de lead desde una llamada sin contexto, utiliza SIP.');
});

test('QA console renders transcripts, tool outcomes and lead errors', async () => {
  const source = await readFile(
    path.join(root, 'components/crm/agents/AgentVoiceTest.tsx'),
    'utf8'
  );
  expect(source).toContain("event.event_type === 'voice.transcript.final'");
  expect(source).toContain("event.event_type === 'session.context.tool_used'");
  expect(source).toContain('event.payload.error_code ?? event.payload.summary');
  expect(source).toContain('lead_context_required');
  expect(source).toContain('Context mode');
  expect(source).toContain("contextMode === 'conversation' ? 'Conversacional' : 'Precargado'");
});

test('QA polling deduplicates by event_id and stops on terminal sessions', async () => {
  const source = await readFile(
    path.join(root, 'components/crm/agents/AgentVoiceTest.tsx'),
    'utf8'
  );
  expect(source).toContain('new Map(current.map((event) => [event.event_id, event]))');
  expect(source).toContain('byId.set(event.event_id, event)');
  expect(source).toContain('window.setTimeout(poll, 1000)');
  expect(source).toContain('TERMINAL.has(result.data.session.status)');
});
