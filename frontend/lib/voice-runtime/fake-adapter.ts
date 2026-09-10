import type { VoiceRuntimeAdapter, VoiceRuntimeConnectionState, VoiceRuntimeJoin } from './adapter';

export class FakeVoiceRuntimeAdapter implements VoiceRuntimeAdapter {
  async connect(_join: VoiceRuntimeJoin, onState: (state: VoiceRuntimeConnectionState) => void) {
    onState('connecting');
    await Promise.resolve();
    onState('connected');
  }

  disconnect() {}
}
