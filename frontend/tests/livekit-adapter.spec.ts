import { expect, test } from '@playwright/test';
import { RoomEvent, type Room } from 'livekit-client';

import { LiveKitVoiceRuntimeAdapter } from '../lib/voice-runtime/livekit-adapter';

class FakeRoom {
  handlers = new Map<string, (...args: never[]) => void>();
  connectCalls: unknown[][] = [];
  disconnectCalls = 0;
  microphoneStates: boolean[] = [];
  mediaStreamTrack = { id: 'published-microphone-track' };
  connectError: Error | null = null;
  localParticipant = {
    identity: 'web-local',
    setMicrophoneEnabled: async (enabled: boolean) => {
      this.microphoneStates.push(enabled);
    },
    getTrackPublication: (source: string) =>
      source === 'microphone' ? { track: { mediaStreamTrack: this.mediaStreamTrack } } : undefined,
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
    if (this.connectError) throw this.connectError;
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

class FakeMediaStream {
  constructor(public readonly tracks: unknown[]) {}
}

test('feeds the level meter from the published microphone track, without a second capture', async () => {
  (globalThis as unknown as { MediaStream: unknown }).MediaStream = FakeMediaStream;
  const room = new FakeRoom();
  const streams: Array<FakeMediaStream | null> = [];
  const adapter = new LiveKitVoiceRuntimeAdapter(
    { onMicrophoneStream: (stream) => streams.push(stream as unknown as FakeMediaStream | null) },
    room as unknown as Room
  );

  await adapter.connect({ serverUrl: 'wss://livekit.example', participantToken: 'token' }, () => {});

  expect(streams).toHaveLength(1);
  expect(streams[0]?.tracks).toEqual([room.mediaStreamTrack]);
  expect(room.microphoneStates).toEqual([true]);

  await adapter.disconnect();

  expect(streams).toHaveLength(2);
  expect(streams[1]).toBeNull();
  expect(room.disconnectCalls).toBe(1);
});

test('a failed connection releases the microphone and reports the error', async () => {
  const room = new FakeRoom();
  room.connectError = new Error('network down');
  const states: string[] = [];
  const streams: unknown[] = [];
  const microphone: boolean[] = [];
  const adapter = new LiveKitVoiceRuntimeAdapter(
    { onMicrophoneStream: (stream) => streams.push(stream), onMicrophoneChange: (active) => microphone.push(active) },
    room as unknown as Room
  );

  await expect(
    adapter.connect({ serverUrl: 'wss://livekit.example', participantToken: 'token' }, (state) => states.push(state))
  ).rejects.toThrow('network down');

  expect(states).toEqual(['connecting', 'error', 'ended']);
  expect(room.disconnectCalls).toBe(1);
  expect(microphone).toEqual([false]);
  expect(streams).toEqual([null]);
  expect(room.handlers.size).toBe(0);
});

test('hangup disconnects the room, removes remote audio and stops listening', async () => {
  const room = new FakeRoom();
  const adapter = new LiveKitVoiceRuntimeAdapter({}, room as unknown as Room);
  await adapter.connect({ serverUrl: 'wss://livekit.example', participantToken: 'token' }, () => {});
  expect(room.handlers.has(RoomEvent.Disconnected)).toBe(true);

  await adapter.disconnect();
  await adapter.disconnect(); // idempotent: a second hangup/unmount never disconnects twice

  expect(room.disconnectCalls).toBe(1);
  expect(room.handlers.size).toBe(0);
});
