<script lang="ts">
  import { onMount } from 'svelte';
  import { analyzeProbe, loadProbeConfig } from '$lib/audio/api';
  import { FALLBACK_PROBE_CONFIG, PROBE_LIMITS, clampProbeConfig } from '$lib/audio/chirp';
  import { captureProbe } from '$lib/audio/recorder';
  import type { AnalysisResponse, ProbeConfig } from '$lib/audio/types';
  import WaveformCanvas from './WaveformCanvas.svelte';

  let config: ProbeConfig = { ...FALLBACK_PROBE_CONFIG };
  let loadingConfig = true;
  let running = false;
  let status = 'Ready';
  let error = '';
  let result: AnalysisResponse | null = null;
  let samples: Float32Array | null = null;
  let sampleRateHz = 0;
  type NumericProbeConfigKey = Exclude<keyof ProbeConfig, 'signal_type'>;

  onMount(async () => {
    try {
      const envelope = await loadProbeConfig();
      config = clampProbeConfig(envelope.default);
    } catch (loadError) {
      console.warn(loadError);
      status = 'Using local default probe config';
    } finally {
      loadingConfig = false;
    }
  });

  async function runProbe(): Promise<void> {
    running = true;
    error = '';
    result = null;
    status = 'Starting';

    try {
      const capture = await captureProbe(config, (nextStatus) => {
        status = nextStatus;
      });
      samples = capture.samples;
      sampleRateHz = capture.sampleRateHz;
      status = 'Uploading';
      result = await analyzeProbe(capture.wavBlob, capture.metadata);
      status = 'Complete';
    } catch (probeError) {
      error = probeError instanceof Error ? probeError.message : String(probeError);
      status = 'Stopped';
    } finally {
      running = false;
    }
  }

  function updateNumber(key: NumericProbeConfigKey, value: string): void {
    const numericValue = Number(value);
    if (Number.isFinite(numericValue)) {
      config = clampProbeConfig({ ...config, [key]: numericValue });
    }
  }

  $: expectedSeconds =
    (config.pre_roll_ms + config.duration_ms + config.post_roll_ms) / 1000;
</script>

<main class="main">
  <section class="hero-row" aria-label="Acoustic probe workflow">
    <div class="panel">
      <div class="panel-header">
        <h1 class="panel-title">Active Probe</h1>
        <p class="panel-subtitle">Desktop Chrome gate: chirp capture, WAV upload, dummy analysis.</p>
      </div>

      <div class="controls">
        <div class="warning">Do not use headphones or earbuds during active probing.</div>

        <div class="control-grid">
          <div class="field">
            <label for="start-hz">Start Hz</label>
            <input
              id="start-hz"
              type="number"
              min={PROBE_LIMITS.start_hz.min}
              max={PROBE_LIMITS.start_hz.max}
              step="50"
              value={config.start_hz}
              disabled={running || loadingConfig}
              on:input={(event) => updateNumber('start_hz', event.currentTarget.value)}
            />
          </div>
          <div class="field">
            <label for="end-hz">End Hz</label>
            <input
              id="end-hz"
              type="number"
              min={PROBE_LIMITS.end_hz.min}
              max={PROBE_LIMITS.end_hz.max}
              step="50"
              value={config.end_hz}
              disabled={running || loadingConfig}
              on:input={(event) => updateNumber('end_hz', event.currentTarget.value)}
            />
          </div>
          <div class="field">
            <label for="duration-ms">Chirp ms</label>
            <input
              id="duration-ms"
              type="number"
              min={PROBE_LIMITS.duration_ms.min}
              max={PROBE_LIMITS.duration_ms.max}
              step="50"
              value={config.duration_ms}
              disabled={running || loadingConfig}
              on:input={(event) => updateNumber('duration_ms', event.currentTarget.value)}
            />
          </div>
          <div class="field">
            <label for="amplitude">Amplitude</label>
            <input
              id="amplitude"
              type="number"
              min={PROBE_LIMITS.amplitude.min}
              max={PROBE_LIMITS.amplitude.max}
              step="0.01"
              value={config.amplitude}
              disabled={running || loadingConfig}
              on:input={(event) => updateNumber('amplitude', event.currentTarget.value)}
            />
          </div>
          <div class="field">
            <label for="pre-roll-ms">Pre-roll ms</label>
            <input
              id="pre-roll-ms"
              type="number"
              min={PROBE_LIMITS.pre_roll_ms.min}
              max={PROBE_LIMITS.pre_roll_ms.max}
              step="50"
              value={config.pre_roll_ms}
              disabled={running || loadingConfig}
              on:input={(event) => updateNumber('pre_roll_ms', event.currentTarget.value)}
            />
          </div>
          <div class="field">
            <label for="post-roll-ms">Post-roll ms</label>
            <input
              id="post-roll-ms"
              type="number"
              min={PROBE_LIMITS.post_roll_ms.min}
              max={PROBE_LIMITS.post_roll_ms.max}
              step="50"
              value={config.post_roll_ms}
              disabled={running || loadingConfig}
              on:input={(event) => updateNumber('post_roll_ms', event.currentTarget.value)}
            />
          </div>
        </div>

        <div class="actions">
          <button class="primary-button" type="button" disabled={running || loadingConfig} on:click={runProbe}>
            {running ? 'Running' : 'Start Probe'}
          </button>
          <span class="status-line">{status} - {expectedSeconds.toFixed(2)} s capture</span>
        </div>

        {#if error}
          <div class="error" role="alert">{error}</div>
        {/if}
      </div>
    </div>

    <div class="panel">
      <div class="panel-header">
        <h2 class="panel-title">Signal</h2>
        <p class="panel-subtitle">Captured PCM waveform and API sanity metrics.</p>
      </div>

      <div class="signal-area">
        <div class="waveform-shell">
          <WaveformCanvas {samples} {sampleRateHz} />
        </div>

        <div class="metric-grid">
          <div class="metric">
            <span>Duration</span>
            <strong>{result ? `${result.audio.duration_seconds.toFixed(3)} s` : '--'}</strong>
          </div>
          <div class="metric">
            <span>Sample rate</span>
            <strong>{result ? `${result.audio.sample_rate_hz} Hz` : '--'}</strong>
          </div>
          <div class="metric">
            <span>RMS</span>
            <strong>{result ? result.audio.rms.toFixed(5) : '--'}</strong>
          </div>
          <div class="metric">
            <span>Peak</span>
            <strong>{result ? result.audio.peak_amplitude.toFixed(5) : '--'}</strong>
          </div>
        </div>

        {#if result}
          <dl class="result-list">
            <div class="result-row">
              <dt>Analysis ID</dt>
              <dd>{result.analysis_id}</dd>
            </div>
            <div class="result-row">
              <dt>Capture path</dt>
              <dd>{result.probe.browser.capture_path}</dd>
            </div>
            <div class="result-row">
              <dt>Upload</dt>
              <dd>{(result.audio.byte_count / 1024).toFixed(1)} KB WAV</dd>
            </div>
            <div class="result-row">
              <dt>Alignment</dt>
              <dd>{result.alignment.method}</dd>
            </div>
          </dl>
        {/if}

        {#if result?.warnings.length}
          <ul class="notice-list" aria-label="Analysis warnings">
            {#each result.warnings as warning}
              <li>{warning}</li>
            {/each}
          </ul>
        {/if}
      </div>
    </div>
  </section>
</main>
