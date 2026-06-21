import type {
  AnalysisResponse,
  LlmExplainResponse,
  SpectrogramGrid,
} from "$lib/audio/types";

export type ValidationStatus = "pass" | "review" | "fail";

export type ValidationCheck = {
  id: string;
  label: string;
  status: ValidationStatus;
  value: string;
  target: string;
  detail: string;
  required: boolean;
  weight: number;
};

export type DeviceValidationSummary = {
  status: ValidationStatus;
  score_model: string;
  score: number;
  required_score: number;
  advisory_score: number;
  checks: ValidationCheck[];
};

export type AcousticReportDescriptor = {
  room_character: string;
  brightness: string;
  dominant_mode: string;
  dominant_mode_hz: number | null;
  dominant_mode_q: number | null;
  dominant_mode_note: string | null;
};

export type AcousticReport = {
  schema_version: "resonancelab.acoustic_report.v1";
  generated_at: string;
  analysis_id: string;
  title: string;
  descriptors: AcousticReportDescriptor;
  validation: DeviceValidationSummary;
  method_notes: string[];
  analysis: AnalysisResponse;
  explanation: LlmExplainResponse["explanation"] | null;
  caveats: string[];
};

export type AcousticReportComparisonMetric = {
  id: string;
  label: string;
  first: string;
  second: string;
  delta: string;
};

export type TransferBandComparison = {
  label: string;
  first: string;
  second: string;
  delta: string;
};

export type AcousticReportComparison = {
  first_id: string;
  second_id: string;
  same_capture_condition: boolean;
  metrics: AcousticReportComparisonMetric[];
  transfer_bands: TransferBandComparison[];
  caveats: string[];
};

const EXPORT_WIDTH = 1600;
const EXPORT_HEIGHT = 1380;
const MISSING = "--";
const VERY_HIGH_Q_THRESHOLD = 300;
const REQUIRED_CHECK_WEIGHT = 2;
const ADVISORY_CHECK_WEIGHT = 1;

export function buildAcousticReport(
  analysis: AnalysisResponse,
  explanation?: LlmExplainResponse | null,
  generatedAt = new Date(),
): AcousticReport {
  return {
    schema_version: "resonancelab.acoustic_report.v1",
    generated_at: generatedAt.toISOString(),
    analysis_id: analysis.analysis_id,
    title: "ResonanceLab Room Acoustic Fingerprint",
    descriptors: buildDescriptors(analysis),
    validation: buildDeviceValidation(analysis),
    method_notes: buildMethodNotes(),
    analysis,
    explanation: explanation?.explanation ?? null,
    caveats: [
      "This report is an acoustic fingerprint, not a spatial reconstruction.",
      "Browser audio processing, device placement, playback volume, and room noise affect repeatability.",
      "Raw PCM data and WAV bytes are not included in this report export.",
      ...buildAnalysisCaveats(analysis),
    ],
  };
}

export function parseAcousticReportPayload(payload: unknown): AcousticReport {
  if (!isRecord(payload)) {
    throw new Error("Report JSON must contain an object.");
  }
  if (payload.schema_version !== "resonancelab.acoustic_report.v1") {
    throw new Error("Report JSON is not a ResonanceLab acoustic report.");
  }
  if (!isRecord(payload.analysis) || typeof payload.analysis_id !== "string") {
    throw new Error("Report JSON is missing analysis data.");
  }
  return payload as AcousticReport;
}

export function compareAcousticReports(
  first: AcousticReport,
  second: AcousticReport,
): AcousticReportComparison {
  const firstAnalysis = first.analysis;
  const secondAnalysis = second.analysis;
  const caveats = comparisonCaveats(first, second);
  return {
    first_id: first.analysis_id,
    second_id: second.analysis_id,
    same_capture_condition: caveats.length === 0,
    metrics: [
      comparisonMetric({
        id: "run_quality",
        label: "Run quality",
        first: first.validation.score,
        second: second.validation.score,
        formatter: (value) =>
          value === null || value === undefined
            ? MISSING
            : `${Math.round(value * 100)}%`,
        deltaFormatter: (value) => `${formatSigned(value * 100, 0)} pp`,
      }),
      comparisonMetric({
        id: "alignment",
        label: "Alignment",
        first: firstAnalysis.alignment.confidence,
        second: secondAnalysis.alignment.confidence,
        formatter: (value) =>
          value === null || value === undefined ? MISSING : value.toFixed(3),
      }),
      comparisonMetric({
        id: "snr",
        label: "SNR",
        first: firstAnalysis.dsp.signal_to_noise_db,
        second: secondAnalysis.dsp.signal_to_noise_db,
        formatter: formatDb,
        deltaFormatter: (value) => formatSigned(value, 1, " dB"),
      }),
      comparisonMetric({
        id: "rt60",
        label: "RT60 proxy",
        first: firstAnalysis.dsp.decay.rt60_seconds,
        second: secondAnalysis.dsp.decay.rt60_seconds,
        formatter: formatSeconds,
        deltaFormatter: (value) => formatSigned(value, 3, " s"),
      }),
      comparisonMetric({
        id: "centroid",
        label: "Centroid",
        first: firstAnalysis.dsp.fft.centroid_hz,
        second: secondAnalysis.dsp.fft.centroid_hz,
        formatter: formatHz,
        deltaFormatter: (value) => formatSigned(value, 0, " Hz"),
      }),
      comparisonMetric({
        id: "dominant_mode",
        label: "Dominant mode",
        first: first.descriptors.dominant_mode_hz,
        second: second.descriptors.dominant_mode_hz,
        formatter: formatHz,
        deltaFormatter: (value) => formatSigned(value, 0, " Hz"),
      }),
    ],
    transfer_bands: compareTransferBands(firstAnalysis, secondAnalysis),
    caveats,
  };
}

export function buildDeviceValidation(
  analysis: AnalysisResponse,
): DeviceValidationSummary {
  const settings = analysis.probe.browser.media_track_settings as Record<
    string,
    unknown
  >;
  const expectedDurationSeconds =
    (analysis.probe.probe_config.pre_roll_ms +
      analysis.probe.probe_config.duration_ms +
      analysis.probe.probe_config.post_roll_ms) /
    1000;
  const processingFlags = [
    "echoCancellation",
    "noiseSuppression",
    "autoGainControl",
  ].filter((key) => settings[key] === true);

  const checks: ValidationCheck[] = [
    statusAtLeast({
      id: "alignment_confidence",
      label: "Alignment",
      value: analysis.alignment.confidence,
      passAt: 0.5,
      reviewAt: 0.2,
      unit: "",
      precision: 3,
      target: ">= 0.50 preferred, >= 0.20 usable",
      required: true,
    }),
    statusAtLeast({
      id: "snr_db",
      label: "SNR",
      value: analysis.dsp.signal_to_noise_db,
      passAt: 18,
      reviewAt: 12,
      unit: " dB",
      precision: 1,
      target: ">= 18 dB preferred, >= 12 dB usable",
      required: true,
    }),
    durationCheck(analysis.audio.duration_seconds, expectedDurationSeconds),
    sampleRateCheck(analysis.audio.sample_rate_hz),
    peakAmplitudeCheck(analysis.audio.peak_amplitude),
    capturePathCheck(analysis.probe.browser.capture_path),
    browserProcessingCheck(processingFlags),
    decayFitCheck(analysis.dsp.decay.fit_r2, analysis.dsp.decay.rt60_seconds),
  ];

  const requiredFailure = checks.some(
    (check) => check.required && check.status === "fail",
  );
  const needsReview = checks.some((check) => check.status !== "pass");
  const requiredChecks = checks.filter((check) => check.required);
  const advisoryChecks = checks.filter((check) => !check.required);
  const score = weightedScore(checks);

  return {
    status: requiredFailure ? "fail" : needsReview ? "review" : "pass",
    score_model:
      "pass=1, review=0.5, fail=0; required checks carry double advisory weight",
    score: round(score, 3),
    required_score: round(unweightedScore(requiredChecks), 3),
    advisory_score: round(unweightedScore(advisoryChecks), 3),
    checks,
  };
}

export function buildDescriptors(
  analysis: AnalysisResponse,
): AcousticReportDescriptor {
  const topPeak = analysis.dsp.dominant_peaks[0] ?? null;
  return {
    room_character: roomCharacter(analysis.dsp.decay.rt60_seconds),
    brightness: brightness(analysis.dsp.fft.centroid_hz),
    dominant_mode: topPeak
      ? `${formatHz(topPeak.frequency_hz)}${topPeak.q_factor === null ? "" : `, ${formatQ(topPeak.q_factor)}`}`
      : MISSING,
    dominant_mode_hz: topPeak?.frequency_hz ?? null,
    dominant_mode_q: topPeak?.q_factor ?? null,
    dominant_mode_note: topPeak ? highQNote(topPeak.q_factor) : null,
  };
}

export function acousticReportFilename(
  report: AcousticReport,
  extension: "json" | "png",
): string {
  const stamp = report.generated_at.replace(/[:.]/g, "-");
  const id = report.analysis_id.slice(0, 8);
  return `resonancelab-${id}-${stamp}.${extension}`;
}

export function downloadAcousticReportJson(report: AcousticReport): void {
  const blob = new Blob([JSON.stringify(report, null, 2)], {
    type: "application/json",
  });
  downloadBlob(blob, acousticReportFilename(report, "json"));
}

export async function downloadAcousticReportPng(
  report: AcousticReport,
): Promise<void> {
  const blob = await renderAcousticReportPng(report);
  downloadBlob(blob, acousticReportFilename(report, "png"));
}

export async function renderAcousticReportPng(
  report: AcousticReport,
): Promise<Blob> {
  if (typeof document === "undefined") {
    throw new Error("PNG export requires a browser document.");
  }
  const scale = Math.max(1, Math.min(2, globalThis.devicePixelRatio || 1));
  const canvas = document.createElement("canvas");
  canvas.width = EXPORT_WIDTH * scale;
  canvas.height = EXPORT_HEIGHT * scale;
  const context = canvas.getContext("2d");
  if (!context) {
    throw new Error("Could not create a canvas rendering context.");
  }
  context.scale(scale, scale);
  drawReport(context, report);
  return canvasToBlob(canvas);
}

function drawReport(
  context: CanvasRenderingContext2D,
  report: AcousticReport,
): void {
  context.fillStyle = "#101614";
  context.fillRect(0, 0, EXPORT_WIDTH, EXPORT_HEIGHT);

  context.fillStyle = "#e7f0ea";
  context.font = "700 34px Inter, Segoe UI, sans-serif";
  context.fillText(report.title, 48, 62);
  context.font = "500 16px Inter, Segoe UI, sans-serif";
  context.fillStyle = "#9fb0aa";
  context.fillText(`Analysis ${report.analysis_id}`, 48, 92);
  context.fillText(new Date(report.generated_at).toLocaleString(), 48, 116);
  context.fillText(reportMetadataLine(report), 430, 116);

  const statusColor = statusColorFor(report.validation.status);
  roundedRect(context, 1250, 42, 300, 84, 8, "#151c1a", "#32423d");
  context.fillStyle = statusColor;
  context.font = "800 28px Inter, Segoe UI, sans-serif";
  context.fillText(report.validation.status.toUpperCase(), 1274, 82);
  context.fillStyle = "#9fb0aa";
  context.font = "600 15px Inter, Segoe UI, sans-serif";
  context.fillText(
    `Run quality ${Math.round(report.validation.score * 100)}%`,
    1274,
    108,
  );

  drawMetricCards(context, report);
  drawSpectrogramPanel(context, report);
  drawImpulseResponsePanel(context, report);
  drawTransferPanel(context, report);
  drawDecayBandsPanel(context, report);
  drawPeaksPanel(context, report);
  drawValidationPanel(context, report);
  drawCaveatsPanel(context, report);
  drawFooter(context);
}

function drawMetricCards(
  context: CanvasRenderingContext2D,
  report: AcousticReport,
): void {
  const metrics = [
    ["Room character", report.descriptors.room_character],
    ["Brightness", report.descriptors.brightness],
    ["Dominant mode", report.descriptors.dominant_mode],
    ["RT60 proxy", formatSeconds(report.analysis.dsp.decay.rt60_seconds)],
    ["Alignment", report.analysis.alignment.confidence.toFixed(3)],
    ["SNR", formatDb(report.analysis.dsp.signal_to_noise_db)],
    ["Centroid", formatHz(report.analysis.dsp.fft.centroid_hz)],
    ["Rolloff", formatHz(report.analysis.dsp.fft.rolloff_hz)],
  ];
  const x = 48;
  const y = 154;
  const width = 356;
  const height = 86;
  const gap = 16;
  metrics.forEach(([label, value], index) => {
    const column = index % 4;
    const row = Math.floor(index / 4);
    const cardX = x + column * (width + gap);
    const cardY = y + row * (height + gap);
    roundedRect(context, cardX, cardY, width, height, 8, "#1d2724", "#32423d");
    context.fillStyle = "#9fb0aa";
    context.font = "600 14px Inter, Segoe UI, sans-serif";
    context.fillText(label, cardX + 18, cardY + 29);
    context.fillStyle = "#e7f0ea";
    context.font = "800 25px Inter, Segoe UI, sans-serif";
    drawWrappedText(context, value, cardX + 18, cardY + 61, width - 36, 26, 1);
  });
}

function drawSpectrogramPanel(
  context: CanvasRenderingContext2D,
  report: AcousticReport,
): void {
  const panel = { x: 48, y: 360, width: 920, height: 360 };
  roundedRect(
    context,
    panel.x,
    panel.y,
    panel.width,
    panel.height,
    8,
    "#151c1a",
    "#32423d",
  );
  drawPanelTitle(context, "Acoustic image", panel.x, panel.y);

  const grid = report.analysis.dsp.mel_spectrogram;
  drawSpectrogram(
    context,
    grid,
    panel.x + 24,
    panel.y + 64,
    panel.width - 48,
    panel.height - 104,
  );
}

function drawImpulseResponsePanel(
  context: CanvasRenderingContext2D,
  report: AcousticReport,
): void {
  const panel = { x: 48, y: 744, width: 920, height: 170 };
  roundedRect(
    context,
    panel.x,
    panel.y,
    panel.width,
    panel.height,
    8,
    "#151c1a",
    "#32423d",
  );
  drawPanelTitle(context, "Impulse envelope", panel.x, panel.y);

  const trace = report.analysis.dsp.impulse_response;
  if (!trace?.times_seconds?.length || !trace.magnitude_db.length) {
    drawEmpty(
      context,
      "No impulse envelope available.",
      panel.x + 24,
      panel.y + 74,
    );
    return;
  }

  drawLineTrace(
    context,
    trace.times_seconds,
    trace.magnitude_db,
    panel.x + 24,
    panel.y + 64,
    panel.width - 48,
    panel.height - 104,
    { minY: -96, maxY: 0, stroke: "#58b9d1" },
  );
  context.fillStyle = "#9fb0aa";
  context.font = "600 12px Inter, Segoe UI, sans-serif";
  context.fillText("0 dB", panel.x + 24, panel.y + 58);
  context.fillText("-96 dB", panel.x + 24, panel.y + panel.height - 22);
  context.textAlign = "right";
  context.fillText(
    `${Math.round((trace.times_seconds.at(-1) ?? 0) * 1000)} ms`,
    panel.x + panel.width - 24,
    panel.y + panel.height - 22,
  );
  context.textAlign = "left";
}

function drawTransferPanel(
  context: CanvasRenderingContext2D,
  report: AcousticReport,
): void {
  const panel = { x: 1000, y: 360, width: 552, height: 250 };
  roundedRect(
    context,
    panel.x,
    panel.y,
    panel.width,
    panel.height,
    8,
    "#151c1a",
    "#32423d",
  );
  drawPanelTitle(context, "Transfer bands", panel.x, panel.y);

  const bands = report.analysis.dsp.transfer_response.slice(0, 8);
  if (!bands.length) {
    drawEmpty(
      context,
      "No transfer bands available.",
      panel.x + 24,
      panel.y + 74,
    );
    return;
  }
  const values = bands.map((band) => band.mean_db);
  const min = Math.min(...values);
  const max = Math.max(...values);
  bands.forEach((band, index) => {
    const y = panel.y + 66 + index * 23;
    const normalized = normalize(band.mean_db, min, max);
    context.fillStyle = "#9fb0aa";
    context.font = "600 13px Inter, Segoe UI, sans-serif";
    context.fillText(
      `${formatHz(band.start_hz)}-${formatHz(band.end_hz)}`,
      panel.x + 24,
      y,
    );
    roundedRect(context, panel.x + 190, y - 12, 220, 10, 5, "#24312d");
    roundedRect(
      context,
      panel.x + 190,
      y - 12,
      Math.max(4, normalized * 220),
      10,
      5,
      "#49d195",
    );
    context.fillStyle = "#e7f0ea";
    context.textAlign = "right";
    context.fillText(formatDb(band.mean_db), panel.x + panel.width - 24, y);
    context.textAlign = "left";
  });
}

function drawDecayBandsPanel(
  context: CanvasRenderingContext2D,
  report: AcousticReport,
): void {
  const panel = { x: 1000, y: 636, width: 552, height: 170 };
  roundedRect(
    context,
    panel.x,
    panel.y,
    panel.width,
    panel.height,
    8,
    "#151c1a",
    "#32423d",
  );
  drawPanelTitle(context, "Decay bands", panel.x, panel.y);

  const bands = report.analysis.dsp.decay_bands ?? [];
  if (!bands.length) {
    drawEmpty(context, "No band-limited decay available.", panel.x + 24, panel.y + 74);
    return;
  }
  const rt60Values = bands
    .map((band) => band.rt60_seconds)
    .filter((value): value is number => value !== null && Number.isFinite(value));
  const maxRt60 = Math.max(...rt60Values, 0.1);
  bands.forEach((band, index) => {
    const y = panel.y + 70 + index * 32;
    const rt60 = band.rt60_seconds;
    const normalized = rt60 === null ? 0 : Math.max(0.04, Math.min(1, rt60 / maxRt60));
    context.fillStyle = "#9fb0aa";
    context.font = "700 13px Inter, Segoe UI, sans-serif";
    context.fillText(
      `${band.label.toUpperCase()} ${formatHz(band.start_hz)}-${formatHz(band.end_hz)}`,
      panel.x + 24,
      y,
    );
    roundedRect(context, panel.x + 214, y - 13, 210, 11, 6, "#24312d");
    if (rt60 !== null) {
      roundedRect(
        context,
        panel.x + 214,
        y - 13,
        normalized * 210,
        11,
        6,
        "#58b9d1",
      );
    }
    context.fillStyle = "#e7f0ea";
    context.textAlign = "right";
    context.fillText(formatSeconds(rt60), panel.x + panel.width - 24, y);
    context.textAlign = "left";
  });
}

function drawPeaksPanel(
  context: CanvasRenderingContext2D,
  report: AcousticReport,
): void {
  const panel = { x: 1000, y: 832, width: 552, height: 214 };
  roundedRect(
    context,
    panel.x,
    panel.y,
    panel.width,
    panel.height,
    8,
    "#151c1a",
    "#32423d",
  );
  drawPanelTitle(context, "Dominant modes", panel.x, panel.y);

  const peaks = report.analysis.dsp.dominant_peaks.slice(0, 5);
  if (!peaks.length) {
    drawEmpty(
      context,
      "No dominant peaks cleared the threshold.",
      panel.x + 24,
      panel.y + 74,
    );
    return;
  }
  peaks.forEach((peak, index) => {
    const y = panel.y + 68 + index * 28;
    context.fillStyle = "#e7f0ea";
    context.font = "800 17px Inter, Segoe UI, sans-serif";
    context.fillText(formatHz(peak.frequency_hz), panel.x + 24, y);
    context.fillStyle = "#9fb0aa";
    context.font = "600 13px Inter, Segoe UI, sans-serif";
    context.fillText(
      `${formatDb(peak.prominence_db)} prominence`,
      panel.x + 180,
      y,
    );
    context.textAlign = "right";
    context.fillText(
      peak.q_factor === null ? "Q --" : formatQ(peak.q_factor),
      panel.x + panel.width - 24,
      y,
    );
    context.textAlign = "left";
  });
}

function drawValidationPanel(
  context: CanvasRenderingContext2D,
  report: AcousticReport,
): void {
  const panel = { x: 48, y: 938, width: 920, height: 330 };
  roundedRect(
    context,
    panel.x,
    panel.y,
    panel.width,
    panel.height,
    8,
    "#151c1a",
    "#32423d",
  );
  drawPanelTitle(context, "Device validation", panel.x, panel.y);

  report.validation.checks.forEach((check, index) => {
    const column = index % 2;
    const row = Math.floor(index / 2);
    const x = panel.x + 24 + column * 438;
    const y = panel.y + 68 + row * 52;
    context.fillStyle = statusColorFor(check.status);
    context.beginPath();
    context.arc(x + 8, y - 7, 6, 0, Math.PI * 2);
    context.fill();
    context.fillStyle = "#e7f0ea";
    context.font = "800 15px Inter, Segoe UI, sans-serif";
    context.fillText(check.label, x + 24, y);
    context.fillStyle = "#9fb0aa";
    context.font = "600 13px Inter, Segoe UI, sans-serif";
    drawWrappedText(
      context,
      `${check.value} | ${check.target}`,
      x + 24,
      y + 21,
      390,
      17,
      1,
    );
  });
}

function drawCaveatsPanel(
  context: CanvasRenderingContext2D,
  report: AcousticReport,
): void {
  const panel = { x: 1000, y: 1072, width: 552, height: 236 };
  roundedRect(
    context,
    panel.x,
    panel.y,
    panel.width,
    panel.height,
    8,
    "#151c1a",
    "#32423d",
  );
  drawPanelTitle(context, "Caveats", panel.x, panel.y);
  const caveats = [...report.caveats, ...report.analysis.warnings].slice(0, 6);
  let y = panel.y + 68;
  caveats.forEach((caveat) => {
    context.fillStyle = "#9fb0aa";
    context.font = "600 13px Inter, Segoe UI, sans-serif";
    y =
      drawWrappedText(
        context,
        caveat,
        panel.x + 24,
        y,
        panel.width - 48,
        18,
        2,
      ) + 8;
  });
}

function drawSpectrogram(
  context: CanvasRenderingContext2D,
  grid: SpectrogramGrid,
  x: number,
  y: number,
  width: number,
  height: number,
): void {
  if (!grid.magnitude_db.length || !grid.times_seconds.length) {
    drawEmpty(context, "No spectrogram available.", x, y + 28);
    return;
  }
  const values = grid.magnitude_db
    .flat()
    .filter((value) => Number.isFinite(value));
  const min = percentile(values, 0.05);
  const max = percentile(values, 0.98);
  const rows = grid.magnitude_db.length;
  const columns = grid.times_seconds.length;
  const cellWidth = width / columns;
  const cellHeight = height / rows;
  for (let row = 0; row < rows; row += 1) {
    const visualRow = rows - row - 1;
    for (let column = 0; column < columns; column += 1) {
      const value = grid.magnitude_db[row]?.[column] ?? min;
      context.fillStyle = heatColor(normalize(value, min, max));
      context.fillRect(
        x + column * cellWidth,
        y + visualRow * cellHeight,
        Math.ceil(cellWidth) + 0.5,
        Math.ceil(cellHeight) + 0.5,
      );
    }
  }
  context.strokeStyle = "#32423d";
  context.strokeRect(x, y, width, height);
  context.fillStyle = "#9fb0aa";
  context.font = "600 12px Inter, Segoe UI, sans-serif";
  context.fillText(formatHz(grid.frequency_bins_hz.at(-1)), x, y - 10);
  context.fillText(formatSeconds(grid.times_seconds[0]), x, y + height + 20);
  context.textAlign = "right";
  context.fillText(
    formatSeconds(grid.times_seconds.at(-1)),
    x + width,
    y + height + 20,
  );
  context.textAlign = "left";
}

function drawLineTrace(
  context: CanvasRenderingContext2D,
  xValues: number[],
  yValues: number[],
  x: number,
  y: number,
  width: number,
  height: number,
  options: { minY: number; maxY: number; stroke: string },
): void {
  const finitePairs = xValues
    .map((xValue, index) => ({ xValue, yValue: yValues[index] }))
    .filter(
      (pair) => Number.isFinite(pair.xValue) && Number.isFinite(pair.yValue),
    );
  if (finitePairs.length < 2) {
    drawEmpty(context, "Trace is too short to draw.", x, y + 28);
    return;
  }

  const minX = finitePairs[0].xValue;
  const maxX = finitePairs.at(-1)?.xValue ?? minX;
  if (maxX <= minX || options.maxY <= options.minY) {
    drawEmpty(context, "Trace range is not drawable.", x, y + 28);
    return;
  }

  context.strokeStyle = "#24312d";
  context.lineWidth = 1;
  for (let tick = 0; tick <= 4; tick += 1) {
    const tickY = y + (tick / 4) * height;
    context.beginPath();
    context.moveTo(x, tickY);
    context.lineTo(x + width, tickY);
    context.stroke();
  }

  context.strokeStyle = options.stroke;
  context.lineWidth = 2;
  context.beginPath();
  finitePairs.forEach((pair, index) => {
    const pointX = x + normalize(pair.xValue, minX, maxX) * width;
    const pointY =
      y +
      (1 - normalize(pair.yValue, options.minY, options.maxY)) * height;
    if (index === 0) {
      context.moveTo(pointX, pointY);
    } else {
      context.lineTo(pointX, pointY);
    }
  });
  context.stroke();
  context.strokeStyle = "#32423d";
  context.strokeRect(x, y, width, height);
}

function drawFooter(context: CanvasRenderingContext2D): void {
  context.fillStyle = "#9fb0aa";
  context.font = "600 12px Inter, Segoe UI, sans-serif";
  context.fillText(
    "Single speaker/microphone captures are acoustic fingerprints, not room geometry or spatial reconstructions.",
    48,
    EXPORT_HEIGHT - 34,
  );
}

function reportMetadataLine(report: AcousticReport): string {
  const config = report.analysis.probe.probe_config;
  return [
    `${report.analysis.audio.sample_rate_hz} Hz`,
    report.analysis.probe.browser.capture_path,
    `${formatHz(config.start_hz)}-${formatHz(config.end_hz)}`,
    `${config.duration_ms} ms chirp`,
  ].join(" | ");
}

function comparisonMetric({
  id,
  label,
  first,
  second,
  formatter,
  deltaFormatter,
}: {
  id: string;
  label: string;
  first: number | null;
  second: number | null;
  formatter: (value: number | null | undefined) => string;
  deltaFormatter?: (delta: number) => string;
}): AcousticReportComparisonMetric {
  const delta =
    first === null ||
    second === null ||
    !Number.isFinite(first) ||
    !Number.isFinite(second)
      ? null
      : second - first;
  return {
    id,
    label,
    first: formatter(first),
    second: formatter(second),
    delta: delta === null ? MISSING : (deltaFormatter ?? formatSigned)(delta),
  };
}

function compareTransferBands(
  first: AnalysisResponse,
  second: AnalysisResponse,
): TransferBandComparison[] {
  const secondBands = new Map(
    second.dsp.transfer_response.map((band) => [transferBandKey(band), band]),
  );
  return first.dsp.transfer_response
    .map((firstBand) => {
      const secondBand = secondBands.get(transferBandKey(firstBand));
      if (!secondBand) {
        return null;
      }
      return {
        label: `${formatHz(firstBand.start_hz)}-${formatHz(firstBand.end_hz)}`,
        first: formatDb(firstBand.mean_db),
        second: formatDb(secondBand.mean_db),
        delta: formatSigned(secondBand.mean_db - firstBand.mean_db, 1, " dB"),
      };
    })
    .filter((value): value is TransferBandComparison => value !== null);
}

function transferBandKey(band: {
  start_hz: number;
  end_hz: number;
}): string {
  return `${Math.round(band.start_hz)}-${Math.round(band.end_hz)}`;
}

function comparisonCaveats(
  first: AcousticReport,
  second: AcousticReport,
): string[] {
  const caveats: string[] = [];
  const firstProbe = first.analysis.probe;
  const secondProbe = second.analysis.probe;
  if (
    first.analysis.audio.sample_rate_hz !== second.analysis.audio.sample_rate_hz
  ) {
    caveats.push("Sample rates differ; compare spectral and decay values cautiously.");
  }
  if (firstProbe.browser.capture_path !== secondProbe.browser.capture_path) {
    caveats.push("Capture paths differ; AudioWorklet and fallback paths can shape results.");
  }
  if (
    firstProbe.browser.user_agent &&
    secondProbe.browser.user_agent &&
    firstProbe.browser.user_agent !== secondProbe.browser.user_agent
  ) {
    caveats.push("Browser or device user-agent strings differ.");
  }
  const firstConfig = JSON.stringify(firstProbe.probe_config);
  const secondConfig = JSON.stringify(secondProbe.probe_config);
  if (firstConfig !== secondConfig) {
    caveats.push("Probe configuration differs; repeatability comparisons need matching chirps.");
  }
  return caveats;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function statusAtLeast({
  id,
  label,
  value,
  passAt,
  reviewAt,
  unit,
  precision,
  target,
  required,
}: {
  id: string;
  label: string;
  value: number | null;
  passAt: number;
  reviewAt: number;
  unit: string;
  precision: number;
  target: string;
  required: boolean;
}): ValidationCheck {
  if (value === null || !Number.isFinite(value)) {
    return {
      id,
      label,
      status: "fail",
      value: MISSING,
      target,
      detail: `${label} was not available.`,
      required,
      weight: checkWeight(required),
    };
  }
  const status =
    value >= passAt ? "pass" : value >= reviewAt ? "review" : "fail";
  return {
    id,
    label,
    status,
    value: `${value.toFixed(precision)}${unit}`,
    target,
    detail: `${label} measured ${value.toFixed(precision)}${unit}.`,
    required,
    weight: checkWeight(required),
  };
}

function durationCheck(
  actualSeconds: number,
  expectedSeconds: number,
): ValidationCheck {
  const ratio = expectedSeconds > 0 ? actualSeconds / expectedSeconds : 0;
  const status =
    ratio >= 0.9 && ratio <= 1.15
      ? "pass"
      : ratio >= 0.75 && ratio <= 1.5
        ? "review"
        : "fail";
  return {
    id: "duration",
    label: "Duration",
    status,
    value: formatSeconds(actualSeconds),
    target: `${formatSeconds(expectedSeconds)} expected`,
    detail: `Capture duration ratio is ${ratio.toFixed(2)}.`,
    required: true,
    weight: checkWeight(true),
  };
}

function sampleRateCheck(sampleRateHz: number): ValidationCheck {
  const status =
    sampleRateHz >= 44100 ? "pass" : sampleRateHz >= 16000 ? "review" : "fail";
  return {
    id: "sample_rate",
    label: "Sample rate",
    status,
    value: `${sampleRateHz} Hz`,
    target: ">= 44.1 kHz preferred",
    detail: "Native browser sample rate is preserved.",
    required: true,
    weight: checkWeight(true),
  };
}

function peakAmplitudeCheck(peakAmplitude: number): ValidationCheck {
  const status =
    peakAmplitude >= 0.02 && peakAmplitude <= 0.95
      ? "pass"
      : peakAmplitude > 0.995 || peakAmplitude < 0.005
        ? "fail"
        : "review";
  return {
    id: "peak_amplitude",
    label: "Peak amplitude",
    status,
    value: peakAmplitude.toFixed(3),
    target: "0.02 to 0.95",
    detail: "Avoid silent captures and clipped recordings.",
    required: true,
    weight: checkWeight(true),
  };
}

function capturePathCheck(capturePath: string): ValidationCheck {
  const status =
    capturePath === "audio_worklet"
      ? "pass"
      : capturePath === "script_processor"
        ? "review"
        : "fail";
  return {
    id: "capture_path",
    label: "Capture path",
    status,
    value: capturePath,
    target: "audio_worklet preferred",
    detail: "AudioWorklet gives the most predictable PCM capture path.",
    required: false,
    weight: checkWeight(false),
  };
}

function browserProcessingCheck(processingFlags: string[]): ValidationCheck {
  return {
    id: "browser_processing",
    label: "Processing",
    status: processingFlags.length ? "review" : "pass",
    value: processingFlags.length ? processingFlags.join(", ") : "off",
    target: "echo/AGC/noise processing off",
    detail: "Browser-forced processing can reshape acoustic fingerprints.",
    required: false,
    weight: checkWeight(false),
  };
}

function decayFitCheck(
  fitR2: number | null,
  rt60Seconds: number | null,
): ValidationCheck {
  const hasRt60 = rt60Seconds !== null && Number.isFinite(rt60Seconds);
  const status =
    hasRt60 && fitR2 !== null && fitR2 >= 0.55
      ? "pass"
      : hasRt60 || fitR2 !== null
        ? "review"
        : "fail";
  return {
    id: "decay_fit",
    label: "Decay fit",
    status,
    value: fitR2 === null ? MISSING : fitR2.toFixed(3),
    target: "RT60 with fit >= 0.55 preferred",
    detail:
      "Decay quality is diagnostic and should not be treated as room identity.",
    required: false,
    weight: checkWeight(false),
  };
}

function buildMethodNotes(): string[] {
  return [
    "Transfer-response bands are regularized driven-path summaries computed from the aligned chirp plus available ring-down; values are not calibrated room transfer functions.",
    "The impulse envelope is a compact, zero-padded regularized deconvolution envelope normalized for comparison, not a spatial room reconstruction.",
    "Low, mid, and high decay bands reuse the post-chirp window and should be compared only across controlled repeat captures.",
    "STFT and mel grids are compact UI/export visualizations, not high-resolution analysis arrays.",
    "Q factor is a half-power bandwidth proxy and can be inflated by narrow tonal, browser, or device artifacts.",
  ];
}

function buildAnalysisCaveats(analysis: AnalysisResponse): string[] {
  const topPeak = analysis.dsp.dominant_peaks[0] ?? null;
  const note = topPeak ? highQNote(topPeak.q_factor) : null;
  return note ? [note] : [];
}

function highQNote(qFactor: number | null): string | null {
  if (qFactor === null || qFactor <= VERY_HIGH_Q_THRESHOLD) {
    return null;
  }
  return (
    `Very narrow dominant peak (${formatQ(qFactor)}); treat the Q proxy as ` +
    "device- and tonal-artifact-sensitive rather than room-mode certainty."
  );
}

function formatQ(qFactor: number): string {
  if (qFactor > VERY_HIGH_Q_THRESHOLD) {
    return `Q >${VERY_HIGH_Q_THRESHOLD}`;
  }
  return `Q ${qFactor.toFixed(1)}`;
}

function checkWeight(required: boolean): number {
  return required ? REQUIRED_CHECK_WEIGHT : ADVISORY_CHECK_WEIGHT;
}

function weightedScore(checks: ValidationCheck[]): number {
  const totalWeight = checks.reduce((total, check) => total + check.weight, 0);
  if (totalWeight <= 0) {
    return 0;
  }
  return (
    checks.reduce(
      (total, check) => total + statusScore(check.status) * check.weight,
      0,
    ) / totalWeight
  );
}

function unweightedScore(checks: ValidationCheck[]): number {
  if (!checks.length) {
    return 0;
  }
  return (
    checks.reduce((total, check) => total + statusScore(check.status), 0) /
    checks.length
  );
}

function statusScore(status: ValidationStatus): number {
  if (status === "pass") {
    return 1;
  }
  if (status === "review") {
    return 0.5;
  }
  return 0;
}

function roomCharacter(rt60Seconds: number | null): string {
  if (rt60Seconds === null || !Number.isFinite(rt60Seconds)) {
    return MISSING;
  }
  if (rt60Seconds < 0.25) {
    return "Dry";
  }
  if (rt60Seconds > 0.75) {
    return "Live";
  }
  return "Balanced";
}

function brightness(centroidHz: number | null): string {
  if (centroidHz === null || !Number.isFinite(centroidHz)) {
    return MISSING;
  }
  if (centroidHz > 3500) {
    return "Bright";
  }
  if (centroidHz < 1200) {
    return "Dark";
  }
  return "Neutral";
}

function formatHz(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return MISSING;
  }
  if (value >= 1000) {
    return `${(value / 1000).toFixed(value >= 10000 ? 1 : 2)} kHz`;
  }
  return `${Math.round(value)} Hz`;
}

function formatDb(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return MISSING;
  }
  return `${value.toFixed(1)} dB`;
}

function formatSeconds(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return MISSING;
  }
  return `${value.toFixed(3)} s`;
}

function formatSigned(value: number, digits = 3, suffix = ""): string {
  if (!Number.isFinite(value)) {
    return MISSING;
  }
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}${suffix}`;
}

function round(value: number, digits: number): number {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

function normalize(value: number, min: number, max: number): number {
  if (
    !Number.isFinite(value) ||
    !Number.isFinite(min) ||
    !Number.isFinite(max) ||
    max <= min
  ) {
    return 0.5;
  }
  return Math.max(0, Math.min(1, (value - min) / (max - min)));
}

function percentile(values: number[], quantile: number): number {
  if (!values.length) {
    return 0;
  }
  const sorted = [...values].sort((a, b) => a - b);
  const index = Math.max(
    0,
    Math.min(sorted.length - 1, Math.round((sorted.length - 1) * quantile)),
  );
  return sorted[index];
}

function heatColor(value: number): string {
  const stops = [
    [8, 16, 18],
    [18, 74, 83],
    [31, 155, 127],
    [78, 209, 149],
    [240, 179, 90],
  ];
  const scaled = Math.max(0, Math.min(1, value)) * (stops.length - 1);
  const index = Math.min(stops.length - 2, Math.floor(scaled));
  const local = scaled - index;
  const from = stops[index];
  const to = stops[index + 1];
  const rgb = from.map((channel, channelIndex) =>
    Math.round(channel + (to[channelIndex] - channel) * local),
  );
  return `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`;
}

function roundedRect(
  context: CanvasRenderingContext2D,
  x: number,
  y: number,
  width: number,
  height: number,
  radius: number,
  fill: string,
  stroke?: string,
): void {
  context.beginPath();
  context.moveTo(x + radius, y);
  context.lineTo(x + width - radius, y);
  context.quadraticCurveTo(x + width, y, x + width, y + radius);
  context.lineTo(x + width, y + height - radius);
  context.quadraticCurveTo(
    x + width,
    y + height,
    x + width - radius,
    y + height,
  );
  context.lineTo(x + radius, y + height);
  context.quadraticCurveTo(x, y + height, x, y + height - radius);
  context.lineTo(x, y + radius);
  context.quadraticCurveTo(x, y, x + radius, y);
  context.closePath();
  context.fillStyle = fill;
  context.fill();
  if (stroke) {
    context.strokeStyle = stroke;
    context.lineWidth = 1;
    context.stroke();
  }
}

function drawPanelTitle(
  context: CanvasRenderingContext2D,
  title: string,
  x: number,
  y: number,
): void {
  context.fillStyle = "#e7f0ea";
  context.font = "800 20px Inter, Segoe UI, sans-serif";
  context.fillText(title, x + 24, y + 36);
}

function drawEmpty(
  context: CanvasRenderingContext2D,
  text: string,
  x: number,
  y: number,
): void {
  context.fillStyle = "#9fb0aa";
  context.font = "600 15px Inter, Segoe UI, sans-serif";
  context.fillText(text, x, y);
}

function drawWrappedText(
  context: CanvasRenderingContext2D,
  text: string,
  x: number,
  y: number,
  maxWidth: number,
  lineHeight: number,
  maxLines = 4,
): number {
  const wrapped = wrapTextForWidth(
    text,
    (value) => context.measureText(value).width,
    maxWidth,
    maxLines,
  );
  for (const line of wrapped.lines) {
    context.fillText(line, x, y);
    y += lineHeight;
  }
  return y;
}

export function wrapTextForWidth(
  text: string,
  measureWidth: (text: string) => number,
  maxWidth: number,
  maxLines: number,
): { lines: string[]; truncated: boolean } {
  const normalized = text.trim().replace(/\s+/g, " ");
  if (!normalized || maxLines <= 0 || maxWidth <= 0) {
    return { lines: [], truncated: Boolean(normalized) };
  }

  const words = normalized.split(" ");
  const lines: string[] = [];
  let line = "";
  for (let index = 0; index < words.length; index += 1) {
    const word = words[index];
    const testLine = line ? `${line} ${word}` : word;
    if (line && measureWidth(testLine) > maxWidth) {
      if (lines.length === maxLines - 1) {
        const remaining = [line, word, ...words.slice(index + 1)].join(" ");
        lines.push(ellipsizeText(remaining, measureWidth, maxWidth));
        return { lines, truncated: true };
      }
      lines.push(line);
      line = word;
    } else {
      line = testLine;
    }
  }

  if (line) {
    const truncated = measureWidth(line) > maxWidth;
    lines.push(truncated ? ellipsizeText(line, measureWidth, maxWidth) : line);
    return { lines, truncated };
  }

  return { lines, truncated: false };
}

function ellipsizeText(
  text: string,
  measureWidth: (text: string) => number,
  maxWidth: number,
): string {
  const ellipsis = "...";
  if (measureWidth(text) <= maxWidth) {
    return text;
  }
  if (measureWidth(ellipsis) > maxWidth) {
    return ellipsis;
  }
  let end = text.length;
  while (end > 0) {
    const candidate = `${text.slice(0, end).trimEnd()}${ellipsis}`;
    if (measureWidth(candidate) <= maxWidth) {
      return candidate;
    }
    end -= 1;
  }
  return ellipsis;
}

function statusColorFor(status: ValidationStatus): string {
  if (status === "pass") {
    return "#49d195";
  }
  if (status === "review") {
    return "#f0b35a";
  }
  return "#ff7d70";
}

function downloadBlob(blob: Blob, filename: string): void {
  if (typeof document === "undefined") {
    throw new Error("Report download requires a browser document.");
  }
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

function canvasToBlob(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (blob) {
        resolve(blob);
      } else {
        reject(new Error("Could not render acoustic report PNG."));
      }
    }, "image/png");
  });
}
