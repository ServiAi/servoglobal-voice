export type VoiceRuntimeConnectionState = 'connecting' | 'connected' | 'ended' | 'error';

export interface VoiceRuntimeAdapter {
  connect(joinUrl: string, onState: (state: VoiceRuntimeConnectionState) => void): Promise<void>;
  disconnect(): void;
}
