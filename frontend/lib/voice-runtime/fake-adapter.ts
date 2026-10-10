import type { VoiceRuntimeAdapter, VoiceRuntimeConnectionState, VoiceRuntimeJoin } from './adapter';

export class FakeVoiceRuntimeAdapter implements VoiceRuntimeAdapter {
  async connect(join: VoiceRuntimeJoin, onState: (state: VoiceRuntimeConnectionState) => void) {
    // Same contract as the real adapter: a LiveKit join, never a provider URL.
    if (typeof join === 'string') throw new Error('LiveKit requires server URL and participant token');
    onState('connecting');
    await Promise.resolve();
    onState('connected');
  }

  disconnect() {}
}
