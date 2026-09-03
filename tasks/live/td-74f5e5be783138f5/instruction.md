# WebSocket audio backend via AudioIO ABC (updated [redacted-ref])

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Implementation of a WebSocket audio backend, based on [redacted-ref] by @reisbauer03 but
reframed onto the project's audio `AudioIO` ABC so the engine runs identically on
local hardware (sounddevice) or over the network.

## What's included
- **`AudioIO` ABC** (`src/[redacted-repo]/audio_io/base.py`): single contract; `SoundDeviceAudioIO`
  and `WebsocketAudioIO` both subclass it. `AudioProtocol` kept as a back-compat alias.
- **`WebsocketAudioIO`**: `/microphone` (16 kHz float32 → VAD → sample queue) and
  `/speaker` (TTS playback with `time`/`sampleRate`/`played`/`reset` ack flow).
- **Rooms opt-in** (`audio_io_options: rooms: true`, default **false**): multi-mic
  ownership arbitration + `segregate_speakers` routing. Default = single-client,
  broadcast to all speakers.
- Config wiring (`config.audio_io_options`), `configs/[redacted-repo]_websocket_config.yaml`,
  protocol docs, and browser (`tests/audio-websocket-*.html`) + Python
  (`examples/audio_websocket_client.py`) reference clients.

## Notes
Closes/supersedes [redacted-ref] (superseded implementation). Author's unrelated older-fork
changes were intentionally not carried over.

<!-- This is an auto-generated comment: release notes by coderabbit.ai -->
## Summary by CodeRabbit

* **New Features**
  * Added WebSocket-based microphone capture and speaker playback.
  * Added room selection, audio synchronization, interruption handling, playback progress, and voice-activity detection.
  * Added a complete local [redacted-repo] configuration with chat, speech, autonomy, and optional integrations.
  * Added browser and Python audio client examples.
  * Improved audio backend configuration and resource cleanup.

* **Documentation**
  * Added WebSocket audio setup, protocol, and client usage documentation.

* **Tests**
  * Added coverage for playback, connection handling, shutdown, and malformed audio input.
<!-- end of auto-generated comment: release notes by coderabbit.ai -->

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
