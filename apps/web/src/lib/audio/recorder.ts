import { clampProbeConfig, generateLogChirp } from './chirp';
import type { BrowserCaptureMetadata, CapturePath, ProbeCapture, ProbeConfig } from './types';
import { encodePcm16Wav } from './wav';

declare global {
  interface Window {
    webkitAudioContext?: typeof AudioContext;
  }
}

type RecorderHandle = {
  capturePath: CapturePath;
  stop: () => void;
  finish: () => Promise<Float32Array>;
};

type WorkletMessage =
  | {
      type: 'pcm-chunk';
      buffer: ArrayBuffer;
      frames: number;
    }
  | {
      type: 'flushed';
    };

type CaptureStatus =
  | 'Requesting microphone'
  | 'Opening audio context'
  | 'Recording pre-roll'
  | 'Playing chirp'
  | 'Recording decay'
  | 'Encoding WAV'
  | 'Uploading';

export async function captureProbe(
  config: ProbeConfig,
  onStatus: (status: CaptureStatus) => void
): Promise<ProbeCapture> {
  const safeConfig = clampProbeConfig(config);
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error('This browser does not expose microphone capture.');
  }

  const AudioContextCtor = window.AudioContext ?? window.webkitAudioContext;
  if (!AudioContextCtor) {
    throw new Error('This browser does not expose Web Audio.');
  }

  onStatus('Opening audio context');
  const audioContext = new AudioContextCtor();
  await audioContext.resume();

  const requestedConstraints: MediaStreamConstraints = {
    audio: {
      echoCancellation: false,
      noiseSuppression: false,
      autoGainControl: false,
      channelCount: 1
    }
  };

  onStatus('Requesting microphone');
  const stream = await navigator.mediaDevices.getUserMedia(requestedConstraints);

  let recorder: RecorderHandle | null = null;
  try {
    recorder = await createRecorder(audioContext, stream);
    const recordingStartedAt = audioContext.currentTime;
    const chirpStartedAt = recordingStartedAt + safeConfig.pre_roll_ms / 1000;
    const chirpEndedAt = chirpStartedAt + safeConfig.duration_ms / 1000;
    const captureEndedAt = chirpEndedAt + safeConfig.post_roll_ms / 1000;
    const chirpPlayback = playChirp(audioContext, safeConfig, chirpStartedAt);

    onStatus('Recording pre-roll');
    await waitUntilContextTime(audioContext, chirpStartedAt);

    onStatus('Playing chirp');
    await waitUntilContextTime(audioContext, chirpEndedAt);

    onStatus('Recording decay');
    await waitUntilContextTime(audioContext, captureEndedAt);
    await chirpPlayback;

    onStatus('Encoding WAV');
    const samples = await recorder.finish();
    const wavBlob = encodePcm16Wav(samples, audioContext.sampleRate);
    const metadata = buildMetadata({
      config: safeConfig,
      stream,
      audioContext,
      requestedConstraints,
      capturePath: recorder.capturePath,
      timing: {
        recordingStartedAt,
        chirpStartedAt,
        chirpEndedAt,
        captureEndedAt
      }
    });

    return {
      wavBlob,
      samples,
      sampleRateHz: audioContext.sampleRate,
      metadata
    };
  } finally {
    recorder?.stop();
    stream.getTracks().forEach((track) => track.stop());
    await audioContext.close();
  }
}

async function createRecorder(audioContext: AudioContext, stream: MediaStream): Promise<RecorderHandle> {
  if (audioContext.audioWorklet) {
    try {
      await audioContext.audioWorklet.addModule('/audio/pcm-recorder-worklet.js');
      return createWorkletRecorder(audioContext, stream);
    } catch (error) {
      console.warn('AudioWorklet recorder unavailable; falling back to ScriptProcessor.', error);
    }
  }

  return createScriptProcessorRecorder(audioContext, stream);
}

function createWorkletRecorder(audioContext: AudioContext, stream: MediaStream): RecorderHandle {
  const chunks: Float32Array[] = [];
  const source = audioContext.createMediaStreamSource(stream);
  const processor = new AudioWorkletNode(audioContext, 'pcm-recorder');
  const sink = audioContext.createGain();
  sink.gain.value = 0;

  let flushResolve: (() => void) | null = null;
  processor.port.onmessage = (event: MessageEvent<WorkletMessage>) => {
    const message = event.data;
    if (message.type === 'pcm-chunk') {
      const view = new Float32Array(message.buffer, 0, message.frames);
      chunks.push(new Float32Array(view));
      processor.port.postMessage({ type: 'return-buffer', buffer: message.buffer }, [message.buffer]);
    }
    if (message.type === 'flushed') {
      flushResolve?.();
      flushResolve = null;
    }
  };

  source.connect(processor);
  processor.connect(sink);
  sink.connect(audioContext.destination);

  return {
    capturePath: 'audio_worklet',
    stop: () => {
      source.disconnect();
      processor.disconnect();
      sink.disconnect();
      processor.port.close();
    },
    finish: async () => {
      await new Promise<void>((resolve) => {
        const timeout = window.setTimeout(() => {
          flushResolve = null;
          resolve();
        }, 150);
        flushResolve = () => {
          window.clearTimeout(timeout);
          resolve();
        };
        processor.port.postMessage({ type: 'flush' });
      });
      return mergeChunks(chunks);
    }
  };
}

function createScriptProcessorRecorder(audioContext: AudioContext, stream: MediaStream): RecorderHandle {
  const chunks: Float32Array[] = [];
  const source = audioContext.createMediaStreamSource(stream);
  const processor = audioContext.createScriptProcessor(4096, 1, 1);
  const sink = audioContext.createGain();
  sink.gain.value = 0;

  processor.onaudioprocess = (event) => {
    chunks.push(new Float32Array(event.inputBuffer.getChannelData(0)));
  };

  source.connect(processor);
  processor.connect(sink);
  sink.connect(audioContext.destination);

  return {
    capturePath: 'script_processor',
    stop: () => {
      source.disconnect();
      processor.disconnect();
      sink.disconnect();
    },
    finish: async () => mergeChunks(chunks)
  };
}

async function playChirp(audioContext: AudioContext, config: ProbeConfig, startTime: number): Promise<void> {
  const chirp = generateLogChirp(config, audioContext.sampleRate);
  const buffer = audioContext.createBuffer(1, chirp.length, audioContext.sampleRate);
  buffer.getChannelData(0).set(chirp);

  const source = audioContext.createBufferSource();
  source.buffer = buffer;
  source.connect(audioContext.destination);

  await new Promise<void>((resolve, reject) => {
    const scheduledDelaySeconds = Math.max(0, startTime - audioContext.currentTime);
    const timeout = window.setTimeout(resolve, (scheduledDelaySeconds + config.duration_ms / 1000 + 1) * 1000);
    source.onended = () => {
      window.clearTimeout(timeout);
      resolve();
    };
    try {
      source.start(startTime);
    } catch (error) {
      window.clearTimeout(timeout);
      reject(error);
    }
  });

  source.disconnect();
}

function buildMetadata({
  config,
  stream,
  audioContext,
  requestedConstraints,
  capturePath,
  timing
}: {
  config: ProbeConfig;
  stream: MediaStream;
  audioContext: AudioContext;
  requestedConstraints: MediaStreamConstraints;
  capturePath: CapturePath;
  timing: {
    recordingStartedAt: number;
    chirpStartedAt: number;
    chirpEndedAt: number;
    captureEndedAt: number;
  };
}): ProbeCapture['metadata'] {
  const track = stream.getAudioTracks()[0];
  const browser: BrowserCaptureMetadata = {
    user_agent: navigator.userAgent,
    audio_context_sample_rate_hz: audioContext.sampleRate,
    media_track_settings: track?.getSettings() ?? {},
    requested_constraints: requestedConstraints,
    capture_path: capturePath,
    recording_started_at_context_seconds: timing.recordingStartedAt,
    chirp_started_at_context_seconds: timing.chirpStartedAt,
    chirp_ended_at_context_seconds: timing.chirpEndedAt,
    capture_ended_at_context_seconds: timing.captureEndedAt
  };

  return {
    client_recorded_at: new Date().toISOString(),
    probe_config: config,
    browser
  };
}

function mergeChunks(chunks: Float32Array[]): Float32Array {
  const length = chunks.reduce((total, chunk) => total + chunk.length, 0);
  const samples = new Float32Array(length);
  let offset = 0;
  for (const chunk of chunks) {
    samples.set(chunk, offset);
    offset += chunk.length;
  }
  return samples;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function waitUntilContextTime(audioContext: AudioContext, targetTime: number): Promise<void> {
  const delayMs = Math.max(0, (targetTime - audioContext.currentTime) * 1000);
  return sleep(delayMs);
}
