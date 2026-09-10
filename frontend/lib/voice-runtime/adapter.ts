export type VoiceRuntimeConnectionState = 'connecting' | 'connected' | 'ended' | 'error';

export type VoiceRuntimeJoin =
  | string
  | { serverUrl: string; participantToken: string };

export interface VoiceRuntimeAdapter {
  connect(join: VoiceRuntimeJoin, onState: (state: VoiceRuntimeConnectionState) => void): Promise<void>;
  disconnect(): void | Promise<void>;
}
