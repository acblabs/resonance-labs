import { normalizeCalibrationProfile } from './calibration';
import type { CalibrationProfile } from './types';

const DB_NAME = 'resonancelab-calibration';
const DB_VERSION = 1;
const PROFILE_STORE = 'profiles';

export type CalibrationStorageEstimate = {
  usageBytes: number | null;
  quotaBytes: number | null;
  usageRatio: number | null;
  persisted: boolean | null;
};

export function isCalibrationStorageAvailable(): boolean {
  return typeof indexedDB !== 'undefined';
}

export async function listCalibrationProfiles(): Promise<CalibrationProfile[]> {
  const db = await openDatabase();
  try {
    const profiles = await requestToPromise<CalibrationProfile[]>(
      db.transaction(PROFILE_STORE, 'readonly').objectStore(PROFILE_STORE).getAll()
    );
    return profiles
      .map(normalizeCalibrationProfile)
      .sort((left, right) => right.updatedAt.localeCompare(left.updatedAt));
  } finally {
    db.close();
  }
}

export async function getCalibrationProfile(id: string): Promise<CalibrationProfile | null> {
  const db = await openDatabase();
  try {
    const profile = await requestToPromise<CalibrationProfile | undefined>(
      db.transaction(PROFILE_STORE, 'readonly').objectStore(PROFILE_STORE).get(id)
    );
    return profile ? normalizeCalibrationProfile(profile) : null;
  } finally {
    db.close();
  }
}

export async function saveCalibrationProfile(profile: CalibrationProfile): Promise<void> {
  const db = await openDatabase();
  try {
    const transaction = db.transaction(PROFILE_STORE, 'readwrite');
    transaction.objectStore(PROFILE_STORE).put(normalizeCalibrationProfile(profile));
    await transactionToPromise(transaction);
  } catch (error) {
    throw storageError(error, 'Calibration profile could not be saved locally.');
  } finally {
    db.close();
  }
}

export async function deleteCalibrationProfile(id: string): Promise<void> {
  const db = await openDatabase();
  try {
    const transaction = db.transaction(PROFILE_STORE, 'readwrite');
    transaction.objectStore(PROFILE_STORE).delete(id);
    await transactionToPromise(transaction);
  } catch (error) {
    throw storageError(error, 'Calibration profile could not be deleted locally.');
  } finally {
    db.close();
  }
}

export async function getCalibrationStorageEstimate(): Promise<CalibrationStorageEstimate> {
  if (typeof navigator === 'undefined' || !navigator.storage?.estimate) {
    return {
      usageBytes: null,
      quotaBytes: null,
      usageRatio: null,
      persisted: null
    };
  }

  const [estimate, persisted] = await Promise.all([
    navigator.storage.estimate(),
    navigator.storage.persisted ? navigator.storage.persisted() : Promise.resolve(null)
  ]);
  const usageBytes = estimate.usage ?? null;
  const quotaBytes = estimate.quota ?? null;
  return {
    usageBytes,
    quotaBytes,
    usageRatio:
      usageBytes !== null && quotaBytes !== null && quotaBytes > 0 ? usageBytes / quotaBytes : null,
    persisted
  };
}

function openDatabase(): Promise<IDBDatabase> {
  if (!isCalibrationStorageAvailable()) {
    return Promise.reject(new Error('IndexedDB is not available in this browser.'));
  }

  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);

    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(PROFILE_STORE)) {
        const store = db.createObjectStore(PROFILE_STORE, { keyPath: 'id' });
        store.createIndex('updatedAt', 'updatedAt', { unique: false });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(storageError(request.error, 'Failed to open calibration DB.'));
    request.onblocked = () =>
      reject(new Error('Calibration DB upgrade was blocked by another open tab.'));
  });
}

function requestToPromise<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(storageError(request.error, 'IndexedDB request failed.'));
  });
}

function transactionToPromise(transaction: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve();
    transaction.onerror = () =>
      reject(storageError(transaction.error, 'Calibration DB transaction failed.'));
    transaction.onabort = () =>
      reject(storageError(transaction.error, 'Calibration DB transaction aborted.'));
  });
}

function storageError(error: unknown, fallback: string): Error {
  if (error instanceof DOMException) {
    if (error.name === 'QuotaExceededError') {
      return new Error('Local calibration storage quota is full. Export or delete profiles.');
    }
    if (error.name === 'InvalidStateError') {
      return new Error('Local calibration storage is unavailable in this browser mode.');
    }
    return new Error(`${fallback} ${error.name}: ${error.message}`);
  }
  if (error instanceof Error) {
    return error;
  }
  return new Error(fallback);
}
