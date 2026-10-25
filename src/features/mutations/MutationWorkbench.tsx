import { useEffect, useState } from 'react';
import {
  ArrowDownToLine,
  ArrowRight,
  Check,
  ChevronDown,
  CircleHelp,
  Database,
  Dices,
  FlaskConical,
  Layers3,
  Plus,
  Save,
  Search,
  SlidersHorizontal,
  Sparkles,
  TableProperties,
} from 'lucide-react';
import { sampleSnapshot } from '../evidence/evidence';
import { WorkspaceSidebar } from '../../shared/components/WorkspaceSidebar';
import type { EvidenceSnapshot, MetricDefinition } from '../evidence/evidence';
import { metricDefinitions } from '../evidence/metricDefinitions';
import { createEvidenceSnapshot, listEvidenceSnapshots, listMetricDefinitions } from '../evidence/services/evidenceApi';
import { generateVariantPreview, validateMutation } from './domain/generateVariants';
import {
  defaultMutationSettings,
  type CombinationMode,
  type EvidenceVariant,
  type MutationProfile,
  type MutationSettings,
  type MutationStrategy,
  type VariantPreview,
} from './types';
import {
  generateEvidenceVariants,
  listMutationProfiles,
  previewEvidenceVariants,
  saveMutationProfile,
} from './services/mutationApi';

function formatValue(value: number, definition?: MetricDefinition): string {
  const displayValue = value * (definition?.displayScale ?? 1);
  if (definition?.unit === '%') return `${displayValue.toFixed(definition.precision)}%`;
  return displayValue.toFixed(definition?.precision ?? 2);
}

function parseNumberList(value: string): number[] {
  if (value.trim() === '') return [];
  return value.split(',').map((item) => {
    const parsed = Number(item.trim());
    return Number.isFinite(parsed) ? parsed : Number.NaN;
  });
}

export function MutationWorkbench() {
  const [snapshot, setSnapshot] = useState<EvidenceSnapshot>(sampleSnapshot);
  const [snapshots, setSnapshots] = useState<EvidenceSnapshot[]>([sampleSnapshot]);
  const [definitions, setDefinitions] = useState<MetricDefinition[]>(metricDefinitions);
  const [selectedFieldKeys, setSelectedFieldKeys] = useState(['HML_valuation_zscore']);
  const [strategy, setStrategy] = useState<MutationStrategy>('explicit');
  const [settings, setSettings] = useState<MutationSettings>(defaultMutationSettings);
  const [combinationMode, setCombinationMode] = useState<CombinationMode>('one-at-a-time');
  const [profileName, setProfileName] = useState('HML valuation sensitivity');
  const [profiles, setProfiles] = useState<MutationProfile[]>([]);
  const [activeProfileId, setActiveProfileId] = useState('');
  const [message, setMessage] = useState('');
  const [generatedVariants, setGeneratedVariants] = useState<EvidenceVariant[] | null>(null);
  const [apiPreview, setApiPreview] = useState<VariantPreview | null>(null);
  const [apiStatus, setApiStatus] = useState<'connecting' | 'connected' | 'offline'>('connecting');
  const [savingProfile, setSavingProfile] = useState(false);
  const [searchText, setSearchText] = useState('');

  const currentSettings = { ...settings, strategy };
  const selectedDefinitions = selectedFieldKeys
    .map((key) => definitions.find((definition) => definition.key === key))
    .filter((definition): definition is MetricDefinition => definition !== undefined);
  const validationError = validateMutation(selectedFieldKeys, currentSettings);
  const localPreview = validationError
    ? { variants: [], totalCount: 0 }
    : generateVariantPreview(
      snapshot.values,
      selectedFieldKeys,
      currentSettings,
      combinationMode,
      Object.fromEntries(selectedDefinitions.map((definition) => [definition.key, definition.displayScale])),
    );
  const preview = apiPreview ?? localPreview;
  const eligibleFields = definitions.filter((definition) =>
    definition.mutationEligible
      && Object.prototype.hasOwnProperty.call(snapshot.values, definition.key)
      && definition.label.toLowerCase().includes(searchText.toLowerCase()),
  );

  useEffect(() => {
    let cancelled = false;
    async function initializeWorkbench() {
      try {
        const [snapshotResult, metricResult, profileResult] = await Promise.all([
          listEvidenceSnapshots(),
          listMetricDefinitions(),
          listMutationProfiles(),
        ]);
        let availableSnapshots = snapshotResult.snapshots;
        if (availableSnapshots.length === 0) {
          const created = await createEvidenceSnapshot({
            name: sampleSnapshot.name,
            asOf: sampleSnapshot.asOf,
            values: sampleSnapshot.values,
          });
          availableSnapshots = [created];
        }
        if (cancelled) return;
        setSnapshots(availableSnapshots);
        setSnapshot(availableSnapshots[0]);
        setDefinitions(metricResult);
        const initialField = metricResult.find((definition) =>
          definition.mutationEligible
            && Object.prototype.hasOwnProperty.call(availableSnapshots[0].values, definition.key),
        );
        setSelectedFieldKeys(initialField ? [initialField.key] : []);
        setProfiles(profileResult.profiles);
        setApiStatus('connected');
        setMessage('');
      } catch (error) {
        if (cancelled) return;
        setApiStatus('offline');
        setMessage(error instanceof Error ? error.message : 'Local API is unavailable.');
      }
    }
    void initializeWorkbench();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    setApiPreview(null);
    if (apiStatus !== 'connected' || validationError) return;
    let cancelled = false;
    const timer = window.setTimeout(() => {
      void previewEvidenceVariants(snapshot.id, selectedFieldKeys, currentSettings, combinationMode)
        .then((result) => {
          if (!cancelled) setApiPreview(result);
        })
        .catch((error: unknown) => {
          if (!cancelled) setMessage(error instanceof Error ? error.message : 'Preview request failed.');
        });
    }, 140);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [apiStatus, snapshot.id, selectedFieldKeys, settings, strategy, combinationMode, validationError]);

  function updateSettings(patch: Partial<MutationSettings>) {
    setSettings((current) => ({ ...current, ...patch }));
    setGeneratedVariants(null);
    setApiPreview(null);
    setMessage('');
  }

  function toggleField(fieldKey: string) {
    const field = definitions.find((definition) => definition.key === fieldKey);
    const selectedUnit = selectedFieldKeys
      .map((key) => definitions.find((definition) => definition.key === key)?.unit)
      .find((unit): unit is string => unit !== undefined);
    if (!selectedFieldKeys.includes(fieldKey) && field && selectedUnit && field.unit !== selectedUnit) {
      setMessage(`Select fields with the same unit (${selectedUnit}) to combine their mutations.`);
      return;
    }
    setSelectedFieldKeys((current) => current.includes(fieldKey)
      ? current.filter((key) => key !== fieldKey)
      : [...current, fieldKey]);
    setGeneratedVariants(null);
    setApiPreview(null);
    setMessage('');
  }

  function chooseStrategy(nextStrategy: MutationStrategy) {
    setStrategy(nextStrategy);
    setGeneratedVariants(null);
    setApiPreview(null);
    setMessage('');
  }

  async function saveProfile() {
    if (validationError) {
      setMessage(validationError);
      return;
    }
    if (!profileName.trim()) {
      setMessage('Give this profile a name before saving.');
      return;
    }

    const profileValues = {
      name: profileName.trim(),
      fieldKeys: [...selectedFieldKeys],
      settings: { ...currentSettings, explicitValues: [...currentSettings.explicitValues] },
      combinationMode,
    };
    setSavingProfile(true);
    try {
      const savedProfile = await saveMutationProfile(profileValues, activeProfileId || undefined);
      setProfiles((current) => [savedProfile, ...current.filter((item) => item.id !== savedProfile.id)]);
      setActiveProfileId(savedProfile.id);
      setMessage('Profile saved to the local API.');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Profile could not be saved.');
    } finally {
      setSavingProfile(false);
    }
  }

  function loadProfile(profileId: string) {
    setActiveProfileId(profileId);
    const profile = profiles.find((item) => item.id === profileId);
    if (!profile) return;
    const availableKeys = profile.fieldKeys.filter((key) =>
      definitions.some((definition) => definition.key === key && definition.mutationEligible)
        && Object.prototype.hasOwnProperty.call(snapshot.values, key),
    );
    setSelectedFieldKeys(availableKeys);
    setSettings(profile.settings);
    setStrategy(profile.settings.strategy);
    setCombinationMode(profile.combinationMode);
    setProfileName(profile.name);
    setGeneratedVariants(null);
    setApiPreview(null);
    setMessage(availableKeys.length === profile.fieldKeys.length
      ? 'Profile loaded.'
      : 'Some profile fields are not available in this snapshot.');
  }

  function selectSnapshot(snapshotId: string) {
    const nextSnapshot = snapshots.find((item) => item.id === snapshotId);
    if (!nextSnapshot) return;
    const nextKeys = selectedFieldKeys.filter((key) =>
      definitions.some((definition) => definition.key === key && definition.mutationEligible)
        && Object.prototype.hasOwnProperty.call(nextSnapshot.values, key),
    );
    const fallbackField = definitions.find((definition) =>
      definition.mutationEligible
        && Object.prototype.hasOwnProperty.call(nextSnapshot.values, definition.key),
    );
    setSnapshot(nextSnapshot);
    setSelectedFieldKeys(nextKeys.length ? nextKeys : fallbackField ? [fallbackField.key] : []);
    setActiveProfileId('');
    setGeneratedVariants(null);
    setApiPreview(null);
    setMessage('');
  }

  async function generateVariants() {
    if (validationError) {
      setMessage(validationError);
      return;
    }
    try {
      const variants = await generateEvidenceVariants(
        snapshot.id,
        selectedFieldKeys,
        currentSettings,
        combinationMode,
        activeProfileId || undefined,
      );
      setGeneratedVariants(variants);
      setMessage(`${variants.length.toLocaleString()} variants saved to the local API.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Variants could not be generated.');
    }
  }

  function setMode(mode: CombinationMode) {
    setCombinationMode(mode);
    setGeneratedVariants(null);
    setApiPreview(null);
    setMessage('');
  }

  return (
    <div className="workbench-shell">
      <WorkspaceSidebar active="mutations" apiStatus={apiStatus} profileCount={profiles.length} />

      <main className="main-content" id="mutation-builder">
        <header className="topbar">
          <div className="breadcrumbs"><span>Workbench</span><span className="crumb-separator">/</span><strong>Mutation builder</strong></div>
          <div className="topbar-right"><span className="environment-pill"><span className={`status-dot${apiStatus === 'offline' ? ' offline' : ''}`} />{apiStatus === 'connected' ? 'API CONNECTED' : apiStatus === 'connecting' ? 'CONNECTING' : 'SAMPLE MODE'}</span><button className="icon-button" type="button" aria-label="Help" title="Help"><CircleHelp size={18} /></button></div>
        </header>

        <div className="content-wrap">
          <div className="page-heading">
            <div>
              <div className="eyebrow"><span className="eyebrow-line" />EVIDENCE LAB <span className="eyebrow-dot">/</span> MUTATIONS</div>
              <h1>Mutation <em>builder</em></h1>
              <p className="page-intro">Shape controlled evidence variants. Keep every change traceable to its source.</p>
            </div>
            <div className="heading-actions">
              <label className="profile-loader">
                <Layers3 size={16} />
                <select aria-label="Load saved profile" value={activeProfileId} onChange={(event) => loadProfile(event.target.value)}>
                  <option value="">Load profile</option>
                  {profiles.map((profile) => <option key={profile.id} value={profile.id}>{profile.name}</option>)}
                </select>
                <ChevronDown size={14} />
              </label>
              <button className="button button-outline" type="button" disabled={savingProfile || apiStatus !== 'connected'} onClick={saveProfile}><Save size={16} />Save profile</button>
            </div>
          </div>

          <section className="snapshot-bar" aria-label="Selected evidence snapshot">
            <div className="snapshot-leading"><div className="snapshot-icon"><Database size={18} /></div><div><span className="field-overline">BASE EVIDENCE SNAPSHOT</span><strong>{snapshot.name}</strong></div></div>
            <div className="snapshot-meta"><span className="snapshot-id">SNAP-{snapshot.id.slice(0, 6).toUpperCase()}</span><span className="meta-divider" /><span>As of {new Date(`${snapshot.asOf}T12:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}</span><span className="snapshot-fields">{Object.keys(snapshot.values).length} fields</span></div>
            <label className="snapshot-change"><select aria-label="Select evidence snapshot" value={snapshot.id} onChange={(event) => selectSnapshot(event.target.value)}>{snapshots.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select><ChevronDown size={14} /></label>
          </section>

          <div className="workspace-grid">
            <section className="panel field-panel" aria-labelledby="field-heading">
              <div className="panel-heading">
                <div><div className="panel-kicker">STEP 01</div><h2 id="field-heading">Choose evidence</h2></div>
                <span className="selection-count">{selectedFieldKeys.length} selected</span>
              </div>
              <p className="panel-description">Select numeric signals to vary. Original evidence stays untouched.</p>

              <label className="search-box"><Search size={15} /><input value={searchText} onChange={(event) => setSearchText(event.target.value)} placeholder="Find a metric" /><kbd>/</kbd></label>

              <div className="field-list" role="group" aria-label="Eligible evidence fields">
                {eligibleFields.map((definition) => {
                  const selected = selectedFieldKeys.includes(definition.key);
                  const value = snapshot.values[definition.key];
                  return (
                    <button className={`field-row${selected ? ' selected' : ''}`} key={definition.key} type="button" aria-pressed={selected} onClick={() => toggleField(definition.key)}>
                      <span className={`field-checkbox${selected ? ' checked' : ''}`}>{selected && <Check size={12} strokeWidth={3} />}</span>
                      <span className="field-name"><strong>{definition.label}</strong><span>{definition.group}</span></span>
                      <span className="field-value">{formatValue(value, definition)}<small>{definition.unit}</small></span>
                    </button>
                  );
                })}
                {eligibleFields.length === 0 && <div className="empty-fields">No matching numeric fields.</div>}
              </div>

              <div className="field-panel-footer"><span><span className="legend-dot" />Mutation eligible</span><button type="button" className="text-button" title="Metric definitions are separate from evidence values">Metric definitions <ArrowRight size={13} /></button></div>
            </section>

            <div className="right-column">
              <section className="panel configuration-panel" aria-labelledby="config-heading">
                <div className="panel-heading">
                  <div><div className="panel-kicker">STEP 02</div><h2 id="config-heading">Define variation</h2></div>
                  <button className="icon-button quiet" type="button" aria-label="Mutation settings help" title="Mutation profiles store instructions, not generated evidence"><CircleHelp size={17} /></button>
                </div>

                <label className="profile-name-label" htmlFor="profile-name">PROFILE NAME <span>OPTIONAL UNTIL SAVED</span></label>
                <div className="profile-name-input"><input id="profile-name" value={profileName} onChange={(event) => setProfileName(event.target.value)} placeholder="e.g. HML valuation sensitivity" /><span className="profile-name-suffix">.profile</span></div>

                <div className="control-label-row"><span className="control-label">Mutation strategy</span><span className="control-hint">One method for selected fields</span></div>
                <div className="strategy-tabs" role="tablist" aria-label="Mutation strategy">
                  <button className={strategy === 'explicit' ? 'active' : ''} type="button" role="tab" aria-selected={strategy === 'explicit'} onClick={() => chooseStrategy('explicit')}><TableProperties size={15} />Values</button>
                  <button className={strategy === 'range' ? 'active' : ''} type="button" role="tab" aria-selected={strategy === 'range'} onClick={() => chooseStrategy('range')}><SlidersHorizontal size={15} />Range</button>
                  <button className={strategy === 'random' ? 'active' : ''} type="button" role="tab" aria-selected={strategy === 'random'} onClick={() => chooseStrategy('random')}><Dices size={15} />Random</button>
                </div>

                {strategy === 'explicit' && (
                  <div className="strategy-fields">
                    <label className="input-label" htmlFor="explicit-values">Test values <span>comma separated</span></label>
                    <div className="number-input-wrap"><input id="explicit-values" value={settings.explicitValues.join(', ')} onChange={(event) => updateSettings({ explicitValues: parseNumberList(event.target.value) })} inputMode="decimal" /><span className="input-unit">{selectedDefinitions[0]?.unit ?? 'value'}</span></div>
                    <div className="input-footnote"><Sparkles size={13} />Baseline {selectedDefinitions[0] ? formatValue(snapshot.values[selectedDefinitions[0].key], selectedDefinitions[0]) : 'value'} is not included unless added.</div>
                  </div>
                )}

                {strategy === 'range' && (
                  <div className="strategy-fields">
                    <div className="range-inputs">
                      <label className="input-label">Start<input type="number" step="any" value={settings.rangeStart} onChange={(event) => updateSettings({ rangeStart: Number(event.target.value) })} /></label>
                      <label className="input-label">End<input type="number" step="any" value={settings.rangeEnd} onChange={(event) => updateSettings({ rangeEnd: Number(event.target.value) })} /></label>
                      <label className="input-label">Step<input type="number" min="0.000001" step="any" value={settings.rangeStep} onChange={(event) => updateSettings({ rangeStep: Number(event.target.value) })} /></label>
                    </div>
                    <div className="input-footnote"><SlidersHorizontal size={13} />Inclusive range · values generated from start through end.</div>
                  </div>
                )}

                {strategy === 'random' && (
                  <div className="strategy-fields">
                    <div className="range-inputs random-inputs">
                      <label className="input-label">Spread around baseline<input type="number" min="0" step="any" value={settings.randomSpread} onChange={(event) => updateSettings({ randomSpread: Number(event.target.value) })} /></label>
                      <label className="input-label">Samples<input type="number" min="1" max="100" step="1" value={settings.randomCount} onChange={(event) => updateSettings({ randomCount: Number(event.target.value) })} /></label>
                    </div>
                    <label className="seed-row"><span><Dices size={14} />Random seed</span><input type="number" value={settings.seed} onChange={(event) => updateSettings({ seed: Number(event.target.value) })} /></label>
                  </div>
                )}

                <div className="combination-section">
                  <div className="control-label-row"><span className="control-label">When multiple fields are selected</span></div>
                  <div className="mode-options">
                    <button className={`mode-option${combinationMode === 'one-at-a-time' ? ' active' : ''}`} type="button" onClick={() => setMode('one-at-a-time')}><span className="radio-mark" /><span><strong>One at a time</strong><small>Isolate each field's effect</small></span></button>
                    <button className={`mode-option${combinationMode === 'cartesian' ? ' active' : ''}`} type="button" onClick={() => setMode('cartesian')}><span className="radio-mark" /><span><strong>All combinations</strong><small>Cross selected field values</small></span></button>
                  </div>
                </div>
              </section>

              <section className="preview-panel" aria-labelledby="preview-heading">
                <div className="preview-heading-row">
                  <div><div className="panel-kicker">STEP 03</div><h2 id="preview-heading">Variant preview</h2></div>
                  <span className="variant-count"><strong>{preview.totalCount.toLocaleString()}</strong> {preview.totalCount === 1 ? 'variant' : 'variants'}</span>
                </div>
                <div className="preview-subhead"><span>Source remains unchanged</span><span className="preview-refresh"><span className="status-dot" />LIVE PREVIEW</span></div>

                {validationError ? (
                  <div className="validation-message"><span className="validation-mark">!</span><span>{validationError}</span></div>
                ) : (
                  <div className="variant-table-wrap">
                    <table className="variant-table">
                      <thead><tr><th>VARIANT</th>{selectedDefinitions.slice(0, 2).map((definition) => <th key={definition.key}>{definition.key.toUpperCase()}</th>)}{selectedDefinitions.length > 2 && <th>+{selectedDefinitions.length - 2} FIELDS</th>}<th>CHANGED</th></tr></thead>
                      <tbody>
                        <tr className="baseline-row"><td><span className="baseline-marker" />Base evidence</td>{selectedDefinitions.slice(0, 2).map((definition) => <td key={definition.key}>{formatValue(snapshot.values[definition.key], definition)}</td>)}{selectedDefinitions.length > 2 && <td>—</td>}<td><span className="unchanged-tag">UNCHANGED</span></td></tr>
                        {(generatedVariants ?? preview.variants).slice(0, 6).map((variant, index) => (
                          <tr className="variant-row" key={variant.id}><td><span className="variant-index">{String(index + 1).padStart(2, '0')}</span>Variant {String(index + 1).padStart(2, '0')}</td>{selectedDefinitions.slice(0, 2).map((definition) => <td key={definition.key}>{formatValue(variant.values[definition.key], definition)}</td>)}{selectedDefinitions.length > 2 && <td>{variant.changedFields.length} fields</td>}<td><span className="changed-tag">{variant.changedFields.length === 1 ? variant.changedFields[0].replace(/_/g, ' ') : `${variant.changedFields.length} fields`}</span></td></tr>
                        ))}
                      </tbody>
                    </table>
                    {preview.totalCount > 6 && <div className="more-variants">+ {Math.min(preview.totalCount - 6, 94)} more in preview <ArrowDownToLine size={13} /></div>}
                  </div>
                )}

                <div className="preview-footer">
                  <div className="run-estimate"><span className="estimate-icon"><FlaskConical size={15} /></span><span><strong>{preview.totalCount.toLocaleString()} runs</strong><small>before repetitions</small></span><span className="estimate-separator">·</span><span className="estimate-repeat">× 1 repeat</span></div>
                  <button className="button button-primary" type="button" disabled={Boolean(validationError) || apiStatus !== 'connected'} onClick={generateVariants}>{generatedVariants ? <Check size={16} /> : <Plus size={16} />}{generatedVariants ? 'Generated' : 'Generate variants'}</button>
                </div>
                {(message || preview.totalCount > 100) && <div className={`status-message${message && message.includes('not available') ? ' warning' : ''}`} role="status">{message || `Showing the first 100 of ${preview.totalCount.toLocaleString()} variants.`}</div>}
              </section>
            </div>
          </div>

          <footer className="page-footer"><span><span className="footer-dot" />Backend preview · no model calls</span><span>Profiles and variants are kept separate from source evidence <ArrowRight size={13} /></span></footer>
        </div>
      </main>
    </div>
  );
}
