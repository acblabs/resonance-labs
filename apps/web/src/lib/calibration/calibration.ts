import type { ProbeConfig } from '$lib/audio/types';
import type {
  AnchorDistance,
  CalibrationAnalysisSource,
  CalibrationAnchor,
  CalibrationAnchorDefinition,
  CalibrationAnchorKind,
  CalibrationCaptureSummary,
  CalibrationEstimate,
  CalibrationExportEnvelope,
  CalibrationFeature,
  CalibrationFeatureVector,
  CalibrationObservation,
  CalibrationProfile,
  CalibrationQuality,
  CalibrationReference,
  CalibrationStability,
  KnownObjectReference,
  KnownReferenceComparison,
  KnownReferenceDistance
} from './types';

const EPSILON = 1e-12;
const PROFILE_SCHEMA_VERSION = 3;
const MIN_COMPARABLE_FEATURES = 5;
const LOW_ALIGNMENT_CONFIDENCE = 0.2;
const LOW_SNR_DB = 12;
const CLOSE_ANCHOR_SPAN = 0.6;
const UNSTABLE_FEATURE_STD = 0.35;

export const CALIBRATION_ANCHORS: CalibrationAnchorDefinition[] = [
  { kind: 'empty', label: 'Empty', fillPercent: 0 },
  { kind: 'half', label: '50%', fillPercent: 50 },
  { kind: 'full', label: 'Full', fillPercent: 100 }
];

export const FREE_AIR_REFERENCE_LABEL = 'Free air';

export function createCalibrationProfile(name: string): CalibrationProfile {
  const now = new Date().toISOString();
  return {
    schemaVersion: PROFILE_SCHEMA_VERSION,
    id: createId('profile'),
    name: sanitizeProfileName(name),
    createdAt: now,
    updatedAt: now,
    anchors: {},
    freeAirReference: null,
    knownReferences: []
  };
}

export function renameCalibrationProfile(
  profile: CalibrationProfile,
  name: string
): CalibrationProfile {
  return {
    ...normalizeCalibrationProfile(profile),
    name: sanitizeProfileName(name),
    updatedAt: new Date().toISOString()
  };
}

export function withCalibrationAnchor(
  profile: CalibrationProfile,
  anchor: CalibrationAnchor
): CalibrationProfile {
  const normalized = normalizeCalibrationProfile(profile);
  const existing = normalized.anchors[anchor.kind];
  const observations = [
    ...(existing?.observations ?? []),
    ...anchor.observations
  ].map(normalizeObservation);

  return {
    ...normalized,
    anchors: {
      ...normalized.anchors,
      [anchor.kind]: aggregateAnchor(anchor.kind, observations)
    },
    updatedAt: new Date().toISOString()
  };
}

export function withFreeAirReference(
  profile: CalibrationProfile,
  reference: CalibrationReference
): CalibrationProfile {
  const normalized = normalizeCalibrationProfile(profile);
  const observations = [
    ...(normalized.freeAirReference?.observations ?? []),
    ...reference.observations
  ].map(normalizeObservation);

  return {
    ...normalized,
    freeAirReference: aggregateReference(observations),
    updatedAt: new Date().toISOString()
  };
}

export function withKnownObjectReference(
  profile: CalibrationProfile,
  reference: KnownObjectReference
): CalibrationProfile {
  const normalized = normalizeCalibrationProfile(profile);
  return {
    ...normalized,
    knownReferences: [
      reference,
      ...normalized.knownReferences.filter((candidate) => candidate.id !== reference.id)
    ],
    updatedAt: new Date().toISOString()
  };
}

export function withoutCalibrationAnchor(
  profile: CalibrationProfile,
  kind: CalibrationAnchorKind
): CalibrationProfile {
  const normalized = normalizeCalibrationProfile(profile);
  const anchors = { ...normalized.anchors };
  delete anchors[kind];
  return {
    ...normalized,
    anchors,
    updatedAt: new Date().toISOString()
  };
}

export function withoutFreeAirReference(profile: CalibrationProfile): CalibrationProfile {
  const normalized = normalizeCalibrationProfile(profile);
  return {
    ...normalized,
    freeAirReference: null,
    updatedAt: new Date().toISOString()
  };
}

export function withoutKnownObjectReference(
  profile: CalibrationProfile,
  referenceId: string
): CalibrationProfile {
  const normalized = normalizeCalibrationProfile(profile);
  return {
    ...normalized,
    knownReferences: normalized.knownReferences.filter(
      (reference) => reference.id !== referenceId
    ),
    updatedAt: new Date().toISOString()
  };
}

export function createCalibrationAnchor(
  kind: CalibrationAnchorKind,
  analysis: CalibrationAnalysisSource
): CalibrationAnchor {
  return aggregateAnchor(kind, [createObservation(analysis)]);
}

export function createFreeAirReference(
  analysis: CalibrationAnalysisSource
): CalibrationReference {
  return aggregateReference([createObservation(analysis)]);
}

export function createKnownObjectReference(
  analysis: CalibrationAnalysisSource,
  label: string,
  material: string
): KnownObjectReference {
  return aggregateKnownObjectReference(
    {
      id: createId('known-ref'),
      label: sanitizeReferenceLabel(label),
      material: sanitizeReferenceMaterial(material)
    },
    [createObservation(analysis)]
  );
}

export function exportCalibrationProfile(profile: CalibrationProfile): string {
  const envelope: CalibrationExportEnvelope = {
    format: 'resonancelab.calibration-profile',
    formatVersion: 1,
    exportedAt: new Date().toISOString(),
    profile: normalizeCalibrationProfile(profile)
  };
  return JSON.stringify(envelope, null, 2);
}

export function importCalibrationProfile(rawJson: string): CalibrationProfile {
  const parsed = JSON.parse(rawJson) as Partial<CalibrationExportEnvelope> | CalibrationProfile;
  const profilePayload =
    'format' in parsed && parsed.format === 'resonancelab.calibration-profile'
      ? parsed.profile
      : parsed;
  if (!profilePayload || typeof profilePayload !== 'object') {
    throw new Error('Calibration import did not contain a profile object.');
  }

  const now = new Date().toISOString();
  const normalized = normalizeCalibrationProfile(profilePayload as CalibrationProfile);
  return {
    ...normalized,
    id: createId('profile'),
    name: `${normalized.name} import`,
    createdAt: now,
    updatedAt: now
  };
}

export function normalizeCalibrationProfile(profile: CalibrationProfile): CalibrationProfile {
  const raw = profile as unknown as Record<string, unknown>;
  const anchorsRaw = (raw.anchors ?? {}) as Partial<Record<CalibrationAnchorKind, unknown>>;
  const anchors: Partial<Record<CalibrationAnchorKind, CalibrationAnchor>> = {};

  for (const definition of CALIBRATION_ANCHORS) {
    const rawAnchor = anchorsRaw[definition.kind];
    if (rawAnchor) {
      anchors[definition.kind] = normalizeAnchor(definition.kind, rawAnchor);
    }
  }

  const freeAirRaw = raw.freeAirReference as unknown;
  const knownReferencesRaw = Array.isArray(raw.knownReferences) ? raw.knownReferences : [];
  return {
    schemaVersion: PROFILE_SCHEMA_VERSION,
    id: stringOr(raw.id, createId('profile')),
    name: sanitizeProfileName(stringOr(raw.name, 'Local glass profile')),
    createdAt: stringOr(raw.createdAt, new Date().toISOString()),
    updatedAt: stringOr(raw.updatedAt, new Date().toISOString()),
    anchors,
    freeAirReference: freeAirRaw ? normalizeReference(freeAirRaw) : null,
    knownReferences: knownReferencesRaw
      .map(normalizeKnownObjectReference)
      .sort((left, right) => right.savedAt.localeCompare(left.savedAt))
  };
}

export function compareKnownReferences(
  analysis: CalibrationAnalysisSource,
  profile: CalibrationProfile
): KnownReferenceComparison {
  const normalizedProfile = normalizeCalibrationProfile(profile);
  const query = extractCalibrationFeatureVector(analysis);
  const references = referenceCandidates(normalizedProfile);
  const warnings: string[] = [];

  if (references.length === 0) {
    return emptyKnownReferenceComparison(['No free-air, anchor, or known-object references saved.']);
  }

  const featureSpace = buildFeatureSpace(
    query,
    references.map((reference) => reference.featureVector)
  );
  if (featureSpace.names.length < MIN_COMPARABLE_FEATURES) {
    warnings.push('Too few comparable reference features survived quality filtering.');
  }

  const queryPoint = projectFeatureVector(query, featureSpace);
  const distances = references
    .map((reference) => ({
      role: reference.role,
      id: reference.id,
      label: reference.label,
      material: reference.material,
      state: reference.state,
      distance: euclideanDistance(queryPoint, projectFeatureVector(reference.featureVector, featureSpace)),
      sampleCount: reference.sampleCount
    }))
    .sort((left, right) => left.distance - right.distance);
  const nearest = distances[0] ?? null;
  const nearestObject =
    distances.find((distance) => distance.role !== 'free_air') ?? null;
  const freeAir = distances.find((distance) => distance.role === 'free_air') ?? null;
  const runnerUp = distances[1] ?? null;
  const margin = nearest && runnerUp ? runnerUp.distance - nearest.distance : null;
  const freeAirDominates = Boolean(
    freeAir &&
      nearest?.role === 'free_air' &&
      (!nearestObject || freeAir.distance < nearestObject.distance * 0.85)
  );

  if (!nearestObject) {
    warnings.push('No saved object references are available for material comparison.');
  }
  if (freeAirDominates) {
    warnings.push('Current probe is closer to free-air than saved object references.');
  }

  const compatibility = compatibilityWarnings(
    analysis,
    Object.values(normalizedProfile.anchors).filter(
      (anchor): anchor is CalibrationAnchor => Boolean(anchor)
    ),
    normalizedProfile.freeAirReference,
    normalizedProfile.knownReferences.flatMap((reference) => reference.observations)
  );
  warnings.push(...compatibility.warnings);
  if (normalizedProfile.knownReferences.some((reference) => reference.sampleCount < 2)) {
    warnings.push('One or more known-object references has only one repeat.');
  }
  if (analysis.alignment.confidence < LOW_ALIGNMENT_CONFIDENCE) {
    warnings.push('Current chirp alignment confidence is below the reference threshold.');
  }
  if (analysis.dsp.signal_to_noise_db !== null && analysis.dsp.signal_to_noise_db < LOW_SNR_DB) {
    warnings.push('Current signal-to-noise ratio is below the reference threshold.');
  }
  if (analysis.warnings.length > 0) {
    warnings.push(...analysis.warnings);
  }

  const confidence = referenceComparisonConfidence({
    analysis,
    comparableFeatureCount: featureSpace.names.length,
    nearestDistance: nearest?.distance ?? Number.POSITIVE_INFINITY,
    margin,
    hasProbeMismatch: compatibility.hasProbeMismatch,
    hasCaptureMismatch: compatibility.hasCaptureMismatch,
    freeAirDominates,
    warningCount: warnings.length
  });

  return {
    status: 'ready',
    nearest,
    nearestObject,
    freeAir,
    distances,
    comparableFeatureCount: featureSpace.names.length,
    margin,
    confidence,
    confidenceLabel: freeAirDominates ? 'none' : confidenceLabel(confidence),
    freeAirDominates,
    warnings: uniqueWarnings(warnings)
  };
}

export function estimateFillLevel(
  analysis: CalibrationAnalysisSource,
  profile: CalibrationProfile
): CalibrationEstimate {
  const normalizedProfile = normalizeCalibrationProfile(profile);
  const missing = missingAnchorKinds(normalizedProfile);
  if (missing.length > 0) {
    return incompleteEstimate([
      `Missing ${missing.map((kind) => anchorDefinition(kind).label).join(', ')} anchors.`
    ]);
  }

  const anchors = requiredAnchors(normalizedProfile);
  const query = extractCalibrationFeatureVector(analysis);
  const featureSpace = buildFeatureSpace(
    query,
    anchors.map((anchor) => anchor.featureVector)
  );
  const warnings: string[] = [];

  if (featureSpace.names.length < MIN_COMPARABLE_FEATURES) {
    warnings.push('Too few comparable calibration features survived quality filtering.');
  }

  const queryPoint = projectFeatureVector(query, featureSpace);
  const anchorPoints = anchors.map((anchor) => ({
    anchor,
    point: projectFeatureVector(anchor.featureVector, featureSpace)
  }));
  const anchorDistances = anchorPoints.map(({ anchor, point }) => ({
    kind: anchor.kind,
    label: anchor.label,
    fillPercent: anchor.fillPercent,
    distance: euclideanDistance(queryPoint, point)
  }));
  const nearestAnchor = nearestDistance(anchorDistances);

  const lowerSegment = projectOntoSegment(
    queryPoint,
    anchorPoints[0].point,
    anchorPoints[1].point,
    anchors[0].kind,
    anchors[1].kind
  );
  const upperSegment = projectOntoSegment(
    queryPoint,
    anchorPoints[1].point,
    anchorPoints[2].point,
    anchors[1].kind,
    anchors[2].kind
  );
  const lowerScore = segmentScore(lowerSegment);
  const upperScore = segmentScore(upperSegment);
  const segment = lowerScore <= upperScore ? lowerSegment : upperSegment;
  const fillPercent =
    segment.from === 'empty' ? segment.position * 50 : 50 + segment.position * 50;

  const totalSpan =
    euclideanDistance(anchorPoints[0].point, anchorPoints[1].point) +
    euclideanDistance(anchorPoints[1].point, anchorPoints[2].point);
  if (totalSpan < CLOSE_ANCHOR_SPAN) {
    warnings.push('Calibration anchors are very close in feature space.');
  }

  const profileStability = combineStability(anchors.map((anchor) => anchor.stability));
  if (anchors.some((anchor) => anchor.sampleCount < 2)) {
    warnings.push('One or more calibration anchors has only one repeat.');
  }
  if ((profileStability.featureStdMax ?? 0) > UNSTABLE_FEATURE_STD) {
    warnings.push('Repeated anchor measurements vary enough to reduce confidence.');
  }

  if (!isPrimaryPeakMonotonic(anchors)) {
    warnings.push('Primary resonance peak is not monotonic across anchors; mode switching is possible.');
  }

  const compatibility = compatibilityWarnings(analysis, anchors, normalizedProfile.freeAirReference);
  warnings.push(...compatibility.warnings);

  if (analysis.alignment.confidence < LOW_ALIGNMENT_CONFIDENCE) {
    warnings.push('Current chirp alignment confidence is below the calibration threshold.');
  }
  if (analysis.dsp.signal_to_noise_db !== null && analysis.dsp.signal_to_noise_db < LOW_SNR_DB) {
    warnings.push('Current signal-to-noise ratio is below the calibration threshold.');
  }
  if (analysis.warnings.length > 0) {
    warnings.push(...analysis.warnings);
  }

  let freeAirDistance: number | null = null;
  let freeAirTooClose = false;
  let referenceMatch: CalibrationEstimate['referenceMatch'] = null;
  if (normalizedProfile.freeAirReference) {
    const freeAirPoint = projectFeatureVector(
      normalizedProfile.freeAirReference.featureVector,
      featureSpace
    );
    freeAirDistance = euclideanDistance(queryPoint, freeAirPoint);
    const nearestAnchorDistance = nearestAnchor?.distance ?? Number.POSITIVE_INFINITY;
    if (freeAirDistance < nearestAnchorDistance * 0.85) {
      freeAirTooClose = true;
      referenceMatch = {
        kind: 'free_air',
        label: FREE_AIR_REFERENCE_LABEL,
        distance: freeAirDistance
      };
      warnings.push('Current probe matches the free-air reference more closely than calibrated glass anchors.');
    }
  } else {
    warnings.push('No free-air reference captured; direct-path and room response are uncharacterized.');
  }

  const confidence = estimateConfidence({
    analysis,
    comparableFeatureCount: featureSpace.names.length,
    residualDistance: segment.residualDistance,
    segmentSpan: segment.spanDistance,
    totalSpan,
    profileStability,
    minAnchorRepeats: Math.min(...anchors.map((anchor) => anchor.sampleCount)),
    hasProbeMismatch: compatibility.hasProbeMismatch,
    hasCaptureMismatch: compatibility.hasCaptureMismatch,
    hasFreeAirReference: Boolean(normalizedProfile.freeAirReference),
    freeAirTooClose,
    warningCount: warnings.length
  });

  return {
    status: 'ready',
    fillPercent: referenceMatch ? null : clamp(fillPercent, 0, 100),
    confidence: referenceMatch ? 0 : confidence,
    confidenceLabel: referenceMatch ? 'none' : confidenceLabel(confidence),
    nearestAnchor: referenceMatch ? null : nearestAnchor,
    referenceMatch,
    anchorDistances,
    segment: {
      from: segment.from,
      to: segment.to,
      position: segment.position,
      residualDistance: segment.residualDistance,
      spanDistance: segment.spanDistance
    },
    comparableFeatureCount: featureSpace.names.length,
    profileRepeatCount: anchors.reduce((total, anchor) => total + anchor.sampleCount, 0),
    profileStability,
    freeAirDistance,
    warnings: uniqueWarnings(warnings),
    references: {
      globalMeanPercent: 50,
      nearestAnchorPercent: nearestAnchor?.fillPercent ?? null
    }
  };
}

export function extractCalibrationFeatureVector(
  analysis: CalibrationAnalysisSource
): CalibrationFeatureVector {
  const features: CalibrationFeature[] = [];
  const peaks = analysis.dsp.dominant_peaks.slice(0, 3);

  // Phase 3 uses physics priors until Phase 4 learns these scales and weights from
  // real repeats: resonance log-Hz shifts carry the strongest fill signal, while Q,
  // decay, and transfer bands provide softer evidence under modal overlap.
  for (let index = 0; index < peaks.length; index += 1) {
    const peak = peaks[index];
    addFiniteFeature(features, {
      name: `peak_${index + 1}_log_hz`,
      label: `Peak ${index + 1}`,
      value: log2(peak.frequency_hz),
      unit: 'log_hz',
      scaleHint: index === 0 ? 0.035 : 0.05,
      weight: index === 0 ? 2.2 : 1.1
    });
    addFiniteFeature(features, {
      name: `peak_${index + 1}_prominence_db`,
      label: `Peak ${index + 1} prominence`,
      value: peak.prominence_db,
      unit: 'db',
      scaleHint: 5,
      weight: index === 0 ? 0.7 : 0.45
    });
    if (peak.q_factor !== null) {
      addFiniteFeature(features, {
        name: `peak_${index + 1}_log_q`,
        label: `Peak ${index + 1} Q`,
        value: log2(peak.q_factor),
        unit: 'unitless',
        scaleHint: 0.5,
        weight: 0.45
      });
    }
  }

  addFiniteFeature(features, {
    name: 'spectral_centroid_log_hz',
    label: 'Spectral centroid',
    value: log2Nullable(analysis.dsp.fft.centroid_hz),
    unit: 'log_hz',
    scaleHint: 0.05,
    weight: 1.05
  });
  addFiniteFeature(features, {
    name: 'spectral_bandwidth_log_hz',
    label: 'Spectral bandwidth',
    value: log2Nullable(analysis.dsp.fft.bandwidth_hz),
    unit: 'log_hz',
    scaleHint: 0.08,
    weight: 0.75
  });
  addFiniteFeature(features, {
    name: 'spectral_rolloff_log_hz',
    label: 'Spectral rolloff',
    value: log2Nullable(analysis.dsp.fft.rolloff_hz),
    unit: 'log_hz',
    scaleHint: 0.06,
    weight: 0.75
  });
  addFiniteFeature(features, {
    name: 'decay_rate_log',
    label: 'Decay rate',
    value: log2Nullable(analysis.dsp.decay.decay_rate_per_second),
    unit: 'unitless',
    scaleHint: 0.35,
    weight: 0.7
  });
  addFiniteFeature(features, {
    name: 'rt60_log_seconds',
    label: 'RT60',
    value: log2Nullable(analysis.dsp.decay.rt60_seconds),
    unit: 'seconds',
    scaleHint: 0.35,
    weight: 0.55
  });

  for (const band of analysis.dsp.transfer_response) {
    const suffix = `${Math.round(band.center_hz)}hz`;
    addFiniteFeature(features, {
      name: `transfer_${suffix}_mean_db`,
      label: `${Math.round(band.center_hz)} Hz mean`,
      value: band.mean_db,
      unit: 'db',
      scaleHint: 4,
      weight: 0.55
    });
    addFiniteFeature(features, {
      name: `transfer_${suffix}_peak_db`,
      label: `${Math.round(band.center_hz)} Hz peak`,
      value: band.peak_db,
      unit: 'db',
      scaleHint: 5,
      weight: 0.35
    });
  }

  return {
    schemaVersion: 1,
    features,
    summary: {
      primaryPeakHz: peaks[0]?.frequency_hz ?? null,
      spectralCentroidHz: finiteOrNull(analysis.dsp.fft.centroid_hz),
      spectralRolloffHz: finiteOrNull(analysis.dsp.fft.rolloff_hz),
      decayRatePerSecond: finiteOrNull(analysis.dsp.decay.decay_rate_per_second),
      rt60Seconds: finiteOrNull(analysis.dsp.decay.rt60_seconds),
      transferBandCount: analysis.dsp.transfer_response.length
    }
  };
}

export function missingAnchorKinds(profile: CalibrationProfile): CalibrationAnchorKind[] {
  const normalized = normalizeCalibrationProfile(profile);
  return CALIBRATION_ANCHORS.map((anchor) => anchor.kind).filter(
    (kind) => normalized.anchors[kind] === undefined
  );
}

export function anchorCount(profile: CalibrationProfile): number {
  return CALIBRATION_ANCHORS.length - missingAnchorKinds(profile).length;
}

export function profileObservationCount(profile: CalibrationProfile): number {
  const normalized = normalizeCalibrationProfile(profile);
  const anchorSamples = CALIBRATION_ANCHORS.reduce(
    (total, definition) => total + (normalized.anchors[definition.kind]?.sampleCount ?? 0),
    0
  );
  const knownReferenceSamples = normalized.knownReferences.reduce(
    (total, reference) => total + reference.sampleCount,
    0
  );
  return anchorSamples + (normalized.freeAirReference?.sampleCount ?? 0) + knownReferenceSamples;
}

export function probeConfigSignature(config: ProbeConfig): string {
  return [
    config.signal_type,
    config.start_hz,
    config.end_hz,
    config.duration_ms,
    config.pre_roll_ms,
    config.post_roll_ms,
    Number(config.amplitude).toFixed(3),
    config.fade_ms
  ].join(':');
}

export function captureSignature(analysis: CalibrationAnalysisSource): string {
  return captureSignatureFromSummary(captureSummary(analysis));
}

function createObservation(analysis: CalibrationAnalysisSource): CalibrationObservation {
  const recordedAt = analysis.probe.client_recorded_at || new Date().toISOString();
  return {
    analysisId: String(analysis.analysis_id),
    recordedAt,
    savedAt: new Date().toISOString(),
    probeConfig: analysis.probe.probe_config,
    probeConfigSignature: probeConfigSignature(analysis.probe.probe_config),
    captureSignature: captureSignature(analysis),
    capture: captureSummary(analysis),
    featureVector: extractCalibrationFeatureVector(analysis),
    quality: {
      alignmentConfidence: finiteOr(analysis.alignment.confidence, 0),
      signalToNoiseDb: finiteOrNull(analysis.dsp.signal_to_noise_db),
      warningCount: analysis.warnings.length
    },
    warnings: [...analysis.warnings]
  };
}

function aggregateAnchor(
  kind: CalibrationAnchorKind,
  observations: CalibrationObservation[]
): CalibrationAnchor {
  const definition = anchorDefinition(kind);
  const normalizedObservations = observations.map(normalizeObservation);
  const latest = latestObservation(normalizedObservations);
  return {
    kind,
    label: definition.label,
    fillPercent: definition.fillPercent,
    sampleCount: normalizedObservations.length,
    observations: normalizedObservations,
    analysisId: latest.analysisId,
    recordedAt: latest.recordedAt,
    savedAt: latest.savedAt,
    probeConfig: latest.probeConfig,
    probeConfigSignature: latest.probeConfigSignature,
    captureSignature: latest.captureSignature,
    capture: latest.capture,
    featureVector: aggregateFeatureVector(normalizedObservations),
    quality: aggregateQuality(normalizedObservations),
    stability: stabilityForObservations(normalizedObservations),
    warnings: uniqueWarnings(normalizedObservations.flatMap((observation) => observation.warnings))
  };
}

function aggregateReference(observations: CalibrationObservation[]): CalibrationReference {
  const normalizedObservations = observations.map(normalizeObservation);
  const latest = latestObservation(normalizedObservations);
  return {
    kind: 'free_air',
    label: FREE_AIR_REFERENCE_LABEL,
    sampleCount: normalizedObservations.length,
    observations: normalizedObservations,
    analysisId: latest.analysisId,
    recordedAt: latest.recordedAt,
    savedAt: latest.savedAt,
    probeConfig: latest.probeConfig,
    probeConfigSignature: latest.probeConfigSignature,
    captureSignature: latest.captureSignature,
    capture: latest.capture,
    featureVector: aggregateFeatureVector(normalizedObservations),
    quality: aggregateQuality(normalizedObservations),
    stability: stabilityForObservations(normalizedObservations),
    warnings: uniqueWarnings(normalizedObservations.flatMap((observation) => observation.warnings))
  };
}

function aggregateKnownObjectReference(
  identity: { id: string; label: string; material: string },
  observations: CalibrationObservation[]
): KnownObjectReference {
  const normalizedObservations = observations.map(normalizeObservation);
  const latest = latestObservation(normalizedObservations);
  return {
    kind: 'known_object',
    id: identity.id,
    label: sanitizeReferenceLabel(identity.label),
    material: sanitizeReferenceMaterial(identity.material),
    sampleCount: normalizedObservations.length,
    observations: normalizedObservations,
    analysisId: latest.analysisId,
    recordedAt: latest.recordedAt,
    savedAt: latest.savedAt,
    probeConfig: latest.probeConfig,
    probeConfigSignature: latest.probeConfigSignature,
    captureSignature: latest.captureSignature,
    capture: latest.capture,
    featureVector: aggregateFeatureVector(normalizedObservations),
    quality: aggregateQuality(normalizedObservations),
    stability: stabilityForObservations(normalizedObservations),
    warnings: uniqueWarnings(normalizedObservations.flatMap((observation) => observation.warnings))
  };
}

function aggregateFeatureVector(observations: CalibrationObservation[]): CalibrationFeatureVector {
  if (observations.length === 0) {
    return emptyFeatureVector();
  }
  if (observations.length === 1) {
    return observations[0].featureVector;
  }

  const maps = observations.map((observation) => featureMap(observation.featureVector));
  const commonNames = [...maps[0].keys()].filter((name) => maps.every((map) => map.has(name)));
  const features = commonNames.map((name) => {
    const sourceFeatures = maps.map((map) => map.get(name) as CalibrationFeature);
    const first = sourceFeatures[0];
    return {
      ...first,
      value: mean(sourceFeatures.map((feature) => feature.value)),
      scaleHint: Math.max(...sourceFeatures.map((feature) => feature.scaleHint)),
      weight: Math.max(...sourceFeatures.map((feature) => feature.weight))
    };
  });

  return {
    schemaVersion: 1,
    features,
    summary: {
      primaryPeakHz: geometricMeanNullable(
        observations.map((observation) => observation.featureVector.summary.primaryPeakHz)
      ),
      spectralCentroidHz: geometricMeanNullable(
        observations.map((observation) => observation.featureVector.summary.spectralCentroidHz)
      ),
      spectralRolloffHz: geometricMeanNullable(
        observations.map((observation) => observation.featureVector.summary.spectralRolloffHz)
      ),
      decayRatePerSecond: meanNullable(
        observations.map((observation) => observation.featureVector.summary.decayRatePerSecond)
      ),
      rt60Seconds: meanNullable(
        observations.map((observation) => observation.featureVector.summary.rt60Seconds)
      ),
      transferBandCount: Math.round(
        mean(observations.map((observation) => observation.featureVector.summary.transferBandCount))
      )
    }
  };
}

function aggregateQuality(observations: CalibrationObservation[]): CalibrationQuality {
  return {
    alignmentConfidence: mean(observations.map((observation) => observation.quality.alignmentConfidence)),
    signalToNoiseDb: meanNullable(
      observations.map((observation) => observation.quality.signalToNoiseDb)
    ),
    warningCount: observations.reduce((total, observation) => total + observation.quality.warningCount, 0)
  };
}

function stabilityForObservations(observations: CalibrationObservation[]): CalibrationStability {
  if (observations.length < 2) {
    return {
      repeated: false,
      featureStdMean: null,
      featureStdMax: null,
      primaryPeakStdHz: null
    };
  }

  const maps = observations.map((observation) => featureMap(observation.featureVector));
  const commonNames = [...maps[0].keys()].filter((name) => maps.every((map) => map.has(name)));
  const normalizedStd = commonNames
    .map((name) => {
      const sourceFeatures = maps.map((map) => map.get(name) as CalibrationFeature);
      const values = sourceFeatures.map((feature) => feature.value);
      const scale = Math.max(...sourceFeatures.map((feature) => feature.scaleHint), EPSILON);
      return standardDeviation(values) / scale;
    })
    .filter(Number.isFinite);

  const peakValues = observations
    .map((observation) => observation.featureVector.summary.primaryPeakHz)
    .filter((value): value is number => value !== null && Number.isFinite(value));

  return {
    repeated: true,
    featureStdMean: normalizedStd.length > 0 ? mean(normalizedStd) : null,
    featureStdMax: normalizedStd.length > 0 ? Math.max(...normalizedStd) : null,
    primaryPeakStdHz: peakValues.length > 1 ? standardDeviation(peakValues) : null
  };
}

function normalizeAnchor(kind: CalibrationAnchorKind, rawAnchor: unknown): CalibrationAnchor {
  const raw = rawAnchor as Record<string, unknown>;
  if (Array.isArray(raw.observations)) {
    return aggregateAnchor(kind, raw.observations.map(normalizeObservation));
  }
  return aggregateAnchor(kind, [legacyObservation(raw)]);
}

function normalizeReference(rawReference: unknown): CalibrationReference {
  const raw = rawReference as Record<string, unknown>;
  if (Array.isArray(raw.observations)) {
    return aggregateReference(raw.observations.map(normalizeObservation));
  }
  return aggregateReference([legacyObservation(raw)]);
}

function normalizeKnownObjectReference(rawReference: unknown): KnownObjectReference {
  const raw = rawReference as Record<string, unknown>;
  const identity = {
    id: stringOr(raw.id, createId('known-ref')),
    label: sanitizeReferenceLabel(stringOr(raw.label, 'Known reference')),
    material: sanitizeReferenceMaterial(stringOr(raw.material, 'unknown'))
  };
  if (Array.isArray(raw.observations)) {
    return aggregateKnownObjectReference(identity, raw.observations.map(normalizeObservation));
  }
  return aggregateKnownObjectReference(identity, [legacyObservation(raw)]);
}

function normalizeObservation(rawObservation: unknown): CalibrationObservation {
  const raw = rawObservation as Partial<CalibrationObservation> & Record<string, unknown>;
  const probeConfig = raw.probeConfig as ProbeConfig;
  const fallbackConfig = probeConfig ?? {
    signal_type: 'log_chirp',
    start_hz: 500,
    end_hz: 10000,
    duration_ms: 500,
    pre_roll_ms: 250,
    post_roll_ms: 1000,
    amplitude: 0.35,
    fade_ms: 10
  };
  const capture = normalizeCapture(raw.capture);
  return {
    analysisId: stringOr(raw.analysisId, createId('analysis')),
    recordedAt: stringOr(raw.recordedAt, new Date().toISOString()),
    savedAt: stringOr(raw.savedAt, new Date().toISOString()),
    probeConfig: fallbackConfig,
    probeConfigSignature: stringOr(raw.probeConfigSignature, probeConfigSignature(fallbackConfig)),
    captureSignature: stringOr(raw.captureSignature, captureSignatureFromSummary(capture)),
    capture,
    featureVector: normalizeFeatureVector(raw.featureVector),
    quality: normalizeQuality(raw.quality),
    warnings: Array.isArray(raw.warnings) ? raw.warnings.map(String) : []
  };
}

function legacyObservation(raw: Record<string, unknown>): CalibrationObservation {
  return normalizeObservation({
    analysisId: raw.analysisId,
    recordedAt: raw.recordedAt,
    savedAt: raw.savedAt,
    probeConfig: raw.probeConfig,
    probeConfigSignature: raw.probeConfigSignature,
    captureSignature: raw.captureSignature,
    capture: raw.capture,
    featureVector: raw.featureVector,
    quality: raw.quality,
    warnings: raw.warnings
  });
}

function normalizeFeatureVector(rawVector: unknown): CalibrationFeatureVector {
  const raw = rawVector as CalibrationFeatureVector | undefined;
  if (!raw || !Array.isArray(raw.features)) {
    return emptyFeatureVector();
  }
  return {
    schemaVersion: 1,
    features: raw.features
      .filter((feature) => Number.isFinite(feature.value))
      .map((feature) => ({ ...feature })),
    summary: {
      primaryPeakHz: finiteOrNull(raw.summary?.primaryPeakHz),
      spectralCentroidHz: finiteOrNull(raw.summary?.spectralCentroidHz),
      spectralRolloffHz: finiteOrNull(raw.summary?.spectralRolloffHz),
      decayRatePerSecond: finiteOrNull(raw.summary?.decayRatePerSecond),
      rt60Seconds: finiteOrNull(raw.summary?.rt60Seconds),
      transferBandCount: Math.max(0, Math.round(finiteOr(raw.summary?.transferBandCount, 0)))
    }
  };
}

function normalizeQuality(rawQuality: unknown): CalibrationQuality {
  const raw = rawQuality as Partial<CalibrationQuality> | undefined;
  return {
    alignmentConfidence: clamp(finiteOr(raw?.alignmentConfidence, 0), 0, 1),
    signalToNoiseDb: finiteOrNull(raw?.signalToNoiseDb),
    warningCount: Math.max(0, Math.round(finiteOr(raw?.warningCount, 0)))
  };
}

function normalizeCapture(rawCapture: unknown): CalibrationCaptureSummary {
  const raw = rawCapture as Partial<CalibrationCaptureSummary> | undefined;
  return {
    sampleRateHz: Math.max(0, Math.round(finiteOr(raw?.sampleRateHz, 0))),
    audioContextSampleRateHz:
      raw?.audioContextSampleRateHz === null
        ? null
        : finiteOrNull(raw?.audioContextSampleRateHz),
    capturePath: raw?.capturePath ?? 'unknown',
    mediaProcessing: {
      echoCancellation: booleanOrNull(raw?.mediaProcessing?.echoCancellation),
      noiseSuppression: booleanOrNull(raw?.mediaProcessing?.noiseSuppression),
      autoGainControl: booleanOrNull(raw?.mediaProcessing?.autoGainControl)
    },
    userAgent: raw?.userAgent ?? null
  };
}

function emptyFeatureVector(): CalibrationFeatureVector {
  return {
    schemaVersion: 1,
    features: [],
    summary: {
      primaryPeakHz: null,
      spectralCentroidHz: null,
      spectralRolloffHz: null,
      decayRatePerSecond: null,
      rt60Seconds: null,
      transferBandCount: 0
    }
  };
}

function requiredAnchors(profile: CalibrationProfile): [CalibrationAnchor, CalibrationAnchor, CalibrationAnchor] {
  return [
    profile.anchors.empty as CalibrationAnchor,
    profile.anchors.half as CalibrationAnchor,
    profile.anchors.full as CalibrationAnchor
  ];
}

type ReferenceCandidate = {
  role: KnownReferenceDistance['role'];
  id: string;
  label: string;
  material: string | null;
  state: string | null;
  sampleCount: number;
  featureVector: CalibrationFeatureVector;
};

function referenceCandidates(profile: CalibrationProfile): ReferenceCandidate[] {
  const candidates: ReferenceCandidate[] = [];
  if (profile.freeAirReference) {
    candidates.push({
      role: 'free_air',
      id: 'free_air',
      label: profile.freeAirReference.label,
      material: null,
      state: 'free_air',
      sampleCount: profile.freeAirReference.sampleCount,
      featureVector: profile.freeAirReference.featureVector
    });
  }

  for (const anchor of Object.values(profile.anchors)) {
    if (!anchor) {
      continue;
    }
    candidates.push({
      role: 'calibration_anchor',
      id: `anchor:${anchor.kind}`,
      label: `${anchor.label} anchor`,
      material: 'glass',
      state: `${anchor.fillPercent}%`,
      sampleCount: anchor.sampleCount,
      featureVector: anchor.featureVector
    });
  }

  for (const reference of profile.knownReferences) {
    candidates.push({
      role: 'known_object',
      id: reference.id,
      label: reference.label,
      material: reference.material,
      state: null,
      sampleCount: reference.sampleCount,
      featureVector: reference.featureVector
    });
  }

  return candidates;
}

function anchorDefinition(kind: CalibrationAnchorKind): CalibrationAnchorDefinition {
  const definition = CALIBRATION_ANCHORS.find((anchor) => anchor.kind === kind);
  if (!definition) {
    throw new Error(`Unknown calibration anchor: ${kind}`);
  }
  return definition;
}

function buildFeatureSpace(
  query: CalibrationFeatureVector,
  anchors: CalibrationFeatureVector[]
): {
  names: string[];
  scales: Map<string, number>;
  weights: Map<string, number>;
} {
  if (anchors.length === 0) {
    return { names: [], scales: new Map(), weights: new Map() };
  }

  const queryMap = featureMap(query);
  const anchorMaps = anchors.map(featureMap);
  const names = [...queryMap.keys()].filter((name) => anchorMaps.every((map) => map.has(name)));
  const scales = new Map<string, number>();
  const weights = new Map<string, number>();

  for (const name of names) {
    const features = anchorMaps.map((map) => map.get(name) as CalibrationFeature);
    const values = features.map((feature) => feature.value);
    const range = Math.max(...values) - Math.min(...values);
    const scaleHint = Math.max(...features.map((feature) => feature.scaleHint));
    const weight = Math.max(...features.map((feature) => feature.weight));
    scales.set(name, Math.max(scaleHint, range, EPSILON));
    weights.set(name, Math.max(weight, EPSILON));
  }

  return { names, scales, weights };
}

function featureMap(vector: CalibrationFeatureVector): Map<string, CalibrationFeature> {
  const map = new Map<string, CalibrationFeature>();
  for (const feature of vector.features) {
    if (Number.isFinite(feature.value)) {
      map.set(feature.name, feature);
    }
  }
  return map;
}

function projectFeatureVector(
  vector: CalibrationFeatureVector,
  featureSpace: {
    names: string[];
    scales: Map<string, number>;
    weights: Map<string, number>;
  }
): number[] {
  const features = new Map(vector.features.map((feature) => [feature.name, feature]));
  return featureSpace.names.map((name) => {
    const feature = features.get(name);
    const scale = featureSpace.scales.get(name) ?? 1;
    const weight = Math.sqrt(featureSpace.weights.get(name) ?? 1);
    return feature ? (feature.value / scale) * weight : 0;
  });
}

function projectOntoSegment(
  query: number[],
  fromPoint: number[],
  toPoint: number[],
  from: CalibrationAnchorKind,
  to: CalibrationAnchorKind
): {
  from: CalibrationAnchorKind;
  to: CalibrationAnchorKind;
  position: number;
  residualDistance: number;
  spanDistance: number;
} {
  const segment = toPoint.map((value, index) => value - fromPoint[index]);
  const queryOffset = query.map((value, index) => value - fromPoint[index]);
  const spanSquared = dot(segment, segment);
  const rawPosition = spanSquared <= EPSILON ? 0 : dot(queryOffset, segment) / spanSquared;
  const position = clamp(rawPosition, 0, 1);
  const projected = fromPoint.map((value, index) => value + segment[index] * position);
  return {
    from,
    to,
    position,
    residualDistance: euclideanDistance(query, projected),
    spanDistance: Math.sqrt(Math.max(spanSquared, 0))
  };
}

function segmentScore(segment: { residualDistance: number; spanDistance: number }): number {
  return segment.residualDistance / Math.max(segment.spanDistance, 0.35);
}

function estimateConfidence({
  analysis,
  comparableFeatureCount,
  residualDistance,
  segmentSpan,
  totalSpan,
  profileStability,
  minAnchorRepeats,
  hasProbeMismatch,
  hasCaptureMismatch,
  hasFreeAirReference,
  freeAirTooClose,
  warningCount
}: {
  analysis: CalibrationAnalysisSource;
  comparableFeatureCount: number;
  residualDistance: number;
  segmentSpan: number;
  totalSpan: number;
  profileStability: CalibrationStability;
  minAnchorRepeats: number;
  hasProbeMismatch: boolean;
  hasCaptureMismatch: boolean;
  hasFreeAirReference: boolean;
  freeAirTooClose: boolean;
  warningCount: number;
}): number {
  const residualRatio = residualDistance / Math.max(segmentSpan, 0.35);
  const residualFactor = Math.exp(-Math.pow(residualRatio / 0.65, 2));
  const spanFactor = clamp((totalSpan - 0.35) / 2.2, 0.18, 1);
  const featureFactor = clamp(comparableFeatureCount / 10, 0.25, 1);
  const alignmentFactor = clamp((analysis.alignment.confidence - 0.12) / 0.68, 0.12, 1);
  const snr = analysis.dsp.signal_to_noise_db;
  const snrFactor = snr === null ? 0.75 : clamp((snr - 6) / 16, 0.15, 1);
  const repeatFactor = minAnchorRepeats >= 2 ? 1 : 0.82;
  const stability = profileStability.featureStdMax ?? 0;
  const stabilityFactor = Math.exp(-Math.pow(stability / 0.75, 2));
  const freeAirFactor = hasFreeAirReference ? 1 : 0.84;
  const warningFactor = Math.pow(0.9, Math.min(warningCount, 8));

  // Confidence is a reliability prior, not a learned probability. Residual geometry
  // dominates; capture/probe mismatches and weak measurement quality impose hard caps.
  const baseConfidence = weightedGeometricMean(
    [
      { value: residualFactor, weight: 3.0 },
      { value: spanFactor, weight: 1.4 },
      { value: featureFactor, weight: 0.9 },
      { value: alignmentFactor, weight: 1.4 },
      { value: snrFactor, weight: 1.0 },
      { value: repeatFactor, weight: 0.5 },
      { value: stabilityFactor, weight: 1.1 },
      { value: freeAirFactor, weight: 0.45 },
      { value: warningFactor, weight: 0.55 }
    ],
    0.99
  );

  const caps = [0.99];
  if (hasProbeMismatch) {
    caps.push(0.32);
  }
  if (hasCaptureMismatch) {
    caps.push(0.4);
  }
  if (freeAirTooClose) {
    caps.push(0.35);
  }
  if (analysis.alignment.confidence < LOW_ALIGNMENT_CONFIDENCE) {
    caps.push(0.24);
  }
  if (snr !== null && snr < LOW_SNR_DB) {
    caps.push(0.45);
  }
  if (comparableFeatureCount < MIN_COMPARABLE_FEATURES) {
    caps.push(0.35);
  }
  if (totalSpan < CLOSE_ANCHOR_SPAN) {
    caps.push(0.45);
  }

  return clamp(Math.min(baseConfidence, ...caps), 0, 0.99);
}

function referenceComparisonConfidence({
  analysis,
  comparableFeatureCount,
  nearestDistance,
  margin,
  hasProbeMismatch,
  hasCaptureMismatch,
  freeAirDominates,
  warningCount
}: {
  analysis: CalibrationAnalysisSource;
  comparableFeatureCount: number;
  nearestDistance: number;
  margin: number | null;
  hasProbeMismatch: boolean;
  hasCaptureMismatch: boolean;
  freeAirDominates: boolean;
  warningCount: number;
}): number {
  const distanceFactor = Math.exp(-Math.pow(nearestDistance / 1.15, 2));
  const marginRatio =
    margin === null ? 0.35 : margin / Math.max(nearestDistance, 0.35);
  const marginFactor = clamp(marginRatio / 0.65, 0.12, 1);
  const featureFactor = clamp(comparableFeatureCount / 10, 0.25, 1);
  const alignmentFactor = clamp((analysis.alignment.confidence - 0.12) / 0.68, 0.12, 1);
  const snr = analysis.dsp.signal_to_noise_db;
  const snrFactor = snr === null ? 0.75 : clamp((snr - 6) / 16, 0.15, 1);
  const warningFactor = Math.pow(0.9, Math.min(warningCount, 8));
  const baseConfidence = weightedGeometricMean(
    [
      { value: distanceFactor, weight: 1.8 },
      { value: marginFactor, weight: 2.2 },
      { value: featureFactor, weight: 0.9 },
      { value: alignmentFactor, weight: 1.2 },
      { value: snrFactor, weight: 1.0 },
      { value: warningFactor, weight: 0.5 }
    ],
    0.5
  );

  const caps = [0.99];
  if (hasProbeMismatch) {
    caps.push(0.35);
  }
  if (hasCaptureMismatch) {
    caps.push(0.42);
  }
  if (freeAirDominates) {
    caps.push(0);
  }
  if (analysis.alignment.confidence < LOW_ALIGNMENT_CONFIDENCE) {
    caps.push(0.24);
  }
  if (snr !== null && snr < LOW_SNR_DB) {
    caps.push(0.45);
  }
  if (comparableFeatureCount < MIN_COMPARABLE_FEATURES) {
    caps.push(0.35);
  }

  return clamp(Math.min(baseConfidence, ...caps), 0, 0.99);
}

function compatibilityWarnings(
  analysis: CalibrationAnalysisSource,
  anchors: CalibrationAnchor[],
  freeAirReference: CalibrationReference | null,
  extraObservations: CalibrationObservation[] = []
): {
  warnings: string[];
  hasProbeMismatch: boolean;
  hasCaptureMismatch: boolean;
} {
  const warnings: string[] = [];
  const observations = [
    ...anchors.flatMap((anchor) => anchor.observations),
    ...(freeAirReference?.observations ?? []),
    ...extraObservations
  ];
  const queryProbeSignature = probeConfigSignature(analysis.probe.probe_config);
  const queryCapture = captureSummary(analysis);

  const hasProbeMismatch = observations.some(
    (observation) => observation.probeConfigSignature !== queryProbeSignature
  );
  if (hasProbeMismatch) {
    warnings.push('Probe settings differ from one or more saved calibration samples.');
  }

  const hasSampleRateMismatch = observations.some(
    (observation) => observation.capture.sampleRateHz !== queryCapture.sampleRateHz
  );
  if (hasSampleRateMismatch) {
    warnings.push('Capture sample rate differs from one or more saved calibration samples.');
  }

  const hasPathMismatch = observations.some(
    (observation) => observation.capture.capturePath !== queryCapture.capturePath
  );
  if (hasPathMismatch) {
    warnings.push('Browser capture path differs from one or more saved calibration samples.');
  }

  const hasBrowserFamilyMismatch = observations.some(
    (observation) => browserFamily(observation.capture.userAgent) !== browserFamily(queryCapture.userAgent)
  );
  if (hasBrowserFamilyMismatch) {
    warnings.push('Browser family differs from one or more saved calibration samples.');
  }

  const hasMediaProcessingMismatch = observations.some(
    (observation) => mediaProcessingSignature(observation.capture) !== mediaProcessingSignature(queryCapture)
  );
  if (hasMediaProcessingMismatch) {
    warnings.push('Browser audio-processing settings differ from saved calibration samples.');
  }

  const currentHasProcessing = Object.values(queryCapture.mediaProcessing).some((value) => value === true);
  if (currentHasProcessing) {
    warnings.push('Current browser capture reports audio processing enabled.');
  }

  return {
    warnings,
    hasProbeMismatch,
    hasCaptureMismatch:
      hasSampleRateMismatch ||
      hasPathMismatch ||
      hasBrowserFamilyMismatch ||
      hasMediaProcessingMismatch
  };
}

function captureSummary(analysis: CalibrationAnalysisSource): CalibrationCaptureSummary {
  const settings = analysis.probe.browser.media_track_settings ?? {};
  return {
    sampleRateHz: analysis.audio.sample_rate_hz,
    audioContextSampleRateHz: finiteOrNull(analysis.probe.browser.audio_context_sample_rate_hz),
    capturePath: analysis.probe.browser.capture_path,
    mediaProcessing: {
      echoCancellation: booleanOrNull(settings.echoCancellation),
      noiseSuppression: booleanOrNull(settings.noiseSuppression),
      autoGainControl: booleanOrNull(settings.autoGainControl)
    },
    userAgent: analysis.probe.browser.user_agent ?? null
  };
}

function captureSignatureFromSummary(capture: CalibrationCaptureSummary): string {
  return [
    capture.sampleRateHz,
    capture.audioContextSampleRateHz ?? 'ctx-unknown',
    capture.capturePath,
    browserFamily(capture.userAgent),
    mediaProcessingSignature(capture)
  ].join(':');
}

function mediaProcessingSignature(capture: CalibrationCaptureSummary): string {
  return [
    capture.mediaProcessing.echoCancellation,
    capture.mediaProcessing.noiseSuppression,
    capture.mediaProcessing.autoGainControl
  ].join('/');
}

function browserFamily(userAgent: string | null): string {
  const value = (userAgent ?? '').toLowerCase();
  if (value.includes('edg/')) {
    return 'edge';
  }
  if (value.includes('chrome/') || value.includes('chromium/')) {
    return 'chrome';
  }
  if (value.includes('firefox/')) {
    return 'firefox';
  }
  if (value.includes('safari/')) {
    return 'safari';
  }
  return 'unknown';
}

function combineStability(stabilities: CalibrationStability[]): CalibrationStability {
  const repeated = stabilities.some((stability) => stability.repeated);
  return {
    repeated,
    featureStdMean: meanNullable(stabilities.map((stability) => stability.featureStdMean)),
    featureStdMax: maxNullable(stabilities.map((stability) => stability.featureStdMax)),
    primaryPeakStdHz: maxNullable(stabilities.map((stability) => stability.primaryPeakStdHz))
  };
}

function isPrimaryPeakMonotonic(anchors: CalibrationAnchor[]): boolean {
  const peaks = anchors.map((anchor) => anchor.featureVector.summary.primaryPeakHz);
  if (peaks.some((peak) => peak === null)) {
    return true;
  }
  const [empty, half, full] = peaks as [number, number, number];
  const toleranceHz = Math.max(25, Math.abs(empty) * 0.01);
  const downward = empty + toleranceHz >= half && half + toleranceHz >= full;
  const upward = empty <= half + toleranceHz && half <= full + toleranceHz;
  return downward || upward;
}

function confidenceLabel(confidence: number): CalibrationEstimate['confidenceLabel'] {
  if (confidence >= 0.72) {
    return 'high';
  }
  if (confidence >= 0.42) {
    return 'medium';
  }
  if (confidence > 0) {
    return 'low';
  }
  return 'none';
}

function nearestDistance(distances: AnchorDistance[]): AnchorDistance | null {
  if (distances.length === 0) {
    return null;
  }
  return distances.reduce((best, candidate) =>
    candidate.distance < best.distance ? candidate : best
  );
}

function incompleteEstimate(warnings: string[]): CalibrationEstimate {
  return {
    status: 'incomplete',
    fillPercent: null,
    confidence: 0,
    confidenceLabel: 'none',
    nearestAnchor: null,
    referenceMatch: null,
    anchorDistances: [],
    segment: null,
    comparableFeatureCount: 0,
    profileRepeatCount: 0,
    profileStability: {
      repeated: false,
      featureStdMean: null,
      featureStdMax: null,
      primaryPeakStdHz: null
    },
    freeAirDistance: null,
    warnings,
    references: {
      globalMeanPercent: 50,
      nearestAnchorPercent: null
    }
  };
}

function emptyKnownReferenceComparison(warnings: string[]): KnownReferenceComparison {
  return {
    status: 'empty',
    nearest: null,
    nearestObject: null,
    freeAir: null,
    distances: [],
    comparableFeatureCount: 0,
    margin: null,
    confidence: 0,
    confidenceLabel: 'none',
    freeAirDominates: false,
    warnings
  };
}

function latestObservation(observations: CalibrationObservation[]): CalibrationObservation {
  if (observations.length === 0) {
    throw new Error('Calibration aggregate requires at least one observation.');
  }
  return observations.reduce((latest, observation) =>
    observation.savedAt.localeCompare(latest.savedAt) > 0 ? observation : latest
  );
}

function addFiniteFeature(features: CalibrationFeature[], feature: CalibrationFeature): void {
  if (Number.isFinite(feature.value)) {
    features.push(feature);
  }
}

function uniqueWarnings(warnings: string[]): string[] {
  return [...new Set(warnings.filter((warning) => warning.trim().length > 0))];
}

function dot(left: number[], right: number[]): number {
  return left.reduce((total, value, index) => total + value * right[index], 0);
}

function euclideanDistance(left: number[], right: number[]): number {
  const sum = left.reduce((total, value, index) => {
    const delta = value - right[index];
    return total + delta * delta;
  }, 0);
  return Math.sqrt(sum);
}

function mean(values: number[]): number {
  const finite = values.filter(Number.isFinite);
  if (finite.length === 0) {
    return 0;
  }
  return finite.reduce((total, value) => total + value, 0) / finite.length;
}

function meanNullable(values: Array<number | null | undefined>): number | null {
  const finite = values.filter((value): value is number => value !== null && value !== undefined && Number.isFinite(value));
  return finite.length > 0 ? mean(finite) : null;
}

function geometricMeanNullable(values: Array<number | null | undefined>): number | null {
  const finite = values.filter(
    (value): value is number =>
      value !== null && value !== undefined && Number.isFinite(value) && value > 0
  );
  return finite.length > 0 ? 2 ** mean(finite.map((value) => log2(value))) : null;
}

function maxNullable(values: Array<number | null | undefined>): number | null {
  const finite = values.filter((value): value is number => value !== null && value !== undefined && Number.isFinite(value));
  return finite.length > 0 ? Math.max(...finite) : null;
}

function standardDeviation(values: number[]): number {
  const finite = values.filter(Number.isFinite);
  if (finite.length < 2) {
    return 0;
  }
  const center = mean(finite);
  const variance = mean(finite.map((value) => Math.pow(value - center, 2)));
  return Math.sqrt(variance);
}

function weightedGeometricMean(
  factors: Array<{ value: number; weight: number }>,
  fallback: number
): number {
  const usable = factors.filter(
    (factor) => Number.isFinite(factor.value) && Number.isFinite(factor.weight) && factor.weight > 0
  );
  const weightSum = usable.reduce((total, factor) => total + factor.weight, 0);
  if (usable.length === 0 || weightSum <= EPSILON) {
    return fallback;
  }

  const logSum = usable.reduce((total, factor) => {
    return total + factor.weight * Math.log(clamp(factor.value, EPSILON, 1));
  }, 0);
  return clamp(Math.exp(logSum / weightSum), 0, 1);
}

function log2(value: number): number {
  return Math.log(Math.max(value, EPSILON)) / Math.LN2;
}

function log2Nullable(value: number | null | undefined): number {
  return value === null || value === undefined ? Number.NaN : log2(value);
}

function finiteOr(value: number | null | undefined, fallback: number): number {
  return value !== null && value !== undefined && Number.isFinite(value) ? value : fallback;
}

function finiteOrNull(value: number | null | undefined): number | null {
  return value !== null && value !== undefined && Number.isFinite(value) ? value : null;
}

function booleanOrNull(value: unknown): boolean | null {
  return typeof value === 'boolean' ? value : null;
}

function stringOr(value: unknown, fallback: string): string {
  return typeof value === 'string' && value.trim().length > 0 ? value : fallback;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function sanitizeProfileName(name: string): string {
  const trimmed = name.trim();
  return trimmed.length > 0 ? trimmed.slice(0, 80) : 'Local glass profile';
}

function sanitizeReferenceLabel(label: string): string {
  const trimmed = label.trim();
  return trimmed.length > 0 ? trimmed.slice(0, 80) : 'Known reference';
}

function sanitizeReferenceMaterial(material: string): string {
  const trimmed = material.trim().toLowerCase();
  return trimmed.length > 0 ? trimmed.slice(0, 60) : 'unknown';
}

function createId(prefix: string): string {
  if (globalThis.crypto?.randomUUID) {
    return globalThis.crypto.randomUUID();
  }
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}
