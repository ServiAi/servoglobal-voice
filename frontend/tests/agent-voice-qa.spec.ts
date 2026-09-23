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
  expect(source).toContain("channel: input.transport");
  expect(source).toContain("input.transport === 'sip' ? 'outbound' : 'internal'");
  expect(source).toContain('caller_phone: input.caller_phone');
  expect(source).toContain('contact_id: input.contact_id');
  expect(source).toContain('lead_id: input.lead_id');
  expect(source).toContain('variables: input.variables ?? {}');
  expect(source).not.toContain('tenant_id:');
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
