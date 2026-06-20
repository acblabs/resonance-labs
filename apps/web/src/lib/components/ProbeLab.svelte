<script lang="ts">
  import { onMount } from "svelte";
  import {
    analyzeProbe,
    explainProbeResult,
    loadProbeConfig,
  } from "$lib/audio/api";
  import {
    FALLBACK_PROBE_CONFIG,
    PROBE_LIMITS,
    clampProbeConfig,
  } from "$lib/audio/chirp";
  import { captureProbe } from "$lib/audio/recorder";
  import type {
    AnalysisResponse,
    LlmExplainResponse,
    ProbeCapture,
    ProbeConfig,
  } from "$lib/audio/types";
  import SpectrogramCanvas from "./SpectrogramCanvas.svelte";
  import SpectrumCanvas from "./SpectrumCanvas.svelte";
  import WaveformCanvas from "./WaveformCanvas.svelte";

  type SignalView = "waveform" | "fft" | "stft" | "mel";
  type NumericProbeConfigKey = Exclude<keyof ProbeConfig, "signal_type">;

  let config: ProbeConfig = { ...FALLBACK_PROBE_CONFIG };
  let loadingConfig = true;
  let running = false;
  let status = "Ready";
  let error = "";
  let result: AnalysisResponse | null = null;
  let samples: Float32Array | null = null;
  let sampleRateHz = 0;
  let signalView: SignalView = "waveform";
  let explanation: LlmExplainResponse | null = null;
  let explaining = false;
  let explainError = "";

  onMount(async () => {
    await loadConfig();
  });

  async function loadConfig(): Promise<void> {
    try {
      const envelope = await loadProbeConfig();
      config = clampProbeConfig(envelope.default);
    } catch (loadError) {
      console.warn(loadError);
      status = "Using local default probe config";
    } finally {
      loadingConfig = false;
    }
  }

  async function runProbe(): Promise<void> {
    running = true;
    error = "";
    result = null;
    explanation = null;
    explainError = "";
    status = "Starting";

    try {
      const capture: ProbeCapture = await captureProbe(config, (nextStatus) => {
        status = nextStatus;
      });
      samples = capture.samples;
      sampleRateHz = capture.sampleRateHz;
      status = "Uploading";
      result = await analyzeProbe(capture.wavBlob, capture.metadata);
      status = "Complete";
    } catch (probeError) {
      error =
        probeError instanceof Error ? probeError.message : String(probeError);
      status = "Stopped";
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

  async function explainCurrentResult(): Promise<void> {
    if (!result || explaining) {
      return;
    }
    explaining = true;
    explainError = "";
    try {
      explanation = await explainProbeResult(result);
    } catch (errorValue) {
      explainError =
        errorValue instanceof Error ? errorValue.message : String(errorValue);
    } finally {
      explaining = false;
    }
  }

  $: expectedSeconds =
    (config.pre_roll_ms + config.duration_ms + config.post_roll_ms) / 1000;
  $: topPeak = result?.dsp.dominant_peaks[0] ?? null;
  $: activeSpectrogram =
    signalView === "mel"
      ? (result?.dsp.mel_spectrogram ?? null)
      : (result?.dsp.stft ?? null);

  function formatHz(value: number | null | undefined): string {
    if (value === null || value === undefined || !Number.isFinite(value)) {
      return "--";
    }
    if (value >= 1000) {
      return `${(value / 1000).toFixed(value >= 10000 ? 1 : 2)} kHz`;
    }
    return `${Math.round(value)} Hz`;
  }

  function formatDb(value: number | null | undefined): string {
    if (value === null || value === undefined || !Number.isFinite(value)) {
      return "--";
    }
    return `${value.toFixed(1)} dB`;
  }

  function formatSeconds(value: number | null | undefined): string {
    if (value === null || value === undefined || !Number.isFinite(value)) {
      return "--";
    }
    return `${value.toFixed(3)} s`;
  }

  function formatRoomCharacter(analysis: AnalysisResponse | null): string {
    const rt60 = analysis?.dsp.decay.rt60_seconds;
    if (rt60 === null || rt60 === undefined || !Number.isFinite(rt60)) {
      return "--";
    }
    if (rt60 < 0.25) {
      return "Dry";
    }
    if (rt60 > 0.75) {
      return "Live";
    }
    return "Balanced";
  }

  function formatBrightness(analysis: AnalysisResponse | null): string {
    const centroid = analysis?.dsp.fft.centroid_hz;
    if (centroid === null || centroid === undefined || !Number.isFinite(centroid)) {
      return "--";
    }
    if (centroid > 3500) {
      return "Bright";
    }
    if (centroid < 1200) {
      return "Dark";
    }
    return "Neutral";
  }

  function formatMode(analysis: AnalysisResponse | null): string {
    const peak = analysis?.dsp.dominant_peaks[0];
    if (!peak) {
      return "--";
    }
    const q = peak.q_factor === null ? "" : `, Q ${peak.q_factor.toFixed(1)}`;
    return `${formatHz(peak.frequency_hz)}${q}`;
  }
</script>

<main class="main">
  <section class="hero-row" aria-label="Acoustic probe workflow">
    <div class="panel">
      <div class="panel-header">
        <h1 class="panel-title">Room Acoustic Fingerprint</h1>
        <p class="panel-subtitle">
          Chirp capture, impulse-response features, spectrograms, decay, and room-mode descriptors.
        </p>
      </div>

      <div class="controls">
        <div class="warning">
          Do not use headphones or earbuds during active probing.
        </div>

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
              on:input={(event) =>
                updateNumber("start_hz", event.currentTarget.value)}
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
              on:input={(event) =>
                updateNumber("end_hz", event.currentTarget.value)}
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
              on:input={(event) =>
                updateNumber("duration_ms", event.currentTarget.value)}
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
              on:input={(event) =>
                updateNumber("amplitude", event.currentTarget.value)}
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
              on:input={(event) =>
                updateNumber("pre_roll_ms", event.currentTarget.value)}
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
              on:input={(event) =>
                updateNumber("post_roll_ms", event.currentTarget.value)}
            />
          </div>
        </div>

        <div class="actions">
          <button
            class="primary-button"
            type="button"
            disabled={running || loadingConfig}
            on:click={runProbe}
          >
            {running ? "Running" : "Start Probe"}
          </button>
          <span class="status-line"
            >{status} - {expectedSeconds.toFixed(2)} s capture</span
          >
        </div>

        {#if error}
          <div class="error" role="alert">{error}</div>
        {/if}
      </div>
    </div>

    <div class="panel">
      <div class="panel-header">
        <h2 class="panel-title">Acoustic Image</h2>
        <p class="panel-subtitle">
          Captured waveform, frequency response, and time-frequency room fingerprint.
        </p>
      </div>

      <div class="signal-area">
        <div class="view-tabs" role="tablist" aria-label="Signal view">
          <button
            type="button"
            role="tab"
            class:active-tab={signalView === "waveform"}
            aria-selected={signalView === "waveform"}
            on:click={() => (signalView = "waveform")}
          >
            Waveform
          </button>
          <button
            type="button"
            role="tab"
            class:active-tab={signalView === "fft"}
            aria-selected={signalView === "fft"}
            on:click={() => (signalView = "fft")}
          >
            FFT
          </button>
          <button
            type="button"
            role="tab"
            class:active-tab={signalView === "stft"}
            aria-selected={signalView === "stft"}
            on:click={() => (signalView = "stft")}
          >
            STFT
          </button>
          <button
            type="button"
            role="tab"
            class:active-tab={signalView === "mel"}
            aria-selected={signalView === "mel"}
            on:click={() => (signalView = "mel")}
          >
            Mel
          </button>
        </div>

        <div class="plot-shell">
          {#if signalView === "waveform"}
            <WaveformCanvas {samples} {sampleRateHz} />
          {:else if signalView === "fft"}
            <SpectrumCanvas
              series={result?.dsp.fft.series ?? null}
              peaks={result?.dsp.dominant_peaks ?? []}
            />
          {:else}
            <SpectrogramCanvas grid={activeSpectrogram} />
          {/if}
        </div>

        <div class="metric-grid">
          <div class="metric">
            <span>Room character</span>
            <strong>{formatRoomCharacter(result)}</strong>
          </div>
          <div class="metric">
            <span>Brightness</span>
            <strong>{formatBrightness(result)}</strong>
          </div>
          <div class="metric">
            <span>Dominant mode</span>
            <strong>{formatMode(result)}</strong>
          </div>
          <div class="metric">
            <span>RT60 proxy</span>
            <strong>{result ? formatSeconds(result.dsp.decay.rt60_seconds) : "--"}</strong>
          </div>
          <div class="metric">
            <span>Alignment</span>
            <strong>
              {result ? `${(result.alignment.confidence ?? 0).toFixed(3)}` : "--"}
            </strong>
          </div>
          <div class="metric">
            <span>SNR</span>
            <strong>{result ? formatDb(result.dsp.signal_to_noise_db) : "--"}</strong>
          </div>
          <div class="metric">
            <span>Centroid</span>
            <strong>{result ? formatHz(result.dsp.fft.centroid_hz) : "--"}</strong>
          </div>
          <div class="metric">
            <span>Rolloff</span>
            <strong>{result ? formatHz(result.dsp.fft.rolloff_hz) : "--"}</strong>
          </div>
          <div class="metric">
            <span>Duration</span>
            <strong>
              {result ? `${result.audio.duration_seconds.toFixed(3)} s` : "--"}
            </strong>
          </div>
          <div class="metric">
            <span>Sample rate</span>
            <strong>{result ? `${result.audio.sample_rate_hz} Hz` : "--"}</strong>
          </div>
          <div class="metric">
            <span>Peak amplitude</span>
            <strong>{result ? result.audio.peak_amplitude.toFixed(3) : "--"}</strong>
          </div>
          <div class="metric">
            <span>Warnings</span>
            <strong>{result?.warnings.length ?? 0}</strong>
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
              <dt>Detected chirp</dt>
              <dd>{formatSeconds(result.alignment.detected_start_seconds)}</dd>
            </div>
            <div class="result-row">
              <dt>Bandpass</dt>
              <dd>
                {formatHz(result.dsp.bandpass_low_hz)} - {formatHz(
                  result.dsp.bandpass_high_hz,
                )}
              </dd>
            </div>
            <div class="result-row">
              <dt>Decay window</dt>
              <dd>
                {formatSeconds(result.dsp.decay.window_start_seconds)} - {formatSeconds(
                  result.dsp.decay.window_end_seconds,
                )}
              </dd>
            </div>
            <div class="result-row">
              <dt>Decay fit</dt>
              <dd>
                {result.dsp.decay.fit_r2 === null
                  ? "--"
                  : result.dsp.decay.fit_r2.toFixed(3)}
              </dd>
            </div>
          </dl>

          {#if result.dsp.transfer_response.length}
            <div class="transfer-list" aria-label="Transfer response bands">
              {#each result.dsp.transfer_response as band}
                <div class="transfer-row">
                  <span>{formatHz(band.start_hz)}-{formatHz(band.end_hz)}</span>
                  <strong>{formatDb(band.mean_db)}</strong>
                </div>
              {/each}
            </div>
          {/if}

          <div class="explain-block" aria-label="Probe explanation">
            <div class="section-heading">
              <h2>Lab assistant</h2>
              <span>
                {explanation
                  ? `${explanation.model} - ${explanation.status}`
                  : "Ready"}
              </span>
            </div>
            <div class="actions">
              <button
                class="secondary-button"
                type="button"
                disabled={explaining}
                on:click={explainCurrentResult}
              >
                {explaining ? "Explaining" : "Explain"}
              </button>
            </div>
            {#if explainError}
              <div class="error" role="alert">{explainError}</div>
            {/if}
            {#if explanation}
              <p class="assistant-summary">{explanation.explanation.summary}</p>
              <div class="assistant-columns">
                <div>
                  <h3>Observed</h3>
                  <ul>
                    {#each explanation.explanation.observations as item}
                      <li>{item}</li>
                    {/each}
                  </ul>
                </div>
                <div>
                  <h3>Hypotheses</h3>
                  <ul>
                    {#each explanation.explanation.acoustic_hypotheses as item}
                      <li>{item}</li>
                    {/each}
                  </ul>
                </div>
                <div>
                  <h3>Next</h3>
                  <ul>
                    {#each explanation.explanation.next_measurement as item}
                      <li>{item}</li>
                    {/each}
                  </ul>
                </div>
              </div>
              {#if explanation.explanation.caveats.length}
                <ul class="notice-list" aria-label="Explanation caveats">
                  {#each explanation.explanation.caveats as caveat}
                    <li>{caveat}</li>
                  {/each}
                </ul>
              {/if}
            {/if}
          </div>
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
