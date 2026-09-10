import { UltravoxSession, UltravoxSessionStatus } from 'ultravox-client';

import type { VoiceRuntimeAdapter, VoiceRuntimeConnectionState, VoiceRuntimeJoin } from './adapter';

export class UltravoxVoiceRuntimeAdapter implements VoiceRuntimeAdapter {
  private readonly session = new UltravoxSession();

  async connect(join: VoiceRuntimeJoin, onState: (state: VoiceRuntimeConnectionState) => void) {
    if (typeof join !== 'string') throw new Error('Ultravox requires a join URL');
    this.session.addEventListener('status', () => {
      const status = this.session.status;
      if (status === UltravoxSessionStatus.CONNECTING) onState('connecting');
      else if (status === UltravoxSessionStatus.DISCONNECTED) onState('ended');
      else onState('connected');
    });
    onState('connecting');
    await this.session.joinCall(join);
  }

  disconnect() {
    this.session.leaveCall();
  }
}
