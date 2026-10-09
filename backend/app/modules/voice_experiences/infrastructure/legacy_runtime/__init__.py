"""Temporary compatibility adapters for the pre-modular public runtime.

WebRTC launch stays on the direct-provider path until PR #135 replaces it
with VoiceSession + LiveKit. Callback stays on provider/SIP until PR #136.
These adapters do not define Voice Experiences policy or own its entities.
"""
