import { UltravoxSession, UltravoxSessionStatus } from 'ultravox-client';

import type { VoiceRuntimeAdapter, VoiceRuntimeConnectionState } from './adapter';

export class UltravoxVoiceRuntimeAdapter implements VoiceRuntimeAdapter {
  private readonly session = new UltravoxSession();

  async connect(joinUrl: string, onState: (state: VoiceRuntimeConnectionState) => void) {
    this.session.addEventListener('status', () => {
      const status = this.session.status;
      if (status === UltravoxSessionStatus.CONNECTING) onState('connecting');
      else if (status === UltravoxSessionStatus.DISCONNECTED) onState('ended');
      else onState('connected');
    });
    onState('connecting');
    await this.session.joinCall(joinUrl);
  }

  disconnect() {
    this.session.leaveCall();
  }
}
