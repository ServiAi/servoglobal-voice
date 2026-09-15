import { expect, test } from '@playwright/test';
import { fetchCrmVoiceCallAgents, startCrmLeadVoiceCall } from '@/lib/api/crm';

test('CRM lista agentes canónicos y envía el contrato outbound V2', async () => {
  const previousApiUrl = process.env.NEXT_PUBLIC_API_URL;
  const previousFetch = globalThis.fetch;
  const requests: Array<{ url: string; init: RequestInit }> = [];
  process.env.NEXT_PUBLIC_API_URL = 'https://api.example.test';
  globalThis.fetch = async (input, init) => {
    requests.push({ url: String(input), init: init ?? {} });
    return new Response(JSON.stringify(requests.length === 1 ? [
      { id: 'draft', name: 'Draft', status: 'draft', published_version_id: null },
      { id: 'unpublished', name: 'Unpublished', status: 'active', published_version_id: null },
      { id: 'published', name: 'Published', status: 'active', published_version_id: 'version-1' },
    ] : { status: 'answered', voice_call_id: 'call-1', voice_session_id: 'session-1' }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  };

  try {
    const agents = await fetchCrmVoiceCallAgents('test-access-token');
    expect(agents.ok).toBe(true);
    if (agents.ok) expect(agents.data.map((agent) => agent.id)).toEqual(['published']);
    const idempotencyKey = crypto.randomUUID();
    await startCrmLeadVoiceCall('test-access-token', 'lead-1', {
      agent_id: 'agent-1',
      idempotency_key: idempotencyKey,
      to_phone: '+573000000000',
    });

    expect(requests[0].url).toBe('https://api.example.test/api/v1/agents');
    expect(requests[1].url).toBe('https://api.example.test/api/v1/crm/leads/lead-1/actions/call');
    expect(requests[1].init.method).toBe('POST');
    expect(JSON.parse(String(requests[1].init.body))).toEqual({
      agent_id: 'agent-1',
      idempotency_key: idempotencyKey,
      to_phone: '+573000000000',
    });
  } finally {
    globalThis.fetch = previousFetch;
    if (previousApiUrl === undefined) delete process.env.NEXT_PUBLIC_API_URL;
    else process.env.NEXT_PUBLIC_API_URL = previousApiUrl;
  }
});
