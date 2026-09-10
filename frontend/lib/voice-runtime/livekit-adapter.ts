import {
  Room,
  RoomEvent,
  Track,
  type Participant,
  type RemoteTrack,
} from 'livekit-client';

import type {
  VoiceRuntimeAdapter,
  VoiceRuntimeConnectionState,
  VoiceRuntimeJoin,
} from './adapter';

type LiveKitAdapterCallbacks = {
  onMicrophoneChange?: (active: boolean) => void;
  onAgentSpeakingChange?: (speaking: boolean) => void;
  onAudioPlaybackBlocked?: () => void;
};

export class LiveKitVoiceRuntimeAdapter implements VoiceRuntimeAdapter {
  private readonly audioElements = new Set<HTMLMediaElement>();
  private readonly remoteAudioTracks = new Set<RemoteTrack>();
  private onState: ((state: VoiceRuntimeConnectionState) => void) | null = null;
  private disconnecting = false;

  constructor(
    private readonly callbacks: LiveKitAdapterCallbacks = {},
    private readonly room = new Room()
  ) {}

  private readonly handleDisconnected = () => {
    this.disconnecting = true;
    this.unbindListeners();
    this.releaseRemoteAudio();
    this.callbacks.onMicrophoneChange?.(false);
    this.callbacks.onAgentSpeakingChange?.(false);
    this.onState?.('ended');
    this.onState = null;
  };

  private readonly handleTrackSubscribed = (track: RemoteTrack) => {
    if (track.kind !== Track.Kind.Audio) return;
    const element = track.attach();
    element.autoplay = true;
    element.setAttribute('aria-hidden', 'true');
    element.style.display = 'none';
    document.body.appendChild(element);
    this.audioElements.add(element);
    this.remoteAudioTracks.add(track);
    void element.play().catch(() => this.callbacks.onAudioPlaybackBlocked?.());
  };

  private readonly handleTrackUnsubscribed = (track: RemoteTrack) => {
    for (const element of track.detach()) {
      this.audioElements.delete(element);
      element.remove();
    }
    this.remoteAudioTracks.delete(track);
  };

  private readonly handleActiveSpeakersChanged = (participants: Participant[]) => {
    this.callbacks.onAgentSpeakingChange?.(
      participants.some((participant) => participant.identity !== this.room.localParticipant.identity)
    );
  };

  async connect(join: VoiceRuntimeJoin, onState: (state: VoiceRuntimeConnectionState) => void) {
    if (typeof join === 'string') throw new Error('LiveKit requires server URL and participant token');
    this.onState = onState;
    this.disconnecting = false;
    this.bindListeners();
    onState('connecting');
    try {
      await this.room.connect(join.serverUrl, join.participantToken);
      await this.room.startAudio().catch(() => this.callbacks.onAudioPlaybackBlocked?.());
      await this.room.localParticipant.setMicrophoneEnabled(true, {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      });
      this.callbacks.onMicrophoneChange?.(true);
      onState('connected');
    } catch (error) {
      onState('error');
      await this.cleanup();
      throw error;
    }
  }

  async enableAudio() {
    await this.room.startAudio();
  }

  disconnect() {
    return this.cleanup();
  }

  private bindListeners() {
    this.room.on(RoomEvent.Disconnected, this.handleDisconnected);
    this.room.on(RoomEvent.TrackSubscribed, this.handleTrackSubscribed);
    this.room.on(RoomEvent.TrackUnsubscribed, this.handleTrackUnsubscribed);
    this.room.on(RoomEvent.ActiveSpeakersChanged, this.handleActiveSpeakersChanged);
  }

  private unbindListeners() {
    this.room.off(RoomEvent.Disconnected, this.handleDisconnected);
    this.room.off(RoomEvent.TrackSubscribed, this.handleTrackSubscribed);
    this.room.off(RoomEvent.TrackUnsubscribed, this.handleTrackUnsubscribed);
    this.room.off(RoomEvent.ActiveSpeakersChanged, this.handleActiveSpeakersChanged);
  }

  private releaseRemoteAudio() {
    for (const track of this.remoteAudioTracks) track.detach();
    this.remoteAudioTracks.clear();
    for (const element of this.audioElements) element.remove();
    this.audioElements.clear();
  }

  private async cleanup() {
    if (this.disconnecting) return;
    this.disconnecting = true;
    this.unbindListeners();
    try {
      await this.room.localParticipant.setMicrophoneEnabled(false);
    } catch {
      // The room may already be disconnected; disconnect(true) still stops local tracks.
    }
    await this.room.disconnect(true);
    this.releaseRemoteAudio();
    this.callbacks.onMicrophoneChange?.(false);
    this.callbacks.onAgentSpeakingChange?.(false);
    this.onState?.('ended');
    this.onState = null;
  }
}
