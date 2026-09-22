import type {
  AppSettings,
  ArchiveRecordingStatus,
  ArchiveStatus,
  CleaningConfigRequest,
  OutputFormat,
  SessionSummary,
  TranscriptSession,
} from './types';

const BASE =
  (import.meta.env.VITE_API_URL as string | undefined) ?? `http://${window.location.hostname}:8010`;

// `fetch` throws a generic "Failed to fetch" TypeError both when the server is
// unreachable and when a CORS check blocks the response — the browser gives
// no way to tell those apart from the error alone. Probe the same URL with
// `mode: 'no-cors'`, which bypasses CORS enforcement: if that resolves, the
// server is up and the real problem is a CORS rejection; if it also throws,
// the server itself isn't reachable.
async function diagnoseFetchFailure(url: string): Promise<string> {
  const origin = window.location.origin;
  try {
    await fetch(url, { mode: 'no-cors' });
    return (
      `Could not reach the API at ${BASE} — the server responded, but the browser blocked it. ` +
      `This is almost always a CORS mismatch: check that TRANSCRIBE3_CORS_ORIGINS in .env includes ` +
      `"${origin}" (setting it REPLACES the built-in localhost defaults, so list every origin you use, ` +
      `comma-separated), then restart the API server.`
    );
  } catch {
    return (
      `Could not reach the API at ${BASE}. Check that the API server is running ` +
      `(uv run uvicorn transcribe3.api.main:app --reload --host 0.0.0.0 --port 8010) and that ` +
      `VITE_API_URL in src/ui/.env.local, if set, points at the right host. Restart the UI dev server ` +
      `after any .env change — it doesn't hot-reload env files.`
    );
  }
}

async function apiFetch(input: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(input, init);
  } catch {
    throw new Error(await diagnoseFetchFailure(input));
  }
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let message = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail?.error) message = body.detail.error;
      else if (typeof body?.detail === 'string') message = body.detail;
    } catch {
      // ignore parse errors
    }
    throw new Error(message);
  }
  return res.json() as Promise<T>;
}

export async function listSessions(): Promise<SessionSummary[]> {
  const res = await apiFetch(`${BASE}/sessions`);
  return handleResponse<SessionSummary[]>(res);
}

export async function getSession(sessionId: string): Promise<TranscriptSession> {
  const res = await apiFetch(`${BASE}/sessions/${sessionId}`);
  return handleResponse<TranscriptSession>(res);
}

export async function uploadTranscript(
  file: File,
  config: CleaningConfigRequest,
  signal?: AbortSignal,
): Promise<TranscriptSession> {
  const form = new FormData();
  form.append('file', file);
  if (config.model !== undefined) form.append('model', config.model);
  if (config.provider_id !== undefined) form.append('provider_id', config.provider_id);
  if (config.mode !== undefined) form.append('mode', config.mode);
  if (config.filler_words !== undefined) form.append('filler_words', config.filler_words);
  if (config.remove_false_starts !== undefined)
    form.append('remove_false_starts', String(config.remove_false_starts));
  if (config.handle_crosstalk !== undefined)
    form.append('handle_crosstalk', String(config.handle_crosstalk));
  if (config.low_confidence_threshold !== undefined)
    form.append('low_confidence_threshold', String(config.low_confidence_threshold));

  const res = await apiFetch(`${BASE}/sessions`, { method: 'POST', body: form, signal });
  return handleResponse<TranscriptSession>(res);
}

export async function updateSpeakerMap(
  sessionId: string,
  speakerMap: Record<string, string>,
): Promise<TranscriptSession> {
  const res = await apiFetch(`${BASE}/sessions/${sessionId}/speakers`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ speaker_map: speakerMap }),
  });
  return handleResponse<TranscriptSession>(res);
}

export async function renameSession(
  sessionId: string,
  displayName: string | null,
): Promise<TranscriptSession> {
  const res = await apiFetch(`${BASE}/sessions/${sessionId}/name`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ display_name: displayName }),
  });
  return handleResponse<TranscriptSession>(res);
}

export async function updateSegmentSpeaker(
  sessionId: string,
  segmentId: string,
  speaker: string,
  confidence: number,
): Promise<TranscriptSession> {
  const res = await apiFetch(`${BASE}/sessions/${sessionId}/segments/${segmentId}/speaker`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ speaker, confidence }),
  });
  return handleResponse<TranscriptSession>(res);
}

export async function updateSegmentText(
  sessionId: string,
  segmentId: string,
  text: string,
): Promise<TranscriptSession> {
  const res = await apiFetch(`${BASE}/sessions/${sessionId}/segments/${segmentId}/text`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  });
  return handleResponse<TranscriptSession>(res);
}

export async function deleteSession(sessionId: string): Promise<void> {
  const res = await apiFetch(`${BASE}/sessions/${sessionId}`, { method: 'DELETE' });
  await handleResponse<unknown>(res);
}

// The API answers with `warning` instead of an error when a provider can't be
// reached, so callers that want to tell "no models" apart from "provider down"
// need the whole payload, not just the list.
export async function listModelsDetailed(
  providerId?: string,
): Promise<{ models: string[]; warning?: string }> {
  const url = providerId ? `${BASE}/models?provider_id=${encodeURIComponent(providerId)}` : `${BASE}/models`;
  const res = await apiFetch(url);
  const data = await handleResponse<{ models: string[]; warning?: string }>(res);
  return { models: data.models ?? [], warning: data.warning };
}

export async function listModels(providerId?: string): Promise<string[]> {
  const { models } = await listModelsDetailed(providerId);
  return models;
}

export async function uploadAudio(
  file: File,
  whisperModel: string,
  backend: string,
  signal?: AbortSignal,
): Promise<TranscriptSession> {
  const form = new FormData();
  form.append('file', file);
  form.append('whisper_model', whisperModel);
  form.append('backend', backend);
  const res = await apiFetch(`${BASE}/sessions/upload-audio`, { method: 'POST', body: form, signal });
  return handleResponse<TranscriptSession>(res);
}

export function exportUrl(sessionId: string, format: OutputFormat): string {
  return `${BASE}/sessions/${sessionId}/export?format=${format}`;
}

export function audioUrl(sessionId: string): string {
  return `${BASE}/sessions/${sessionId}/audio`;
}

export async function getSettings(): Promise<AppSettings> {
  const res = await apiFetch(`${BASE}/settings`);
  return handleResponse<AppSettings>(res);
}

export async function updateSettings(settings: AppSettings): Promise<AppSettings> {
  const res = await apiFetch(`${BASE}/settings`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  });
  return handleResponse<AppSettings>(res);
}

export async function getArchiveStatus(): Promise<ArchiveStatus> {
  const res = await apiFetch(`${BASE}/archive`);
  return handleResponse<ArchiveStatus>(res);
}

export async function configureArchive(archiveDir: string): Promise<ArchiveStatus> {
  const res = await apiFetch(`${BASE}/archive/configuration`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ archive_dir: archiveDir }),
  });
  return handleResponse<ArchiveStatus>(res);
}

export async function archiveRecording(
  sessionId: string,
  removeLocal: boolean,
): Promise<ArchiveRecordingStatus> {
  const res = await apiFetch(`${BASE}/archive/${sessionId}/archive`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ remove_local: removeLocal }),
  });
  return handleResponse<ArchiveRecordingStatus>(res);
}

export async function restoreRecording(sessionId: string): Promise<ArchiveRecordingStatus> {
  const res = await apiFetch(`${BASE}/archive/${sessionId}/restore`, { method: 'POST' });
  return handleResponse<ArchiveRecordingStatus>(res);
}

export async function deleteLocalRecording(sessionId: string): Promise<ArchiveRecordingStatus> {
  const res = await apiFetch(`${BASE}/archive/${sessionId}/local-copy`, { method: 'DELETE' });
  return handleResponse<ArchiveRecordingStatus>(res);
}
