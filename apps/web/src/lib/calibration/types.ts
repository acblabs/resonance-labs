import type { AnalysisResponse, CapturePath, ProbeConfig } from '$lib/audio/types';

export type CalibrationAnchorKind = 'empty' | 'half' | 'full';
export type CalibrationReferenceKind = 'free_air';

export type CalibrationAnchorDefinition = {
  kind: CalibrationAnchorKind;
  label: string;
  fillPercent: number;
};

export type CalibrationFeatureUnit = 'log_hz' | 'db' | 'seconds' | 'ratio' | 'unitless';

export type CalibrationFeature = {
  name: string;
  label: string;
  value: number;
  unit: CalibrationFeatureUnit;
  scaleHint: number;
  weight: number;
};

export type CalibrationFeatureVector = {
  schemaVersion: 1;
  features: CalibrationFeature[];
  summary: {
    primaryPeakHz: number | null;
    spectralCentroidHz: number | null;
    spectralRolloffHz: number | null;
    decayRatePerSecond: number | null;
    rt60Seconds: number | null;
    transferBandCount: number;
  };
};

export type CalibrationQuality = {
  alignmentConfidence: number;
  signalToNoiseDb: number | null;
  warningCount: number;
};

export type CalibrationMediaProcessing = {
  echoCancellation: boolean | null;
  noiseSuppression: boolean | null;
  autoGainControl: boolean | null;
};

export type CalibrationCaptureSummary = {
  sampleRateHz: number;
  audioContextSampleRateHz: number | null;
  capturePath: CapturePath;
  mediaProcessing: CalibrationMediaProcessing;
  userAgent: string | null;
};

export type CalibrationObservation = {
  analysisId: string;
  recordedAt: string;
  savedAt: string;
  probeConfig: ProbeConfig;
  probeConfigSignature: string;
  captureSignature: string;
  capture: CalibrationCaptureSummary;
  featureVector: CalibrationFeatureVector;
  quality: CalibrationQuality;
  warnings: string[];
};

export type CalibrationStability = {
  repeated: boolean;
  featureStdMean: number | null;
  featureStdMax: number | null;
  primaryPeakStdHz: number | null;
};

export type CalibrationAnchor = {
  kind: CalibrationAnchorKind;
  label: string;
  fillPercent: number;
  sampleCount: number;
  observations: CalibrationObservation[];
  analysisId: string;
  recordedAt: string;
  savedAt: string;
  probeConfig: ProbeConfig;
  probeConfigSignature: string;
  captureSignature: string;
  capture: CalibrationCaptureSummary;
  featureVector: CalibrationFeatureVector;
  quality: CalibrationQuality;
  stability: CalibrationStability;
  warnings: string[];
};

export type CalibrationReference = {
  kind: CalibrationReferenceKind;
  label: string;
  sampleCount: number;
  observations: CalibrationObservation[];
  analysisId: string;
  recordedAt: string;
  savedAt: string;
  probeConfig: ProbeConfig;
  probeConfigSignature: string;
  captureSignature: string;
  capture: CalibrationCaptureSummary;
  featureVector: CalibrationFeatureVector;
  quality: CalibrationQuality;
  stability: CalibrationStability;
  warnings: string[];
};

export type KnownObjectReference = {
  kind: 'known_object';
  id: string;
  label: string;
  material: string;
  sampleCount: number;
  observations: CalibrationObservation[];
  analysisId: string;
  recordedAt: string;
  savedAt: string;
  probeConfig: ProbeConfig;
  probeConfigSignature: string;
  captureSignature: string;
  capture: CalibrationCaptureSummary;
  featureVector: CalibrationFeatureVector;
  quality: CalibrationQuality;
  stability: CalibrationStability;
  warnings: string[];
};

export type CalibrationProfile = {
  schemaVersion: 3;
  id: string;
  name: string;
  createdAt: string;
  updatedAt: string;
  anchors: Partial<Record<CalibrationAnchorKind, CalibrationAnchor>>;
  freeAirReference: CalibrationReference | null;
  knownReferences: KnownObjectReference[];
};

export type AnchorDistance = {
  kind: CalibrationAnchorKind;
  label: string;
  fillPercent: number;
  distance: number;
};

export type CalibrationReferenceMatch = {
  kind: CalibrationReferenceKind;
  label: string;
  distance: number;
};

export type KnownReferenceRole = 'free_air' | 'calibration_anchor' | 'known_object';

export type KnownReferenceDistance = {
  role: KnownReferenceRole;
  id: string;
  label: string;
  material: string | null;
  state: string | null;
  distance: number;
  sampleCount: number;
};

export type KnownReferenceComparison = {
  status: 'ready' | 'empty';
  nearest: KnownReferenceDistance | null;
  nearestObject: KnownReferenceDistance | null;
  freeAir: KnownReferenceDistance | null;
  distances: KnownReferenceDistance[];
  comparableFeatureCount: number;
  margin: number | null;
  confidence: number;
  confidenceLabel: 'high' | 'medium' | 'low' | 'none';
  freeAirDominates: boolean;
  warnings: string[];
};

export type CalibrationEstimate = {
  status: 'ready' | 'incomplete';
  fillPercent: number | null;
  confidence: number;
  confidenceLabel: 'high' | 'medium' | 'low' | 'none';
  nearestAnchor: AnchorDistance | null;
  referenceMatch: CalibrationReferenceMatch | null;
  anchorDistances: AnchorDistance[];
  segment: {
    from: CalibrationAnchorKind;
    to: CalibrationAnchorKind;
    position: number;
    residualDistance: number;
    spanDistance: number;
  } | null;
  comparableFeatureCount: number;
  profileRepeatCount: number;
  profileStability: CalibrationStability;
  freeAirDistance: number | null;
  warnings: string[];
  references: {
    globalMeanPercent: number;
    nearestAnchorPercent: number | null;
  };
};

export type CalibrationExportEnvelope = {
  format: 'resonancelab.calibration-profile';
  formatVersion: 1;
  exportedAt: string;
  profile: CalibrationProfile;
};

export type CalibrationAnalysisSource = Pick<
  AnalysisResponse,
  'analysis_id' | 'audio' | 'probe' | 'alignment' | 'dsp' | 'warnings'
>;
