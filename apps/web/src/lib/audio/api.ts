import { env } from "$env/dynamic/public";
import { dev } from "$app/environment";
import type {
  AnalysisResponse,
  DatasetCaptureRequest,
  DatasetCaptureResponse,
  ProbeConfigEnvelope,
  ProbeMetadata,
} from "./types";

export function apiBaseUrl(): string {
  if (env.PUBLIC_API_URL) {
    return env.PUBLIC_API_URL;
  }
  if (dev) {
    return "http://localhost:8000";
  }
  throw new Error(
    "PUBLIC_API_URL must be configured outside local development.",
  );
}

export async function loadProbeConfig(): Promise<ProbeConfigEnvelope> {
  const response = await fetch(`${apiBaseUrl()}/api/v1/probe-config`);
  if (!response.ok) {
    throw new Error(
      `Probe config request failed with HTTP ${response.status}.`,
    );
  }
  return response.json() as Promise<ProbeConfigEnvelope>;
}

export async function analyzeProbe(
  wavBlob: Blob,
  metadata: ProbeMetadata,
): Promise<AnalysisResponse> {
  const form = new FormData();
  form.append("audio", wavBlob, "resonancelab-probe.wav");
  form.append("metadata", JSON.stringify(metadata));

  const response = await fetch(`${apiBaseUrl()}/api/v1/analyze`, {
    method: "POST",
    body: form,
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(
      `Analyze request failed with HTTP ${response.status}: ${errorText}`,
    );
  }

  return response.json() as Promise<AnalysisResponse>;
}

export function isPhase4CaptureEnabled(): boolean {
  return env.PUBLIC_PHASE4_CAPTURE_ENABLED === "true";
}

export async function saveDatasetCapture(
  wavBlob: Blob,
  metadata: ProbeMetadata,
  capture: DatasetCaptureRequest,
  operatorToken: string,
): Promise<DatasetCaptureResponse> {
  const form = new FormData();
  form.append("audio", wavBlob, "resonancelab-phase4-capture.wav");
  form.append("metadata", JSON.stringify(metadata));
  form.append("capture", JSON.stringify(capture));

  const idempotencyKey = await datasetCaptureIdempotencyKey(
    wavBlob,
    metadata,
    capture,
  );

  const response = await fetch(`${apiBaseUrl()}/api/v1/dataset/captures`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${operatorToken}`,
      "Idempotency-Key": idempotencyKey,
    },
    body: form,
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(
      `Dataset capture failed with HTTP ${response.status}: ${errorText}`,
    );
  }

  return response.json() as Promise<DatasetCaptureResponse>;
}

async function datasetCaptureIdempotencyKey(
  wavBlob: Blob,
  metadata: ProbeMetadata,
  capture: DatasetCaptureRequest,
): Promise<string> {
  const audioDigest = await sha256Hex(await wavBlob.arrayBuffer());
  const metadataDigest = await sha256Hex(
    bytesToArrayBuffer(new TextEncoder().encode(stableStringify(metadata))),
  );
  const captureDigest = await sha256Hex(
    bytesToArrayBuffer(new TextEncoder().encode(stableStringify(capture))),
  );
  return `${audioDigest.slice(0, 32)}-${metadataDigest.slice(0, 12)}-${captureDigest.slice(0, 12)}`;
}

async function sha256Hex(data: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
}

function bytesToArrayBuffer(bytes: Uint8Array): ArrayBuffer {
  const copy = new Uint8Array(bytes.byteLength);
  copy.set(bytes);
  return copy.buffer;
}

function stableStringify(value: unknown): string {
  if (value === null || typeof value !== "object") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => stableStringify(item)).join(",")}]`;
  }
  const record = value as Record<string, unknown>;
  return `{${Object.keys(record)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${stableStringify(record[key])}`)
    .join(",")}}`;
}
