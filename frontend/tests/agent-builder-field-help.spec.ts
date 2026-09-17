import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import es from '@/messages/es.json';
import en from '@/messages/en.json';

const source = (name: string) => readFileSync(resolve(process.cwd(), `components/crm/agents/${name}.tsx`), 'utf8');

test('all Agent Builder fields and voice controls have localized help', () => {
  const builder = source('AgentBuilder');
  for (const key of Object.keys(es.crm.agentBuilder.fields)) {
    expect(builder, `General/Behavior: ${key}`).toContain(`help.fields.${key}`);
  }
  for (const key of Object.keys(es.crm.agentBuilder.help.voice)) {
    expect(builder, `Voice: ${key}`).toContain(`help.voice.${key}`);
  }
  expect(Object.keys(en.crm.agentBuilder.help.fields)).toEqual(Object.keys(es.crm.agentBuilder.help.fields));
  expect(Object.keys(en.crm.agentBuilder.help.voice)).toEqual(Object.keys(es.crm.agentBuilder.help.voice));
});

test('model parameters and selectable tools use help labels', () => {
  const model = source('AgentModelSection');
  for (const key of ['pipeline', 'managementMode', 'provider', 'model', 'parameterFallback']) {
    expect(model, key).toContain(`help.model.${key}`);
  }
  expect(model).toContain('help.model.parameterHelp.${paramKey}');
  expect(source('AgentToolsSection')).toContain('help={tool.description}');
});
