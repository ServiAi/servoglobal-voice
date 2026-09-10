import { expect, test } from '@playwright/test';
import { RoomEvent, type Room } from 'livekit-client';

import { LiveKitVoiceRuntimeAdapter } from '../lib/voice-runtime/livekit-adapter';

class FakeRoom {
  handlers = new Map<string, (...args: never[]) => void>();
  connectCalls: unknown[][] = [];
  disconnectCalls = 0;
  microphoneStates: boolean[] = [];
  localParticipant = {
    identity: 'web-local',
    setMicrophoneEnabled: async (enabled: boolean) => {
      this.microphoneStates.push(enabled);
    },
  };

  on(event: string, callback: (...args: never[]) => void) {
    this.handlers.set(event, callback);
    return this;
  }

  off(event: string, callback: (...args: never[]) => void) {
    if (this.handlers.get(event) === callback) this.handlers.delete(event);
    return this;
  }

  async connect(...args: unknown[]) {
    this.connectCalls.push(args);
  }

  async startAudio() {}

  async disconnect() {
    this.disconnectCalls += 1;
  }
}

test('connects with the participant token, publishes one microphone, and cleans up', async () => {
  const room = new FakeRoom();
  const states: string[] = [];
  const microphone: boolean[] = [];
  const adapter = new LiveKitVoiceRuntimeAdapter(
    { onMicrophoneChange: (active) => microphone.push(active) },
    room as unknown as Room
  );

  await adapter.connect(
    { serverUrl: 'wss://livekit.example', participantToken: 'participant-token' },
    (state) => states.push(state)
  );

  expect(room.connectCalls).toEqual([['wss://livekit.example', 'participant-token']]);
  expect(room.microphoneStates).toEqual([true]);
  expect(states).toEqual(['connecting', 'connected']);
  expect(microphone).toEqual([true]);

  await adapter.disconnect();

  expect(room.microphoneStates).toEqual([true, false]);
  expect(room.disconnectCalls).toBe(1);
  expect(states).toEqual(['connecting', 'connected', 'ended']);
  expect(microphone).toEqual([true, false]);
  expect(room.handlers.has(RoomEvent.Disconnected)).toBe(false);
});

test('rejects legacy Ultravox join URLs without acquiring a microphone', async () => {
  const room = new FakeRoom();
  const adapter = new LiveKitVoiceRuntimeAdapter({}, room as unknown as Room);

  await expect(adapter.connect('https://ultravox.example', () => {})).rejects.toThrow(
    'LiveKit requires server URL and participant token'
  );
  expect(room.microphoneStates).toEqual([]);
});
