<script lang="ts">
  import { onMount } from "svelte";
  import { analyzeProbe, loadProbeConfig } from "$lib/audio/api";
  import {
    FALLBACK_PROBE_CONFIG,
    PROBE_LIMITS,
    clampProbeConfig,
  } from "$lib/audio/chirp";
  import { captureProbe } from "$lib/audio/recorder";
  import type {
    AnalysisResponse,
    ProbeCapture,
    ProbeConfig,
  } from "$lib/audio/types";
  import type {
    CalibrationEstimate,
    CalibrationProfile,
  } from "$lib/calibration/types";
  import CalibrationManager from "./CalibrationManager.svelte";
  import DatasetCapturePanel from "./DatasetCapturePanel.svelte";
  import SpectrogramCanvas from "./SpectrogramCanvas.svelte";
  import SpectrumCanvas from "./SpectrumCanvas.svelte";
  import WaveformCanvas from "./WaveformCanvas.svelte";

  type SignalView = "waveform" | "fft" | "stft" | "mel";

  let config: ProbeConfig = { ...FALLBACK_PROBE_CONFIG };
  let loadingConfig = true;
  let running = false;
  let status = "Ready";
  let error = "";
  let result: AnalysisResponse | null = null;
  let lastCapture: ProbeCapture | null = null;
  let samples: Float32Array | null = null;
  let sampleRateHz = 0;
  let signalView: SignalView = "waveform";
  let selectedProfile: CalibrationProfile | null = null;
  let calibrationEstimate: CalibrationEstimate | null = null;
  let selectedAnchorCount = 0;
  let selectedObservationCount = 0;
  type NumericProbeConfigKey = Exclude<keyof ProbeConfig, "signal_type">;

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
    lastCapture = null;
    status = "Starting";

    try {
      const capture = await captureProbe(config, (nextStatus) => {
        status = nextStatus;
      });
      lastCapture = capture;
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

  function formatPercent(value: number | null | undefined): string {
    if (value === null || value === undefined || !Number.isFinite(value)) {
      return "--";
    }
    return `${value.toFixed(0)}%`;
  }

  function formatConfidence(estimateValue: CalibrationEstimate | null): string {
    if (!estimateValue || estimateValue.status !== "ready") {
      return "--";
    }
    if (estimateValue.referenceMatch) {
      return "reference match";
    }
    return `${estimateValue.confidenceLabel} ${(estimateValue.confidence * 100).toFixed(0)}%`;
  }

  function formatFillEstimate(
    estimateValue: CalibrationEstimate | null,
  ): string {
    if (!estimateValue) {
      return "--";
    }
    if (estimateValue.referenceMatch) {
      return estimateValue.referenceMatch.label;
    }
    return formatPercent(estimateValue.fillPercent);
  }

  function formatReferenceMatch(
    estimateValue: CalibrationEstimate | null,
  ): string {
    return (
      estimateValue?.referenceMatch?.label ??
      estimateValue?.nearestAnchor?.label ??
      "--"
    );
  }

  function formatRepeatCount(count: number | null | undefined): string {
    if (!count) {
      return "n=0";
    }
    return `n=${count}`;
  }

  function formatStability(estimateValue: CalibrationEstimate | null): string {
    const value = estimateValue?.profileStability.featureStdMax;
    if (value === null || value === undefined || !Number.isFinite(value)) {
      return "--";
    }
    return value.toFixed(2);
  }
</script>

<main class="main">
  <section class="hero-row" aria-label="Acoustic probe workflow">
    <div class="panel">
      <div class="panel-header">
        <h1 class="panel-title">Active Probe</h1>
        <p class="panel-subtitle">
          Chirp capture, WAV upload, alignment, and Phase 2 DSP analysis.
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

        <CalibrationManager
          {result}
          bind:selectedProfile
          bind:calibrationEstimate
          bind:selectedAnchorCount
          bind:selectedObservationCount
        />

        <DatasetCapturePanel
          {result}
          wavBlob={lastCapture?.wavBlob ?? null}
          metadata={lastCapture?.metadata ?? null}
        />
      </div>
    </div>

    <div class="panel">
      <div class="panel-header">
        <h2 class="panel-title">Signal</h2>
        <p class="panel-subtitle">
          Captured PCM waveform and API-derived frequency views.
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
            <span>Duration</span>
            <strong
              >{result
                ? `${result.audio.duration_seconds.toFixed(3)} s`
                : "--"}</strong
            >
          </div>
          <div class="metric">
            <span>Sample rate</span>
            <strong
              >{result ? `${result.audio.sample_rate_hz} Hz` : "--"}</strong
            >
          </div>
          <div class="metric">
            <span>Alignment</span>
            <strong
              >{result
                ? `${(result.alignment.confidence ?? 0).toFixed(3)}`
                : "--"}</strong
            >
          </div>
          <div class="metric">
            <span>SNR</span>
            <strong
              >{result ? formatDb(result.dsp.signal_to_noise_db) : "--"}</strong
            >
          </div>
          <div class="metric">
            <span>Peak Hz</span>
            <strong>{topPeak ? formatHz(topPeak.frequency_hz) : "--"}</strong>
          </div>
          <div class="metric">
            <span>RT60</span>
            <strong
              >{result
                ? formatSeconds(result.dsp.decay.rt60_seconds)
                : "--"}</strong
            >
          </div>
          <div class="metric">
            <span>Fill estimate</span>
            <strong>{formatFillEstimate(calibrationEstimate)}</strong>
          </div>
          <div class="metric">
            <span>Confidence</span>
            <strong>
              {calibrationEstimate?.status === "ready"
                ? formatConfidence(calibrationEstimate)
                : `${selectedAnchorCount}/3 anchors`}
            </strong>
          </div>
          <div class="metric">
            <span>Anchor stability</span>
            <strong>{formatStability(calibrationEstimate)}</strong>
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
              <dt>Centroid</dt>
              <dd>{formatHz(result.dsp.fft.centroid_hz)}</dd>
            </div>
            <div class="result-row">
              <dt>Rolloff</dt>
              <dd>{formatHz(result.dsp.fft.rolloff_hz)}</dd>
            </div>
            <div class="result-row">
              <dt>Profile</dt>
              <dd>{selectedProfile?.name ?? "--"}</dd>
            </div>
            <div class="result-row">
              <dt>Reference match</dt>
              <dd>{formatReferenceMatch(calibrationEstimate)}</dd>
            </div>
            <div class="result-row">
              <dt>Free-air ref</dt>
              <dd>
                {selectedProfile?.freeAirReference
                  ? formatRepeatCount(
                      selectedProfile.freeAirReference.sampleCount,
                    )
                  : "--"}
              </dd>
            </div>
            <div class="result-row">
              <dt>Profile samples</dt>
              <dd>{selectedObservationCount}</dd>
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
        {/if}

        {#if result?.warnings.length}
          <ul class="notice-list" aria-label="Analysis warnings">
            {#each result.warnings as warning}
              <li>{warning}</li>
            {/each}
          </ul>
        {/if}

        {#if calibrationEstimate?.warnings.length}
          <ul class="notice-list" aria-label="Calibration warnings">
            {#each calibrationEstimate.warnings as warning}
              <li>{warning}</li>
            {/each}
          </ul>
        {/if}
      </div>
    </div>
  </section>
</main>
