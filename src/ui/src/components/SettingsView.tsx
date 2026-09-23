import { useEffect, useState } from 'react'
import { getSettings, listModelsDetailed, updateSettings } from '../api'
import { AUDIO_BACKENDS, WHISPER_MODELS } from '../audioOptions'
import type { AppSettings, LLMProtocol, LLMProviderConfig } from '../types'

interface Props {
  onBack: () => void
}

const PROTOCOLS: { value: LLMProtocol; label: string }[] = [
  { value: 'ollama', label: 'Ollama' },
  { value: 'openai_compatible', label: 'OpenAI v1' },
]

const TIMEOUT_PRESETS = [60, 120, 300, 600, 1800]

type ModelState = {
  models: string[]
  loading: boolean
  /** Set when the provider answered but couldn't be reached, or the call failed. */
  problem: string | null
}

function slugify(label: string): string {
  return label.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '')
}

function uniqueId(base: string, existing: string[]): string {
  const slug = slugify(base) || 'provider'
  if (!existing.includes(slug)) return slug
  let n = 2
  while (existing.includes(`${slug}-${n}`)) n += 1
  return `${slug}-${n}`
}

export default function SettingsView({ onBack }: Props) {
  const [settings, setSettings] = useState<AppSettings | null>(null)
  // The last state the server confirmed. Model listing and connection checks
  // always run against the *saved* provider config, so edits in the form aren't
  // live until they're saved — this is what lets us say so in the UI.
  const [savedSettings, setSavedSettings] = useState<AppSettings | null>(null)
  const [modelState, setModelState] = useState<ModelState>({
    models: [],
    loading: true,
    problem: null,
  })
  const [checks, setChecks] = useState<Record<string, string>>({})
  // Rows whose id is still the generated placeholder, so it may follow the name.
  const [autoIdRows, setAutoIdRows] = useState<Set<number>>(new Set())
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getSettings()
      .then((s) => {
        setSettings(s)
        setSavedSettings(s)
        void loadModels(s.default_provider_id)
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : 'Failed to load settings')
        setModelState({ models: [], loading: false, problem: null })
      })
  }, [])

  /** Fetch the model list for `providerId`; when `pickFirst`, replace a default
   *  model the new provider doesn't offer instead of silently keeping a stale one. */
  async function loadModels(providerId: string, pickFirst = false): Promise<void> {
    if (!providerId) {
      setModelState({ models: [], loading: false, problem: null })
      return
    }
    setModelState({ models: [], loading: true, problem: null })
    try {
      const { models, warning } = await listModelsDetailed(providerId)
      setModelState({ models, loading: false, problem: warning ?? null })
      if (pickFirst && models.length > 0) {
        setSettings((prev) =>
          prev && !models.includes(prev.default_model)
            ? { ...prev, default_model: models[0]! }
            : prev,
        )
      }
    } catch (e) {
      setModelState({
        models: [],
        loading: false,
        problem: e instanceof Error ? e.message : 'Could not list models',
      })
    }
  }

  function handleDefaultProviderChange(providerId: string) {
    if (!settings) return
    setSettings({ ...settings, default_provider_id: providerId })
    void loadModels(providerId, true)
  }

  function updateProvider(index: number, patch: Partial<LLMProviderConfig>) {
    if (!settings) return
    const previous = settings.llm_providers[index]!
    const effective = { ...patch }

    // A provider's id decides which environment variable holds its bearer token
    // (TRANSCRIBE3_LLM_API_KEY_<ID>), so an id left at the "provider" placeholder
    // while the name says "oMLX" sends people to the wrong variable. Keep the id
    // in step with the name until someone edits the id by hand.
    if (patch.label !== undefined && patch.id === undefined && autoIdRows.has(index)) {
      const others = settings.llm_providers.filter((_, i) => i !== index).map((p) => p.id)
      effective.id = uniqueId(patch.label, others)
    }
    if (patch.id !== undefined) {
      setAutoIdRows((prev) => {
        const next = new Set(prev)
        next.delete(index)
        return next
      })
    }

    const providers = settings.llm_providers.map((p, i) => (i === index ? { ...p, ...effective } : p))
    const defaultProviderId =
      settings.default_provider_id === previous.id && effective.id !== undefined
        ? effective.id
        : settings.default_provider_id
    setSettings({ ...settings, llm_providers: providers, default_provider_id: defaultProviderId })
  }

  function addProvider() {
    if (!settings) return
    setAutoIdRows((prev) => new Set(prev).add(settings.llm_providers.length))
    const id = uniqueId('provider', settings.llm_providers.map((p) => p.id))
    const provider: LLMProviderConfig = {
      id,
      label: 'New provider',
      protocol: 'openai_compatible',
      base_url: 'http://127.0.0.1:8000/v1',
      enabled: true,
    }
    setSettings({ ...settings, llm_providers: [...settings.llm_providers, provider] })
  }

  function removeProvider(index: number) {
    if (!settings) return
    const removed = settings.llm_providers[index]!
    const providers = settings.llm_providers.filter((_, i) => i !== index)
    let defaultProviderId = settings.default_provider_id
    if (removed.id === defaultProviderId) {
      defaultProviderId = providers.find((p) => p.enabled)?.id ?? providers[0]?.id ?? ''
      void loadModels(defaultProviderId, true)
    }
    setSettings({ ...settings, llm_providers: providers, default_provider_id: defaultProviderId })
  }

  async function checkProvider(provider: LLMProviderConfig) {
    setChecks((prev) => ({ ...prev, [provider.id]: 'Checking…' }))
    try {
      const { models, warning } = await listModelsDetailed(provider.id)
      setChecks((prev) => ({
        ...prev,
        [provider.id]: warning
          ? `✗ ${warning}`
          : `✓ reachable — ${models.length} model${models.length === 1 ? '' : 's'}`,
      }))
    } catch (e) {
      setChecks((prev) => ({
        ...prev,
        [provider.id]: `✗ ${e instanceof Error ? e.message : 'check failed'}`,
      }))
    }
  }

  /** True while this provider's row differs from what the server has stored. */
  function isProviderUnsaved(index: number): boolean {
    if (!settings || !savedSettings) return true
    const current = settings.llm_providers[index]
    const stored = savedSettings.llm_providers[index]
    if (!current || !stored) return true
    return JSON.stringify(current) !== JSON.stringify(stored)
  }

  const providers = settings?.llm_providers ?? []
  const providerIds = providers.map((p) => p.id)
  const idCounts = providerIds.reduce<Record<string, number>>((acc, id) => {
    acc[id] = (acc[id] ?? 0) + 1
    return acc
  }, {})
  const defaultProvider = providers.find((p) => p.id === settings?.default_provider_id) ?? null
  const validationError =
    providerIds.length === 0
      ? 'Add at least one LLM provider.'
      : providerIds.some((id) => !id.trim())
      ? 'Every provider needs a non-empty id.'
      : Object.values(idCounts).some((n) => n > 1)
      ? 'Provider ids must be unique.'
      : !defaultProvider
      ? 'Pick which provider to use by default.'
      : !defaultProvider.enabled
      ? `"${defaultProvider.label}" is the default provider, so it has to stay enabled.`
      : null

  async function handleSave() {
    if (!settings || validationError) return
    setSaving(true)
    setError(null)
    setSaved(false)
    try {
      const updated = await updateSettings(settings)
      setSettings(updated)
      setSavedSettings(updated)
      setChecks({})
      void loadModels(updated.default_provider_id)
      setSaved(true)
      setTimeout(() => setSaved(false), 2500)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  if (!settings) return <p>{error ?? 'Loading settings…'}</p>

  const { models, loading: modelsLoading, problem: modelProblem } = modelState
  const modelMissing =
    !modelsLoading &&
    !modelProblem &&
    models.length > 0 &&
    !models.includes(settings.default_model)

  return (
    <div className="settings-view">
      <h2>Settings</h2>

      {/* ── What runs the cleaning: provider + model, side by side ── */}
      <section className="panel settings-section">
        <h3>Default language model</h3>
        <p className="settings-hint">
          Used for transcript cleaning and speaker attribution. Individual sessions can
          override both on the New Session screen.
        </p>

        <div className="settings-fields">
          <div className="settings-field">
            <span className="settings-label">Provider</span>
            <select
              value={settings.default_provider_id}
              onChange={(e) => handleDefaultProviderChange(e.target.value)}
            >
              {providers.length === 0 && <option value="">No providers configured</option>}
              {providers.map((p) => (
                <option key={p.id} value={p.id} disabled={!p.enabled}>
                  {p.label || p.id}
                  {p.enabled ? '' : ' (disabled)'}
                </option>
              ))}
            </select>
          </div>

          <div className="settings-field">
            <span className="settings-label">Model</span>
            <div className="settings-inline">
              {models.length > 0 ? (
                <select
                  value={settings.default_model}
                  onChange={(e) => setSettings({ ...settings, default_model: e.target.value })}
                >
                  {modelMissing && (
                    <option value={settings.default_model}>
                      {settings.default_model} (not installed)
                    </option>
                  )}
                  {models.map((m) => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
              ) : (
                // With no list to pick from, let the name be typed rather than
                // trapping the user on whatever was saved last.
                <input
                  type="text"
                  value={settings.default_model}
                  placeholder="Model name"
                  onChange={(e) => setSettings({ ...settings, default_model: e.target.value })}
                />
              )}
              <button
                type="button"
                onClick={() => void loadModels(settings.default_provider_id)}
                disabled={modelsLoading || !settings.default_provider_id}
                title="Reload the model list from the provider"
              >
                ↻
              </button>
            </div>
          </div>
        </div>

        <p className="settings-hint settings-hint--tight">
          {modelsLoading ? (
            <span className="settings-status">
              <span className="spinner" />
              Loading models from {defaultProvider?.label ?? 'the provider'}…
            </span>
          ) : modelProblem ? (
            // The API's warning already names the cause and the fix; adding our own
            // guess ("check the base URL") on top of a 401 just misdirects.
            <span className="settings-status settings-status--error">{modelProblem}</span>
          ) : models.length === 0 ? (
            <span className="settings-status settings-status--warn">
              {defaultProvider?.label ?? 'This provider'} reports no installed models.
            </span>
          ) : modelMissing ? (
            <span className="settings-status settings-status--warn">
              {defaultProvider?.label} doesn't offer "{settings.default_model}" — pick one of
              its {models.length} models.
            </span>
          ) : (
            <span className="settings-status settings-status--ok">
              ✓ {models.length} model{models.length === 1 ? '' : 's'} available from{' '}
              {defaultProvider?.label}.
            </span>
          )}
        </p>
      </section>

      {/* ── Audio upload defaults ── */}
      <section className="panel settings-section">
        <h3>Default audio processing</h3>
        <p className="settings-hint">
          Preselected on the New Session screen for audio uploads. An individual
          upload can still override both.
        </p>

        <div className="settings-fields">
          <div className="settings-field">
            <span className="settings-label">Transcription backend</span>
            <select
              value={settings.default_transcription_backend}
              onChange={(e) =>
                setSettings({ ...settings, default_transcription_backend: e.target.value })
              }
            >
              {AUDIO_BACKENDS.map((b) => (
                <option key={b.value} value={b.value}>{b.label}</option>
              ))}
            </select>
          </div>

          <div className="settings-field">
            <span className="settings-label">Whisper model</span>
            <select
              value={settings.default_whisper_model}
              onChange={(e) => setSettings({ ...settings, default_whisper_model: e.target.value })}
            >
              {WHISPER_MODELS.map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          </div>
        </div>
      </section>

      {/* ── Provider registry ── */}
      <section className="panel settings-section">
        <h3>Providers</h3>
        <p className="settings-hint">
          Any server speaking the Ollama or OpenAI v1 protocol (LM Studio, vLLM, llama.cpp,
          a hosted API, …) can be added here — no code changes needed. A provider needing a
          bearer token reads it from the environment variable shown on its row; set that in
          .env and restart the API. Check tests a saved provider — save first for edits to
          take effect.
        </p>

        <div className="provider-grid">
          <span className="provider-grid-head provider-grid-head--center">Default</span>
          <span className="provider-grid-head">Name</span>
          <span className="provider-grid-head">Protocol</span>
          <span className="provider-grid-head">Base URL</span>
          <span className="provider-grid-head">ID</span>
          <span className="provider-grid-head provider-grid-head--center">On</span>
          <span className="provider-grid-head" />

          {providers.map((provider, i) => {
            const unsaved = isProviderUnsaved(i)
            const check = checks[provider.id]
            return (
              <div key={i} style={{ display: 'contents' }}>
                {i > 0 && <div className="provider-rule" />}
                <div className="provider-toggle">
                  <input
                    type="radio"
                    name="default_provider"
                    checked={provider.id === settings.default_provider_id}
                    disabled={!provider.id.trim() || !provider.enabled}
                    onChange={() => handleDefaultProviderChange(provider.id)}
                    aria-label={`Use ${provider.label || provider.id} by default`}
                  />
                </div>
                <input
                  type="text"
                  value={provider.label}
                  placeholder="Display name"
                  aria-label="Provider name"
                  onChange={(e) => updateProvider(i, { label: e.target.value })}
                />
                <select
                  value={provider.protocol}
                  aria-label="Protocol"
                  onChange={(e) => updateProvider(i, { protocol: e.target.value as LLMProtocol })}
                >
                  {PROTOCOLS.map((p) => (
                    <option key={p.value} value={p.value}>{p.label}</option>
                  ))}
                </select>
                <input
                  type="text"
                  value={provider.base_url}
                  placeholder="http://127.0.0.1:8090/v1"
                  aria-label="Base URL"
                  onChange={(e) => updateProvider(i, { base_url: e.target.value })}
                />
                <input
                  type="text"
                  className="provider-id"
                  value={provider.id}
                  placeholder="id"
                  aria-label="Provider id"
                  onChange={(e) => updateProvider(i, { id: e.target.value })}
                />
                <div className="provider-toggle">
                  <input
                    type="checkbox"
                    checked={provider.enabled}
                    aria-label="Enabled"
                    onChange={(e) => updateProvider(i, { enabled: e.target.checked })}
                  />
                </div>
                <div className="provider-actions">
                  <button
                    type="button"
                    onClick={() => void checkProvider(provider)}
                    disabled={unsaved || !provider.id.trim()}
                    title={
                      unsaved
                        ? 'Save settings first — the check uses the stored configuration'
                        : 'Ask this provider for its model list'
                    }
                  >
                    Check
                  </button>
                  <button
                    type="button"
                    className="btn-danger"
                    onClick={() => removeProvider(i)}
                    title="Remove this provider"
                  >
                    ✕
                  </button>
                </div>
                <p className="provider-note settings-status">
                  {/* The token lives in the environment, so the row names the exact
                      variable instead of leaving people to derive it from the id. */}
                  <span title="Bearer token is read from this environment variable">
                    🔑 <code>{provider.api_key_env_var ?? '—'}</code>{' '}
                    {provider.api_key_set ? (
                      <span className="settings-status--ok">set</span>
                    ) : (
                      <span className="settings-status--muted">not set</span>
                    )}
                  </span>
                  {unsaved && <span className="provider-note-sep">Unsaved changes</span>}
                  {check && (
                    <span
                      className={
                        check.startsWith('✓')
                          ? 'provider-note-sep settings-status--ok'
                          : check.startsWith('✗')
                          ? 'provider-note-sep settings-status--error'
                          : 'provider-note-sep'
                      }
                    >
                      {check}
                    </span>
                  )}
                </p>
              </div>
            )
          })}
        </div>

        <div className="settings-actions" style={{ marginTop: 12 }}>
          <button type="button" onClick={addProvider}>+ Add provider</button>
        </div>

        {validationError && (
          <p className="settings-status settings-status--error" style={{ marginTop: 8 }}>
            {validationError}
          </p>
        )}
      </section>

      {/* ── Everything that tunes the run ── */}
      <section className="panel settings-section">
        <h3>Processing</h3>

        <div className="stage-toggles">
          <label className="stage-toggle">
            <input
              type="checkbox"
              checked={settings.run_cleaning}
              onChange={(e) => setSettings({ ...settings, run_cleaning: e.target.checked })}
            />
            <span>
              <strong>Clean transcript text</strong>
              <span className="settings-hint settings-hint--tight">
                Filler words, false starts and crosstalk handling.{' '}
                <strong>Rule-based and fast - no LLM.</strong> Off keeps every word
                exactly as transcribed.
              </span>
            </span>
          </label>

          <label className="stage-toggle">
            <input
              type="checkbox"
              checked={settings.run_attribution}
              onChange={(e) => setSettings({ ...settings, run_attribution: e.target.checked })}
            />
            <span>
              <strong>Validate speaker attribution with the LLM</strong>
              <span className="settings-hint settings-hint--tight">
                One LLM call per 10-segment window, so this is usually the longest stage of
                a long recording. Off keeps the diarization speaker labels as they are and
                leaves confidence unscored.
              </span>
            </span>
          </label>
        </div>

        {!settings.run_attribution && (
          <p className="settings-status settings-status--warn" style={{ margin: '0 0 12px' }}>
            With attribution off, nothing scores segment confidence — the low-confidence
            threshold below has no effect on new runs.
          </p>
        )}

        <div className="settings-fields">
          <div className="settings-field">
            <label className="settings-label" htmlFor="llm_timeout">
              Request timeout (seconds)
            </label>
            <div className="settings-inline">
              <input
                id="llm_timeout"
                type="number"
                min={1}
                max={1800}
                step={5}
                value={settings.llm_timeout}
                style={{ width: 90 }}
                onChange={(e) => {
                  const v = Math.min(1800, Math.max(1, Number(e.target.value)))
                  setSettings({ ...settings, llm_timeout: v })
                }}
              />
              <div className="settings-presets">
                {TIMEOUT_PRESETS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    className={settings.llm_timeout === s ? 'is-active' : undefined}
                    onClick={() => setSettings({ ...settings, llm_timeout: s })}
                  >
                    {s >= 60 ? `${s / 60}m` : `${s}s`}
                  </button>
                ))}
              </div>
            </div>
            <p className="settings-hint settings-hint--tight">
              How long to wait for one LLM request (1–1800 s), for every provider. Large
              models on first load may need 2–5 min; slow CPU-only inference more.
            </p>
          </div>

          <div className="settings-field">
            <label className="settings-label" htmlFor="conf_threshold">
              Low-confidence threshold (0–1)
            </label>
            <div className="settings-slider">
              <input
                id="conf_threshold"
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={settings.low_confidence_threshold}
                onChange={(e) =>
                  setSettings({ ...settings, low_confidence_threshold: Number(e.target.value) })
                }
              />
              <input
                type="number"
                min={0}
                max={1}
                step={0.05}
                value={settings.low_confidence_threshold}
                onChange={(e) => {
                  const v = Math.min(1, Math.max(0, Number(e.target.value)))
                  setSettings({ ...settings, low_confidence_threshold: v })
                }}
              />
            </div>
            <p className="settings-hint settings-hint--tight">
              Segments below this confidence are flagged for human review.
            </p>
          </div>
        </div>
      </section>

      <p className="settings-hint">
        Recording storage and the archive drive are configured under Admin.
      </p>

      {error && <div className="error-msg">{error}</div>}

      <div className="settings-actions">
        <button
          className="btn btn-primary"
          disabled={saving || !!validationError}
          onClick={handleSave}
        >
          {saving ? 'Saving…' : saved ? '✓ Saved' : 'Save settings'}
        </button>
        <button onClick={onBack}>Cancel</button>
      </div>
    </div>
  )
}
