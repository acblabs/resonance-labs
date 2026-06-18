<script lang="ts">
  import { onMount } from 'svelte';
  import type { AnalysisResponse } from '$lib/audio/types';
  import {
    CALIBRATION_ANCHORS,
    FREE_AIR_REFERENCE_LABEL,
    anchorCount,
    createCalibrationAnchor,
    createCalibrationProfile,
    createFreeAirReference,
    estimateFillLevel,
    exportCalibrationProfile,
    importCalibrationProfile,
    profileObservationCount,
    renameCalibrationProfile,
    withCalibrationAnchor,
    withFreeAirReference
  } from '$lib/calibration/calibration';
  import {
    deleteCalibrationProfile,
    getCalibrationStorageEstimate,
    isCalibrationStorageAvailable,
    listCalibrationProfiles,
    saveCalibrationProfile
  } from '$lib/calibration/storage';
  import type { CalibrationStorageEstimate } from '$lib/calibration/storage';
  import type {
    CalibrationAnchor,
    CalibrationAnchorKind,
    CalibrationEstimate,
    CalibrationProfile,
    CalibrationReference
  } from '$lib/calibration/types';

  export let result: AnalysisResponse | null = null;
  export let selectedProfile: CalibrationProfile | null = null;
  export let calibrationEstimate: CalibrationEstimate | null = null;
  export let selectedAnchorCount = 0;
  export let selectedObservationCount = 0;

  let calibrationProfiles: CalibrationProfile[] = [];
  let selectedProfileId = '';
  let profileNameDraft = 'Local glass profile';
  let loadingProfiles = true;
  let savingCalibration = false;
  let calibrationStatus = 'Loading profiles';
  let calibrationError = '';
  let storageEstimate: CalibrationStorageEstimate | null = null;
  let calibrationEstimateCacheKey = '';
  let importInput: HTMLInputElement;

  onMount(loadProfiles);

  async function loadProfiles(): Promise<void> {
    loadingProfiles = true;
    calibrationError = '';

    if (!isCalibrationStorageAvailable()) {
      calibrationStatus = 'IndexedDB unavailable';
      calibrationError = 'This browser does not expose local calibration storage.';
      loadingProfiles = false;
      return;
    }

    try {
      let profiles = await listCalibrationProfiles();
      if (profiles.length === 0) {
        const profile = createCalibrationProfile('Local glass profile');
        await saveCalibrationProfile(profile);
        profiles = [profile];
      }
      setProfiles(profiles, selectedProfileId || profiles[0]?.id || '');
      await refreshStorageEstimate();
      calibrationStatus = 'Profiles local';
    } catch (profileError) {
      calibrationError = profileError instanceof Error ? profileError.message : String(profileError);
      calibrationStatus = 'Storage error';
    } finally {
      loadingProfiles = false;
    }
  }

  async function refreshStorageEstimate(): Promise<void> {
    try {
      storageEstimate = await getCalibrationStorageEstimate();
    } catch (storageError) {
      console.warn(storageError);
      storageEstimate = null;
    }
  }

  function setProfiles(profiles: CalibrationProfile[], activeId: string): void {
    calibrationProfiles = profiles;
    selectedProfileId = profiles.some((profile) => profile.id === activeId)
      ? activeId
      : profiles[0]?.id || '';
    selectedProfile =
      calibrationProfiles.find((profile) => profile.id === selectedProfileId) ?? null;
    profileNameDraft = selectedProfile?.name ?? 'Local glass profile';
  }

  function selectProfile(profileId: string): void {
    selectedProfileId = profileId;
    selectedProfile =
      calibrationProfiles.find((profile) => profile.id === selectedProfileId) ?? null;
    profileNameDraft = selectedProfile?.name ?? 'Local glass profile';
    calibrationStatus = selectedProfile ? 'Profile selected' : 'No profile selected';
  }

  async function createProfile(): Promise<void> {
    savingCalibration = true;
    calibrationError = '';
    try {
      const profile = createCalibrationProfile(profileNameDraft || 'Local glass profile');
      await saveCalibrationProfile(profile);
      setProfiles([profile, ...calibrationProfiles], profile.id);
      await refreshStorageEstimate();
      calibrationStatus = 'Profile created';
    } catch (profileError) {
      calibrationError = profileError instanceof Error ? profileError.message : String(profileError);
    } finally {
      savingCalibration = false;
    }
  }

  async function saveProfileName(): Promise<void> {
    if (!selectedProfile) {
      return;
    }
    savingCalibration = true;
    calibrationError = '';
    try {
      const profile = renameCalibrationProfile(selectedProfile, profileNameDraft);
      await saveCalibrationProfile(profile);
      replaceProfile(profile);
      await refreshStorageEstimate();
      calibrationStatus = 'Profile renamed';
    } catch (profileError) {
      calibrationError = profileError instanceof Error ? profileError.message : String(profileError);
    } finally {
      savingCalibration = false;
    }
  }

  async function removeProfile(): Promise<void> {
    if (!selectedProfile) {
      return;
    }
    const confirmed = window.confirm(`Delete "${selectedProfile.name}" and its local anchors?`);
    if (!confirmed) {
      return;
    }

    savingCalibration = true;
    calibrationError = '';
    try {
      await deleteCalibrationProfile(selectedProfile.id);
      let remaining = calibrationProfiles.filter((profile) => profile.id !== selectedProfileId);
      if (remaining.length === 0) {
        const profile = createCalibrationProfile('Local glass profile');
        await saveCalibrationProfile(profile);
        remaining = [profile];
      }
      setProfiles(remaining, remaining[0]?.id || '');
      await refreshStorageEstimate();
      calibrationStatus = 'Profile deleted';
    } catch (profileError) {
      calibrationError = profileError instanceof Error ? profileError.message : String(profileError);
    } finally {
      savingCalibration = false;
    }
  }

  async function saveCurrentAsAnchor(kind: CalibrationAnchorKind): Promise<void> {
    if (!selectedProfile || !result) {
      return;
    }
    savingCalibration = true;
    calibrationError = '';
    try {
      const anchor = createCalibrationAnchor(kind, result);
      const profile = withCalibrationAnchor(selectedProfile, anchor);
      await saveCalibrationProfile(profile);
      replaceProfile(profile);
      await refreshStorageEstimate();
      calibrationStatus = `${anchor.label} repeat saved (n=${profile.anchors[kind]?.sampleCount ?? 1})`;
    } catch (anchorError) {
      calibrationError = anchorError instanceof Error ? anchorError.message : String(anchorError);
    } finally {
      savingCalibration = false;
    }
  }

  async function saveCurrentAsFreeAirReference(): Promise<void> {
    if (!selectedProfile || !result) {
      return;
    }
    savingCalibration = true;
    calibrationError = '';
    try {
      const reference = createFreeAirReference(result);
      const profile = withFreeAirReference(selectedProfile, reference);
      await saveCalibrationProfile(profile);
      replaceProfile(profile);
      await refreshStorageEstimate();
      calibrationStatus = `${FREE_AIR_REFERENCE_LABEL} repeat saved (n=${profile.freeAirReference?.sampleCount ?? 1})`;
    } catch (referenceError) {
      calibrationError =
        referenceError instanceof Error ? referenceError.message : String(referenceError);
    } finally {
      savingCalibration = false;
    }
  }

  function exportSelectedProfile(): void {
    if (!selectedProfile) {
      return;
    }
    const blob = new Blob([exportCalibrationProfile(selectedProfile)], {
      type: 'application/json'
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${selectedProfile.name.replace(/[^a-z0-9_-]+/gi, '-').toLowerCase()}-calibration.json`;
    link.click();
    URL.revokeObjectURL(url);
    calibrationStatus = 'Profile exported';
  }

  async function importProfileFile(event: Event): Promise<void> {
    const input = event.currentTarget as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) {
      return;
    }
    savingCalibration = true;
    calibrationError = '';
    try {
      const profile = importCalibrationProfile(await file.text());
      await saveCalibrationProfile(profile);
      setProfiles([profile, ...calibrationProfiles], profile.id);
      await refreshStorageEstimate();
      calibrationStatus = 'Profile imported';
    } catch (importError) {
      calibrationError = importError instanceof Error ? importError.message : String(importError);
      calibrationStatus = 'Import failed';
    } finally {
      input.value = '';
      savingCalibration = false;
    }
  }

  function replaceProfile(profile: CalibrationProfile): void {
    const profiles = calibrationProfiles
      .map((candidate) => (candidate.id === profile.id ? profile : candidate))
      .sort((left, right) => right.updatedAt.localeCompare(left.updatedAt));
    setProfiles(profiles, profile.id);
  }

  function formatHz(value: number | null | undefined): string {
    if (value === null || value === undefined || !Number.isFinite(value)) {
      return '--';
    }
    if (value >= 1000) {
      return `${(value / 1000).toFixed(value >= 10000 ? 1 : 2)} kHz`;
    }
    return `${Math.round(value)} Hz`;
  }

  function anchorFor(kind: CalibrationAnchorKind): CalibrationAnchor | null {
    return selectedProfile?.anchors[kind] ?? null;
  }

  function freeAirReference(): CalibrationReference | null {
    return selectedProfile?.freeAirReference ?? null;
  }

  function formatAnchorStatus(kind: CalibrationAnchorKind): string {
    const anchor = anchorFor(kind);
    if (!anchor) {
      return 'Open';
    }
    return formatHz(anchor.featureVector.summary.primaryPeakHz);
  }

  function formatRepeatCount(count: number | null | undefined): string {
    if (!count) {
      return 'n=0';
    }
    return `n=${count}`;
  }

  function formatStorage(): string {
    if (!storageEstimate || storageEstimate.usageBytes === null) {
      return 'Storage --';
    }
    const usage = formatBytes(storageEstimate.usageBytes);
    const quota = storageEstimate.quotaBytes === null ? '--' : formatBytes(storageEstimate.quotaBytes);
    return `Storage ${usage}/${quota}`;
  }

  function formatBytes(bytes: number): string {
    if (bytes >= 1024 * 1024) {
      return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    }
    return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  }

  function currentEstimateCacheKey(): string {
    const resultKey = result?.analysis_id ?? 'no-result';
    const profileKey = selectedProfile
      ? `${selectedProfile.id}:${selectedProfile.updatedAt}:${selectedProfile.schemaVersion}`
      : 'no-profile';
    return `${resultKey}|${profileKey}`;
  }

  $: selectedAnchorCount = selectedProfile ? anchorCount(selectedProfile) : 0;
  $: selectedObservationCount = selectedProfile ? profileObservationCount(selectedProfile) : 0;
  $: {
    const cacheKey = currentEstimateCacheKey();
    if (cacheKey !== calibrationEstimateCacheKey) {
      calibrationEstimateCacheKey = cacheKey;
      calibrationEstimate = result && selectedProfile ? estimateFillLevel(result, selectedProfile) : null;
    }
  }
</script>

<div class="calibration-block" aria-label="Calibration profile workflow">
  <div class="section-heading">
    <h2>Calibration</h2>
    <span>
      {selectedProfile ? `${selectedAnchorCount}/3 anchors, ${selectedObservationCount} samples` : '--'}
    </span>
  </div>

  <div class="profile-row">
    <select
      aria-label="Calibration profile"
      value={selectedProfileId}
      disabled={loadingProfiles || savingCalibration || calibrationProfiles.length === 0}
      on:change={(event) => selectProfile(event.currentTarget.value)}
    >
      {#each calibrationProfiles as profile}
        <option value={profile.id}>{profile.name}</option>
      {/each}
    </select>
    <button
      class="secondary-button"
      type="button"
      disabled={loadingProfiles || savingCalibration}
      on:click={createProfile}
    >
      New
    </button>
    <button
      class="secondary-button"
      type="button"
      disabled={!selectedProfile || loadingProfiles || savingCalibration}
      on:click={saveProfileName}
    >
      Rename
    </button>
    <button
      class="danger-button"
      type="button"
      disabled={!selectedProfile || loadingProfiles || savingCalibration}
      on:click={removeProfile}
    >
      Delete
    </button>
  </div>

  <div class="profile-tools">
    <button
      class="secondary-button"
      type="button"
      disabled={!selectedProfile || loadingProfiles || savingCalibration}
      on:click={exportSelectedProfile}
    >
      Export
    </button>
    <button
      class="secondary-button"
      type="button"
      disabled={loadingProfiles || savingCalibration}
      on:click={() => importInput.click()}
    >
      Import
    </button>
    <input
      bind:this={importInput}
      class="hidden-input"
      type="file"
      accept="application/json,.json"
      on:change={importProfileFile}
    />
    <span class="storage-line">{formatStorage()}</span>
  </div>

  <div class="field">
    <label for="profile-name">Profile name</label>
    <input
      id="profile-name"
      type="text"
      value={profileNameDraft}
      disabled={loadingProfiles || savingCalibration}
      on:input={(event) => (profileNameDraft = event.currentTarget.value)}
    />
  </div>

  <div class="anchor-grid">
    {#each CALIBRATION_ANCHORS as anchor}
      <button
        class="anchor-button"
        class:anchor-saved={Boolean(anchorFor(anchor.kind))}
        type="button"
        disabled={!selectedProfile || !result || savingCalibration}
        on:click={() => saveCurrentAsAnchor(anchor.kind)}
      >
        <span>{anchor.label}</span>
        <strong>{formatAnchorStatus(anchor.kind)}</strong>
        <em>{formatRepeatCount(anchorFor(anchor.kind)?.sampleCount)}</em>
      </button>
    {/each}
    <button
      class="anchor-button reference-button"
      class:anchor-saved={Boolean(freeAirReference())}
      type="button"
      disabled={!selectedProfile || !result || savingCalibration}
      on:click={saveCurrentAsFreeAirReference}
    >
      <span>{FREE_AIR_REFERENCE_LABEL}</span>
      <strong>{formatHz(freeAirReference()?.featureVector.summary.primaryPeakHz)}</strong>
      <em>{formatRepeatCount(freeAirReference()?.sampleCount)}</em>
    </button>
  </div>

  <span class="status-line">{calibrationStatus}</span>

  {#if calibrationError}
    <div class="error" role="alert">{calibrationError}</div>
  {/if}
</div>
