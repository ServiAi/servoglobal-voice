import type { VoiceRuntimeAdapter, VoiceRuntimeConnectionState } from './adapter';

export class FakeVoiceRuntimeAdapter implements VoiceRuntimeAdapter {
  async connect(_joinUrl: string, onState: (state: VoiceRuntimeConnectionState) => void) {
    onState('connecting');
    await Promise.resolve();
    onState('connected');
  }

  disconnect() {}
}
