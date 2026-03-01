# Debug Log: Greeting Audio Feature

## Feature Goal
When user clicks "Activate Assistant", play a greeting audio message ("Hey Pierre, how can I help you today?") streamed from ElevenLabs TTS to the glasses speakers.

## Implementation Summary

### Backend Changes (tools/mock_backend/server.py)
1. Added `elevenlabs` SDK dependency
2. Added `python-dotenv` for loading `.env` file with API key
3. Created `stream_greeting_audio()` function that:
   - Waits 10 seconds for "Experience started" system announcement to finish
   - Calls ElevenLabs TTS with `ulaw_8000` format (8kHz for HFP compatibility)
   - Converts μ-law to PCM s16le
   - Sends audio via WebSocket as `assistant.audio_chunk` messages
4. Triggers greeting on `session.activate` WebSocket message

### Audio Format
- Sample rate: 8000 Hz (HFP requirement per DAT SDK docs)
- Codec: pcm_s16le
- Channels: 1 (mono)

## Current Issue

**Error:** `WebSocket is not connected.`

### Evidence from Logs

**Backend logs show successful audio generation and sending:**
```
HTTP Request: POST https://api.elevenlabs.io/v1/text-to-speech/JBFqnCBsd6RMkjVDRZzb?output_format=ulaw_8000 "HTTP/1.1 200 OK"
{"bytes": 35666, "chunks": 1, "duration_ms": 2229, "event": "greeting.audio.sent", ...}
```

**iOS app shows:**
- `playback_route: "BluetoothHFP"` (correct)
- Error: "WebSocket is not connected" appearing in app

### Debug Code Added
Added debug print statements to `SessionOrchestrator.swift` in `handleInboundWebSocketMessage()`:
- Logs when audio chunks are received
- Logs sample rate, byte count, isLast flag
- Logs any errors during playback

## Suspected Root Causes

1. **WebSocket timing issue**: The 10-second delay before sending greeting may cause the WebSocket to be in a disconnected/reconnecting state by the time the audio is sent.

2. **WebSocket connection race condition**: The greeting audio task is spawned with `asyncio.create_task()` which runs independently. If the WebSocket disconnects/reconnects during the 10-second wait, the reference to `websocket` may be stale.

3. **Audio route not ready**: HFP audio route may not be fully established when audio chunks arrive.

4. **Dual AVAudioEngine conflict**: `AssistantPlaybackEngine` was creating its own `AVAudioEngine` while `AudioCollectionManager` had a separate engine for mic capture. Two `AVAudioEngine` instances fighting for the same audio hardware causes playback to fail silently.

5. **AVAudioSession category mismatch**: Using `.voiceChat` mode with `.allowBluetoothHFP` applies aggressive audio processing that can interfere with TTS playback. DAT SDK recommends `.default` mode with `.allowBluetooth`.

## Fix Applied (2026-03-01)

### Root Cause
The main issue was **dual AVAudioEngine conflict**. iOS does not support multiple `AVAudioEngine` instances sharing the audio hardware reliably. The `AssistantPlaybackEngine` created its own engine, while `AudioCollectionManager` had another for microphone capture.

### Changes Made

1. **Merged playback into shared AVAudioEngine** ([AudioCollectionManager.swift](AudioCollectionManager.swift), [AssistantPlaybackEngine.swift](../Runtime/AssistantPlaybackEngine.swift), [SessionOrchestrator.swift](../Runtime/SessionOrchestrator.swift), [StreamSessionViewModel.swift](../ViewModels/StreamSessionViewModel.swift))
   - `AudioCollectionManager` now exposes `sharedAudioEngine`
   - `AssistantPlaybackEngine` accepts an optional external engine and attaches its player node to it
   - `SessionOrchestrator.Dependencies` includes `sharedAudioEngine`
   - `StreamSessionViewModel` passes the shared engine when creating the orchestrator

2. **Aligned AVAudioSession with DAT SDK** ([AudioCollectionManager.swift](AudioCollectionManager.swift))
   - Changed from `.playAndRecord, mode: .voiceChat, options: [.allowBluetoothHFP]`
   - To `.playAndRecord, mode: .default, options: [.allowBluetooth]` per DAT SDK sample code
   - Added `.notifyOthersOnDeactivation` on `setActive()`

3. **Reduced backend greeting delay** ([server.py](../../tools/mock_backend/server.py))
   - Changed from 10 seconds to 2 seconds (per DAT SDK HFP readiness guidance)
   - Reduces risk of WebSocket becoming stale during the wait

4. **Fixed error fallback sample rate** ([server.py](../../tools/mock_backend/server.py))
   - ElevenLabs error fallback was generating 16kHz audio
   - Changed to 8kHz to match HFP requirements

5. **Added diagnostic logging** ([AssistantPlaybackEngine.swift](../Runtime/AssistantPlaybackEngine.swift))
   - Logs current audio route, engine state, and buffer scheduling
   - Helps verify audio chunks are being processed correctly

### Verification Steps

1. Run mock backend with `ELEVENLABS_API_KEY` set
2. Activate assistant in app
3. Check Xcode console for:
   - `[DEBUG] Received audio chunk` - confirms WS delivery
   - `[AssistantPlaybackEngine] appendPCMData` - confirms playback processing
   - `Current route: BluetoothHFP` or `BluetoothA2DP`
4. Listen for greeting audio on glasses speakers

## Status Update (2026-03-01 - Attempt 2)

**Result:** Still no audio heard on glasses.

### Console Output Analysis

```
[AssistantPlaybackEngine] Engine running: true, ownsEngine: false
[AssistantPlaybackEngine] First chunk - connecting player node
[AssistantPlaybackEngine] Starting player node
AVAudioPlayerNode.mm:658   Player@0x14adf3c00: Engine is not running because it was not explicitly started or may have stopped because of an interruption. Cannot play yet!
[AssistantPlaybackEngine] Buffer scheduled, playerNode.isPlaying: false
```

### Root Cause Found: Node Attachment Order

**The bug:** We were calling `connect()` BEFORE `attach()`. In AVAudioEngine:
1. A node must be **attached** to the engine first
2. Only then can it be **connected** to other nodes

The code was:
```swift
// WRONG ORDER:
connectPlayerNodeIfNeeded() // calls audioEngine.connect() - node not attached yet!
startEngineIfNeeded()       // calls audioEngine.attach()
```

Should be:
```swift
// CORRECT ORDER:
startEngineIfNeeded()       // calls audioEngine.attach() first
connectPlayerNodeIfNeeded() // now connect() works
```

### Fix Applied
Reordered calls in `appendPCMData()` to attach before connect.

### What Changed
- Fixed duplicate `}` syntax error in `AssistantPlaybackEngine.swift`
- Code formatter reverted `.allowBluetooth` to `.allowBluetoothHFP` (this is actually fine per DAT SDK)

### New Hypotheses

1. **Engine timing**: `AudioCollectionManager.sharedAudioEngine` may not be running yet when the greeting audio arrives (2s after activate). The engine only starts in `start()` which is called after `prepareAudioSession()`, but the greeting arrives before recording fully starts.

2. **Player node connection order**: The player node must be attached AND connected to the mixer BEFORE the engine starts. Currently we attach lazily in `startEngineIfNeeded()` but connect in `connectPlayerNodeIfNeeded()`. If the engine is already running, connecting a new node may require stopping/restarting.

3. **Format/route mismatch**: The `mainMixerNode` format may not match the 8kHz mono PCM we're sending. On HFP, the hardware sample rate is locked to 8kHz, but the mixer might expect a different format.

4. **Output node not connected**: We connect `playerNode -> mainMixerNode` but need to verify `mainMixerNode -> outputNode` is also connected (usually automatic, but worth checking).

### Console Logs to Look For

```
[DEBUG] Received audio chunk: <chunk_id>, bytes: <count>, sampleRate: 8000, isLast: true
[AssistantPlaybackEngine] appendPCMData: <bytes> bytes, format: pcm_s16le@8000Hz/1ch  
[AssistantPlaybackEngine] Current route: BluetoothHFP
[AssistantPlaybackEngine] Engine running: true, ownsEngine: false
[AssistantPlaybackEngine] First chunk - connecting player node
[AssistantPlaybackEngine] Starting player node
[AssistantPlaybackEngine] Buffer scheduled, playerNode.isPlaying: true
```

If you see `Engine running: false` - that's the problem.

### Next Debugging Steps

1. **Check if engine is running when audio arrives**
   - Add log: `print("[DEBUG] sharedAudioEngine.isRunning: \(audioCollectionManager.sharedAudioEngine.isRunning)")`
   - In `SessionOrchestrator.handleInboundWebSocketMessage()` before calling `playbackEngine.appendChunk()`

2. **Try starting engine earlier**
   - Call `sharedAudioEngine.prepare()` and `sharedAudioEngine.start()` in `prepareAudioSession()` instead of waiting for `start()`

3. **Test with A2DP instead of HFP**
   - Temporarily change to `.playback` category with `.allowBluetoothA2DP` to isolate if HFP is the issue

4. **Verify greeting is not blocked by "Experience started"**
   - Increase backend delay back to 5-10 seconds to ensure glasses system audio is done

## Next Steps to Investigate

1. Check if WebSocket is still connected after the 10-second delay
2. Verify the `websocket` object passed to `stream_greeting_audio()` is still valid
3. Check Xcode console for `[DEBUG]` messages to see if audio chunks are being received
4. Consider sending greeting immediately (without delay) to test WebSocket connectivity
5. Check if the glasses' "Experience started" announcement can be disabled or if there's a callback for when it completes

## Files Modified

- `tools/mock_backend/server.py` - Added greeting audio streaming
- `tools/mock_backend/requirements.txt` - Added elevenlabs, python-dotenv
- `tools/mock_backend/run.sh` - Added env var documentation
- `MetaCollectLuigi/Runtime/SessionOrchestrator.swift` - Added debug logging

## Final Resolution (2026-03-01) ✅ WORKING

### Status
Greeting audio confirmed playing on glasses speakers.

### Root Causes Fixed

| # | Issue | Fix |
|---|-------|-----|
| 1 | **Dual AVAudioEngine conflict** — `AssistantPlaybackEngine` had its own engine; iOS cannot share audio hardware across two `AVAudioEngine` instances reliably | Merged onto `AudioCollectionManager.sharedAudioEngine`; `AssistantPlaybackEngine` now accepts an optional external engine |
| 2 | **AVAudioSession `.voiceChat` mode** interfered with TTS playback | Changed to `.default` mode with `.allowBluetoothHFP` per DAT SDK guidance |
| 3 | **Node attach/connect order** — `connectPlayerNodeIfNeeded()` was called before `attach()` | Reordered: attach node at init, connect graph at init, start engine lazily |
| 4 | **2s greeting delay too short** — greeting overlapped glasses' "Experience started" system announcement | Bumped to **4s** (tested: sufficient to clear announcement without WebSocket staleness) |
| 5 | **16kHz mock audio** in ElevenLabs error fallback | Fixed to 8kHz to match HFP hardware sample rate |

### Key Files Changed
- [AudioCollectionManager.swift](AudioCollectionManager.swift) — exposes `sharedAudioEngine`; `.default` mode session
- [AssistantPlaybackEngine.swift](../Runtime/AssistantPlaybackEngine.swift) — accepts external engine; fixed attach/connect order; no premature `stop()` on `stopResponse`
- [SessionOrchestrator.swift](../Runtime/SessionOrchestrator.swift) — passes `sharedAudioEngine` in `Dependencies`; added `flushPendingAudioChunks`
- [StreamSessionViewModel.swift](../ViewModels/StreamSessionViewModel.swift) — wires `sharedAudioEngine` and `flushPendingAudioChunks` into orchestrator
- [server.py](../../tools/mock_backend/server.py) — 4s delay; 8kHz audio throughout; μ-law → PCM conversion

## Related Documentation

- [Wearables DAT SDK.md](Wearables%20DAT%20SDK.md) - HFP uses 8kHz mono audio
- DAT SDK mentions "Experience started" is a system announcement from glasses
