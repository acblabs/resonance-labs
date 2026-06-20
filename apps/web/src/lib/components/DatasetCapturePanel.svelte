<script lang="ts">
  import { isPhase4CaptureEnabled, saveDatasetCapture } from "$lib/audio/api";
  import type {
    AnalysisResponse,
    DatasetCaptureContext,
    DatasetCaptureLabel,
    ProbeMetadata,
  } from "$lib/audio/types";

  export let result: AnalysisResponse | null = null;
  export let wavBlob: Blob | null = null;
  export let metadata: ProbeMetadata | null = null;

  const captureEnabled = isPhase4CaptureEnabled();

  let operatorToken = "";
  let sessionId = "";
  let glassId = "";
  let deviceId = "";
  let browserId = "";
  let roomId = "";
  let volumeSetting = "";
  let operatorId = "";
  let material = "";
  let geometry = "";
  let notes = "";
  let fillPercent = "";
  let emptyMass = "";
  let fullMass = "";
  let currentMass = "";
  let storeAudio = true;
  let saving = false;
  let captureStatus = "Ready";
  let captureError = "";
  let lastRecordId = "";
  let derivedFillPercent: number | null = null;

  $: if (result?.probe.browser.user_agent && !browserId) {
    browserId = browserLabel(result.probe.browser.user_agent);
  }
  $: derivedFillPercent = computeDerivedFillPercent();
  $: canSave =
    Boolean(result && wavBlob && metadata) &&
    Boolean(operatorToken.trim()) &&
    Boolean(sessionId.trim()) &&
    Boolean(glassId.trim()) &&
    Boolean(deviceId.trim()) &&
    Boolean(browserId.trim()) &&
    Boolean(roomId.trim()) &&
    (optionalNumber(fillPercent) !== undefined || derivedFillPercent !== null);

  async function saveCapture(): Promise<void> {
    if (!result || !wavBlob || !metadata || !canSave) {
      return;
    }

    saving = true;
    captureError = "";
    captureStatus = "Saving";
    try {
      const response = await saveDatasetCapture(
        wavBlob,
        metadata,
        {
          label: buildLabel(),
          context: buildContext(),
          store_audio: storeAudio,
          notes: clean(notes),
        },
        operatorToken.trim(),
      );
      lastRecordId = response.record_id;
      captureStatus = "Stored";
    } catch (error) {
      captureError = error instanceof Error ? error.message : String(error);
      captureStatus = "Failed";
    } finally {
      saving = false;
    }
  }

  function buildLabel(): DatasetCaptureLabel {
    const label: DatasetCaptureLabel = {};
    const explicitFill = optionalNumber(fillPercent);
    if (explicitFill !== undefined) {
      label.fill_percent = explicitFill;
    }
    const empty = optionalNumber(emptyMass);
    const full = optionalNumber(fullMass);
    const current = optionalNumber(currentMass);
    if (empty !== undefined) {
      label.vessel_empty_mass_g = empty;
    }
    if (full !== undefined) {
      label.vessel_full_mass_g = full;
    }
    if (current !== undefined) {
      label.vessel_current_mass_g = current;
      if (empty !== undefined) {
        label.fill_mass_g = Math.max(0, current - empty);
      }
    }
    return label;
  }

  function buildContext(): DatasetCaptureContext {
    return {
      session_id: sessionId.trim(),
      glass_id: glassId.trim(),
      device_id: deviceId.trim(),
      browser_id: browserId.trim(),
      room_id: roomId.trim(),
      operator_id: clean(operatorId),
      volume_setting: clean(volumeSetting),
      material: clean(material),
      geometry: clean(geometry),
      notes: clean(notes),
    };
  }

  function computeDerivedFillPercent(): number | null {
    const empty = optionalNumber(emptyMass);
    const full = optionalNumber(fullMass);
    const current = optionalNumber(currentMass);
    if (empty === undefined || full === undefined || current === undefined) {
      return null;
    }
    const capacity = full - empty;
    if (capacity <= 0) {
      return null;
    }
    const percent = (100 * (current - empty)) / capacity;
    return Number.isFinite(percent) && percent >= 0 && percent <= 100
      ? percent
      : null;
  }

  function optionalNumber(value: string): number | undefined {
    const text = value.trim();
    if (!text) {
      return undefined;
    }
    const numericValue = Number(text);
    return Number.isFinite(numericValue) ? numericValue : undefined;
  }

  function clean(value: string): string | undefined {
    const text = value.trim();
    return text || undefined;
  }

  function browserLabel(userAgent: string): string {
    const lower = userAgent.toLowerCase();
    if (lower.includes("firefox")) {
      return "firefox";
    }
    if (lower.includes("edg/")) {
      return "edge";
    }
    if (lower.includes("chrome")) {
      return "chrome";
    }
    if (lower.includes("safari")) {
      return "safari";
    }
    return "browser";
  }
</script>

{#if captureEnabled}
  <form
    class="dataset-capture-block"
    aria-label="Private dataset capture"
    on:submit|preventDefault={saveCapture}
  >
    <div class="section-heading">
      <h2>Dataset Capture</h2>
      <span>{captureStatus}</span>
    </div>

    <div class="control-grid">
      <div class="field">
        <label for="phase4-token">Operator token</label>
        <input
          id="phase4-token"
          type="password"
          bind:value={operatorToken}
          autocomplete="off"
        />
      </div>
      <div class="field">
        <label for="phase4-session">Session ID</label>
        <input id="phase4-session" type="text" bind:value={sessionId} />
      </div>
      <div class="field">
        <label for="phase4-glass">Glass ID</label>
        <input id="phase4-glass" type="text" bind:value={glassId} />
      </div>
      <div class="field">
        <label for="phase4-device">Device ID</label>
        <input id="phase4-device" type="text" bind:value={deviceId} />
      </div>
      <div class="field">
        <label for="phase4-browser">Browser ID</label>
        <input id="phase4-browser" type="text" bind:value={browserId} />
      </div>
      <div class="field">
        <label for="phase4-room">Room ID</label>
        <input id="phase4-room" type="text" bind:value={roomId} />
      </div>
      <div class="field">
        <label for="phase4-fill">Fill %</label>
        <input
          id="phase4-fill"
          type="number"
          min="0"
          max="100"
          step="0.1"
          bind:value={fillPercent}
        />
      </div>
      <div class="field">
        <label for="phase4-current-mass">Current mass g</label>
        <input
          id="phase4-current-mass"
          type="number"
          min="0"
          step="0.1"
          bind:value={currentMass}
        />
      </div>
      <div class="field">
        <label for="phase4-empty-mass">Empty mass g</label>
        <input
          id="phase4-empty-mass"
          type="number"
          min="0"
          step="0.1"
          bind:value={emptyMass}
        />
      </div>
      <div class="field">
        <label for="phase4-full-mass">Full mass g</label>
        <input
          id="phase4-full-mass"
          type="number"
          min="0"
          step="0.1"
          bind:value={fullMass}
        />
      </div>
      <div class="field">
        <label for="phase4-volume">Volume setting</label>
        <input id="phase4-volume" type="text" bind:value={volumeSetting} />
      </div>
      <div class="field">
        <label for="phase4-operator">Operator ID</label>
        <input id="phase4-operator" type="text" bind:value={operatorId} />
      </div>
      <div class="field">
        <label for="phase4-material">Material</label>
        <input id="phase4-material" type="text" bind:value={material} />
      </div>
      <div class="field">
        <label for="phase4-geometry">Geometry</label>
        <input id="phase4-geometry" type="text" bind:value={geometry} />
      </div>
    </div>

    <div class="field">
      <label for="phase4-notes">Notes</label>
      <input id="phase4-notes" type="text" bind:value={notes} />
    </div>

    <label class="checkbox-field">
      <input type="checkbox" bind:checked={storeAudio} />
      <span>Store WAV</span>
    </label>

    <div class="actions">
      <button
        class="secondary-button"
        type="submit"
        disabled={!canSave || saving}
      >
        {saving ? "Saving" : "Save Dataset Capture"}
      </button>
      <span class="status-line">
        {lastRecordId ||
          (derivedFillPercent === null
            ? "--"
            : `${derivedFillPercent.toFixed(1)}%`)}
      </span>
    </div>

    {#if captureError}
      <div class="error" role="alert">{captureError}</div>
    {/if}
  </form>
{/if}
