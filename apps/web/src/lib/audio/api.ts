import { env } from '$env/dynamic/public';
import { dev } from '$app/environment';
import type { AnalysisResponse, ProbeConfigEnvelope, ProbeMetadata } from './types';

export function apiBaseUrl(): string {
  if (env.PUBLIC_API_URL) {
    return env.PUBLIC_API_URL;
  }
  if (dev) {
    return 'http://localhost:8000';
  }
  throw new Error('PUBLIC_API_URL must be configured outside local development.');
}

export async function loadProbeConfig(): Promise<ProbeConfigEnvelope> {
  const response = await fetch(`${apiBaseUrl()}/api/v1/probe-config`);
  if (!response.ok) {
    throw new Error(`Probe config request failed with HTTP ${response.status}.`);
  }
  return response.json() as Promise<ProbeConfigEnvelope>;
}

export async function analyzeProbe(wavBlob: Blob, metadata: ProbeMetadata): Promise<AnalysisResponse> {
  const form = new FormData();
  form.append('audio', wavBlob, 'resonancelab-probe.wav');
  form.append('metadata', JSON.stringify(metadata));

  const response = await fetch(`${apiBaseUrl()}/api/v1/analyze`, {
    method: 'POST',
    body: form
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Analyze request failed with HTTP ${response.status}: ${errorText}`);
  }

  return response.json() as Promise<AnalysisResponse>;
}
