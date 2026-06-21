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
  import {
    buildAcousticReport,
    buildDeviceValidation,
    compareAcousticReports,
    downloadAcousticReportJson,
    downloadAcousticReportPng,
    parseAcousticReportPayload,
  } from "$lib/report/acousticReport";
  import type {
    AnalysisResponse,
    LlmExplainResponse,
    ProbeCapture,
    ProbeConfig,
  } from "$lib/audio/types";
  import type {
    AcousticReport,
    DeviceValidationSummary,
    ValidationStatus,
  } from "$lib/report/acousticReport";
  import SpectrogramCanvas from "./SpectrogramCanvas.svelte";
  import SpectrumCanvas from "./SpectrumCanvas.svelte";
  import WaveformCanvas from "./WaveformCanvas.svelte";

  type SignalView = "waveform" | "fft" | "stft" | "mel";
  type NumericProbeConfigKey = Exclude<keyof ProbeConfig, "signal_type">;
  const VERY_HIGH_Q_THRESHOLD = 300;

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
  let exportingReport = false;
  let reportError = "";
  let comparisonReports: AcousticReport[] = [];
  let comparisonError = "";

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
    reportError = "";
    comparisonError = "";
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

  async function exportCurrentReport(kind: "json" | "png"): Promise<void> {
    if (!result || exportingReport) {
      return;
    }
    exportingReport = true;
    reportError = "";
    try {
      const report = buildAcousticReport(result, explanation);
      if (kind === "json") {
        downloadAcousticReportJson(report);
      } else {
        await downloadAcousticReportPng(report);
      }
    } catch (errorValue) {
      reportError =
        errorValue instanceof Error ? errorValue.message : String(errorValue);
    } finally {
      exportingReport = false;
    }
  }

  async function importComparisonReports(event: Event): Promise<void> {
    const input = event.currentTarget as HTMLInputElement;
    const files = Array.from(input.files ?? []).slice(0, 2);
    comparisonError = "";
    if (files.length < 2) {
      comparisonReports = [];
      comparisonError = "Select two exported report JSON files.";
      input.value = "";
      return;
    }

    try {
      comparisonReports = await Promise.all(
        files.map(async (file) =>
          parseAcousticReportPayload(JSON.parse(await file.text())),
        ),
      );
    } catch (errorValue) {
      comparisonReports = [];
      comparisonError =
        errorValue instanceof Error ? errorValue.message : String(errorValue);
    } finally {
      input.value = "";
    }
  }

  function clearComparisonReports(): void {
    comparisonReports = [];
    comparisonError = "";
  }

  $: expectedSeconds =
    (config.pre_roll_ms + config.duration_ms + config.post_roll_ms) / 1000;
  $: topPeak = result?.dsp.dominant_peaks[0] ?? null;
  $: activeSpectrogram =
    signalView === "mel"
      ? (result?.dsp.mel_spectrogram ?? null)
      : (result?.dsp.stft ?? null);
  $: validation = result ? buildDeviceValidation(result) : null;
  $: dominantPeakNote = topPeak ? highQNote(topPeak.q_factor) : "";
  $: reportComparison =
    comparisonReports.length >= 2
      ? compareAcousticReports(comparisonReports[0], comparisonReports[1])
      : null;

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
    const q = peak.q_factor === null ? "" : `, ${formatQ(peak.q_factor)}`;
    return `${formatHz(peak.frequency_hz)}${q}`;
  }

  function formatQ(qFactor: number): string {
    if (qFactor > VERY_HIGH_Q_THRESHOLD) {
      return `Q >${VERY_HIGH_Q_THRESHOLD}`;
    }
    return `Q ${qFactor.toFixed(1)}`;
  }

  function highQNote(qFactor: number | null): string {
    if (qFactor === null || qFactor <= VERY_HIGH_Q_THRESHOLD) {
      return "";
    }
    return "Very narrow dominant peak; treat the Q proxy as device- and tonal-artifact-sensitive.";
  }

  function formatValidation(summary: DeviceValidationSummary | null): string {
    if (!summary) {
      return "--";
    }
    return `${summary.status.toUpperCase()} ${Math.round(summary.score * 100)}%`;
  }

  function validationTone(status: ValidationStatus): string {
    if (status === "pass") {
      return "Pass";
    }
    if (status === "review") {
      return "Review";
    }
    return "Fail";
  }

  function shortId(report: AcousticReport): string {
    return report.analysis_id.slice(0, 8);
  }
</script>

<main class="main">
  <section class="hero-row" aria-label="Acoustic probe workflow">
    <div class="panel panel--controls">
      <div class="panel-header">
        <h1 class="panel-title">Room Acoustic Fingerprint</h1>
        <p class="panel-subtitle">
          Chirp capture, impulse-envelope features, spectrograms, decay, and room-mode descriptors.
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

    <div class="panel panel--results">
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
          <div class="metric">
            <span>Run quality</span>
            <strong>{formatValidation(validation)}</strong>
          </div>
        </div>

        {#if result}
          <div class="report-block" aria-label="Acoustic report export">
            <div class="section-heading">
              <h2>Report</h2>
              <span>{formatValidation(validation)}</span>
            </div>
            <div class="actions">
              <button
                class="secondary-button"
                type="button"
                disabled={exportingReport}
                on:click={() => exportCurrentReport("json")}
              >
                {exportingReport ? "Exporting" : "Export JSON"}
              </button>
              <button
                class="secondary-button"
                type="button"
                disabled={exportingReport}
                on:click={() => exportCurrentReport("png")}
              >
                {exportingReport ? "Exporting" : "Export PNG"}
              </button>
            </div>
            {#if reportError}
              <div class="error" role="alert">{reportError}</div>
            {/if}

            <div class="comparison-block" aria-label="Report comparison">
              <div class="section-heading">
                <h2>Compare reports</h2>
                <span>
                  {comparisonReports.length === 2
                    ? `${shortId(comparisonReports[0])} / ${shortId(comparisonReports[1])}`
                    : "JSON"}
                </span>
              </div>
              <div class="actions">
                <label class="file-button">
                  Import JSON
                  <input
                    type="file"
                    accept="application/json,.json"
                    multiple
                    on:change={importComparisonReports}
                  />
                </label>
                {#if comparisonReports.length}
                  <button
                    class="secondary-button"
                    type="button"
                    on:click={clearComparisonReports}
                  >
                    Clear
                  </button>
                {/if}
              </div>
              {#if comparisonError}
                <div class="error" role="alert">{comparisonError}</div>
              {/if}
              {#if reportComparison}
                <div class="comparison-grid">
                  {#each reportComparison.metrics as metric}
                    <div class="comparison-row">
                      <span>{metric.label}</span>
                      <strong>{metric.first}</strong>
                      <strong>{metric.second}</strong>
                      <em>{metric.delta}</em>
                    </div>
                  {/each}
                </div>
                {#if reportComparison.transfer_bands.length}
                  <div class="comparison-transfer">
                    {#each reportComparison.transfer_bands as band}
                      <div class="comparison-row">
                        <span>{band.label}</span>
                        <strong>{band.first}</strong>
                        <strong>{band.second}</strong>
                        <em>{band.delta}</em>
                      </div>
                    {/each}
                  </div>
                {/if}
                {#if reportComparison.caveats.length}
                  <ul class="notice-list" aria-label="Comparison caveats">
                    {#each reportComparison.caveats as caveat}
                      <li>{caveat}</li>
                    {/each}
                  </ul>
                {/if}
              {/if}
            </div>
          </div>

          {#if validation}
            <div class="validation-grid" aria-label="Device validation">
              {#each validation.checks as check}
                <div
                  class="validation-row"
                  class:validation-pass={check.status === "pass"}
                  class:validation-review={check.status === "review"}
                  class:validation-fail={check.status === "fail"}
                >
                  <div>
                    <span>{check.label}</span>
                    <strong>{check.value}</strong>
                  </div>
                  <em>{validationTone(check.status)}</em>
                </div>
              {/each}
            </div>
          {/if}

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

          {#if result.dsp.decay_bands.length}
            <div class="section-heading">
              <h2>Decay bands</h2>
              <span>RT60 proxies</span>
            </div>
            <div class="transfer-list" aria-label="Decay bands">
              {#each result.dsp.decay_bands as band}
                <div class="transfer-row">
                  <span>{band.label} {formatHz(band.start_hz)}-{formatHz(band.end_hz)}</span>
                  <strong>{formatSeconds(band.rt60_seconds)}</strong>
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

        {#if dominantPeakNote}
          <ul class="notice-list" aria-label="Analysis notes">
            <li>{dominantPeakNote}</li>
          </ul>
        {/if}
      </div>
    </div>
  </section>
</main>
