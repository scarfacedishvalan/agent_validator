import { useEffect, useState } from 'react';
import { AlertCircle, ArrowDownToLine, ArrowRight, BookOpen, Check, ChevronRight, Code2, Database, Eye, FileJson2, FileText, FlaskConical, FolderOpen, Layers3, Play, Plus, RotateCcw, Settings2, ShieldCheck, Trash2, Users } from 'lucide-react';
import { WorkspaceSidebar } from '../../shared/components/WorkspaceSidebar';
import { documents, initialDraft, isObject, resolveDraft, type DocumentId, type JsonValue } from './configuration';
import { convergenceApi, type RunDetail } from './api';
import { useConfigurationSync } from './useConfigurationSync';
import { isRunning, RunHistory, RunResults } from './RunResults';
import { JsonFields } from './JsonFields';
import './convergence.css';

const icons = { run: Settings2, evidence: Database, personalities: Users, defaults: Settings2, factors: Layers3, metrics: BookOpen, system: FileText, user: FileText, policy: ShieldCheck, contract: FileJson2 };
const tabNames = ['Setup', 'Prompt preview', 'Results', 'Run history'] as const;
type Tab = typeof tabNames[number];

export function ConvergenceWorkbench() {
  const sync = useConfigurationSync();
  const { draft, setDraft } = sync;
  const [selectedRunId, setSelectedRunId] = useState('');
  const [selectedRun, setSelectedRun] = useState<RunDetail | null>(null);
  const [runError, setRunError] = useState('');
  const [runLoadError, setRunLoadError] = useState('');
  const [runBusy, setRunBusy] = useState(false);
  const [showStartConfirmation, setShowStartConfirmation] = useState(false);
  const [tab, setTab] = useState<Tab>('Setup');
  const [selected, setSelected] = useState<DocumentId>('run');
  const [mode, setMode] = useState<'form' | 'raw'>('form');
  const [editingPersonality, setEditingPersonality] = useState('Long-Horizon Analyst with Adaptive Short-Term Adjustment');
  const [newPersonality, setNewPersonality] = useState('');
  const [personalityError, setPersonalityError] = useState('');
  const [confirmReset, setConfirmReset] = useState(false);
  const resolved = resolveDraft(draft);
  const activeDocument = documents.find((doc) => doc.id === selected)!;
  const current = resolved.parsed[selected];
  const run = resolved.parsed.run.value;
  const runtime = resolved.parsed.defaults.value;
  const evidence = resolved.parsed.evidence.value;
  const personalities = resolved.parsed.personalities.value;
  const personalityNames = isObject(personalities) ? Object.keys(personalities) : [];
  const currentPersonality = personalityNames.includes(editingPersonality) ? editingPersonality : personalityNames[0] ?? '';
  const iterations = isObject(run) && typeof run.iterations === 'number' ? run.iterations : 0;
  const factorCount = Array.isArray(resolved.parsed.factors.value) ? resolved.parsed.factors.value.length : 0;

  useEffect(() => {
    if (!selectedRunId && sync.listing.runs.length) setSelectedRunId(sync.listing.runs[0].id);
  }, [selectedRunId, sync.listing.runs]);
  useEffect(() => {
    if (!selectedRunId || !sync.connected) return;
    let cancelled = false;
    void convergenceApi.run(selectedRunId).then((result) => {
      if (!cancelled) { setSelectedRun(result); setRunLoadError(''); }
    }).catch((error: unknown) => {
      if (!cancelled) { setSelectedRun(null); setRunLoadError(error instanceof Error ? error.message : 'Run could not be loaded.'); }
    });
    return () => { cancelled = true; };
  }, [selectedRunId, sync.listing, sync.connected]);

  function updateDocument(id: DocumentId, value: JsonValue) {
    setDraft((previous) => ({ ...previous, [id]: JSON.stringify(value, null, 2) }));
  }
  function chooseDocument(id: DocumentId) {
    setSelected(id);
    setMode(id === 'contract' ? 'raw' : 'form');
    setConfirmReset(false);
  }
  function addPersonality() {
    const name = newPersonality.trim();
    if (!name || !isObject(personalities)) {
      setPersonalityError('Enter a personality name and fix any JSON syntax errors first.');
      return;
    }
    if (Object.prototype.hasOwnProperty.call(personalities, name)) {
      setPersonalityError('A personality with that name already exists.');
      return;
    }
    updateDocument('personalities', { ...personalities, [name]: ['Describe how this analyst interprets the supplied evidence.'] });
    setEditingPersonality(name);
    setNewPersonality('');
    setPersonalityError('');
  }
  function exportDraft() {
    const blob = new Blob([JSON.stringify({ schemaVersion: 1, documents: draft }, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'convergence-setup.json';
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  const runObject = isObject(run) ? run : null;
  const modelOptions = runObject && Array.isArray(runObject.models)
    ? runObject.models.filter((model): model is string => typeof model === 'string')
    : [];
  const validationErrors = [...resolved.errors, ...(sync.previewError ? [sync.previewError] : [])];
  const previewReady = validationErrors.length === 0 && !!sync.preview && !sync.previewPending && sync.connected;
  const activeRun = sync.listing.runs.find((run) => isRunning(run.status));
  const canStart = previewReady && sync.allSaved && sync.credentialsReady && !activeRun && !runBusy;
  const syncStatus = !sync.connected ? 'Disconnected' : sync.conflicts.length ? 'File conflict' : sync.dirty.length ? 'Unsaved edits' : sync.saving.length ? 'Saving files...' : sync.allSaved ? 'Synced to local files' : 'Loading files...';

  async function startRun() {
    if (!canStart || !sync.remote) return;
    setRunBusy(true);
    setRunError('');
    try {
      const revisions = Object.fromEntries(documents.map(({ id }) => [id, sync.remote![id].revision])) as Record<DocumentId, string>;
      const created = await convergenceApi.start(revisions);
      setSelectedRunId(created.id);
      setSelectedRun(await convergenceApi.run(created.id));
      setShowStartConfirmation(false);
      setTab('Results');
      await sync.refresh();
    } catch (error) {
      setRunError(error instanceof Error ? error.message : 'Run could not be started.');
    } finally {
      setRunBusy(false);
    }
  }
  async function stopRun() {
    if (!selectedRunId || runBusy) return;
    setRunBusy(true);
    setRunError('');
    try {
      await convergenceApi.stop(selectedRunId);
      setSelectedRun(await convergenceApi.run(selectedRunId));
    } catch (error) {
      setRunError(error instanceof Error ? error.message : 'Run could not be stopped.');
    } finally {
      setRunBusy(false);
    }
  }

  return (
    <div className="workbench-shell convergence-shell">
      <WorkspaceSidebar active="convergence" apiStatus={sync.connected ? 'connected' : 'offline'} />
      <main className="main-content">
        <header className="topbar">
          <div className="breadcrumbs"><span>Workbench</span><span className="crumb-separator">/</span><strong>Convergence testing</strong></div>
          <span className="environment-pill"><span className={`status-dot${sync.connected ? '' : ' offline'}`} />{sync.connected ? 'FILE SYNC CONNECTED' : 'DISCONNECTED'}</span>
        </header>
        <div className="content-wrap convergence-content">
          <div className="page-heading">
            <div>
              <div className="eyebrow"><span className="eyebrow-line" />EVIDENCE LAB <span className="eyebrow-dot">/</span> REPEATABILITY</div>
              <h1>Convergence <em>testing</em></h1>
              <p className="page-intro">One configuration. Repeated calls. A clearer picture of factor-view stability.</p>
            </div>
            <div className="heading-actions">
              <button className="button button-outline" type="button" onClick={exportDraft}><ArrowDownToLine size={14} />Export setup</button>
              <button className="button button-primary" type="button" disabled={!canStart} title={!sync.credentialsReady ? 'Set OPENAI_API_KEY on the backend' : !sync.allSaved ? 'Save or resolve all document edits first' : activeRun ? 'A batch is already running' : 'Start a billable sequential batch'} onClick={() => setShowStartConfirmation(true)}><Play size={14} />Start run</button>
            </div>
          </div>
          <div className="convergence-notice"><FlaskConical size={17} /><div><strong>File-backed research workspace</strong><span>Valid edits save automatically to local files. External edits sync back in real time. A running batch keeps its inputs frozen; changes apply to the next run.</span></div><span className="preview-label">LIVE CONFIGURATION</span></div>
          {sync.error && <div className="config-error" role="alert">{sync.error} <button className="text-button" onClick={() => void sync.refresh()}>Reconnect</button></div>}
          {sync.cacheError && <div className="config-error" role="alert">{sync.cacheError}</div>}
          {runError && <div className="config-error" role="alert">{runError}</div>}
          {runLoadError && <div className="config-error" role="alert">{runLoadError}</div>}
          {showStartConfirmation && <section className="start-confirmation" role="alertdialog" aria-modal="false" aria-labelledby="confirm-run-title"><h2 id="confirm-run-title">Start {iterations} live API calls?</h2><p>This will incur provider charges. Calls are sequential and failures stop the batch without retries. All current file revisions and rendered prompts will be frozen.</p><p><strong>{runObject ? String(runObject.model) : ''}</strong> | {runObject ? String(runObject.personality) : ''}</p><div className="heading-actions"><button className="button button-outline" onClick={() => setShowStartConfirmation(false)}>Cancel</button><button className="button button-primary" disabled={!canStart} onClick={() => void startRun()}>{runBusy ? 'Starting...' : `Confirm ${iterations} billable calls`}</button></div></section>}
          {sync.conflicts.map((id) => <section className="file-conflict" role="alert" key={id}><h3>External file conflict: {documents.find((doc) => doc.id === id)?.label}</h3><p>The file changed while you were editing. Compare the versions before choosing.</p><div className="conflict-columns"><details><summary>Your unsaved draft</summary><pre>{draft[id]}</pre></details><details><summary>Current file</summary><pre>{sync.remote?.[id].content}</pre></details></div><div className="heading-actions"><button className="button button-outline" onClick={() => sync.resolveConflict(id, false)}>Reload file (discard my edits)</button><button className="button button-outline" onClick={() => sync.resolveConflict(id, true)}>Keep my draft (overwrite latest file)</button></div></section>)}
          {!!Object.keys(sync.saveErrors).length && <div className="config-error" role="alert">{Object.entries(sync.saveErrors).map(([id, error]) => <p key={id}>{id}: {error}</p>)}<button className="text-button" onClick={sync.retrySaves}>Retry saving valid drafts</button></div>}
          {!sync.credentialsReady && sync.connected && <p className="credentials-notice">Live runs require OPENAI_API_KEY in the backend environment. The key is never sent to this browser.</p>}
          {activeRun && <div className="active-run-banner"><span>{activeRun.status === 'stopping' ? 'Stopping after current call' : 'Batch running'}: {activeRun.completedIterations}/{activeRun.requestedIterations} completed</span><button className="text-button" onClick={() => { setSelectedRunId(activeRun.id); setTab('Results'); }}>Inspect active batch <ArrowRight size={12} /></button></div>}
          <div className="convergence-summary">
            <div><span>EXPERIMENT</span><strong>{runObject ? String(runObject.name ?? 'Untitled') : 'Invalid run settings'}</strong></div>
            <div><span>MODEL</span><strong>{runObject ? String(runObject.model ?? 'Not set') : 'Not set'}</strong></div>
            <div><span>SEQUENTIAL CALLS</span><strong>{iterations} <small>requested</small></strong></div>
            <div><span>FACTOR CATALOG</span><strong>{factorCount} <small>factors</small></strong></div>
            <div className="draft-status" role="status">{sync.allSaved && sync.connected ? <Check size={14} /> : <AlertCircle size={14} />}<span>{syncStatus}</span></div>
          </div>
          <div className="convergence-tabs" role="tablist" aria-label="Convergence sections">
            {tabNames.map((name, index) => <button key={name} type="button" role="tab" id={`convergence-tab-${index}`} aria-selected={tab === name} aria-controls="convergence-panel" onClick={() => setTab(name)} className={tab === name ? 'active' : ''}>{name}{name === 'Prompt preview' && <span className="tab-count">2</span>}{name === 'Run history' && <span className="tab-count">{sync.listing.runs.length}</span>}</button>)}
            <span className="tabs-trailing">LOCAL FILE CONFIGURATION</span>
          </div>
          <div role="tabpanel" id="convergence-panel" aria-labelledby={`convergence-tab-${tabNames.indexOf(tab)}`}>
            {tab === 'Setup' && (
              <div className="configuration-workspace">
                <nav className="config-navigation" aria-label="Configuration inputs">
                  <div className="config-nav-heading">INPUT DOCUMENTS <span>{documents.length}</span></div>
                  {documents.map((doc, index) => {
                    const Icon = icons[doc.id];
                    return <button type="button" key={doc.id} aria-label={doc.label} className={`config-nav-item${selected === doc.id ? ' active' : ''}`} aria-current={selected === doc.id ? 'true' : undefined} onClick={() => chooseDocument(doc.id)}><Icon size={15} /><span>{doc.label}</span>{resolved.parsed[doc.id].error ? <AlertCircle size={12} className="error-ink" /> : <small>{String(index + 1).padStart(2, '0')}</small>}</button>;
                  })}
                  <div className="config-nav-note"><FolderOpen size={16} /><p>Bundled from local files.<br /><strong>Edits are browser-only.</strong></p></div>
                </nav>
                <section className="config-editor" aria-label={activeDocument.label}>
                  <fieldset className="config-editable-fields" disabled={!sync.remote}>
                  <div className="config-editor-heading">
                    <div><div className="field-overline">CONFIGURATION / {String(documents.indexOf(activeDocument) + 1).padStart(2, '0')}</div><h2>{activeDocument.label}</h2></div>
                    {activeDocument.format === 'json' && <div className="editor-mode" role="group" aria-label="Editor mode"><button type="button" className={mode === 'form' ? 'active' : ''} onClick={() => setMode('form')}><Settings2 size={12} />Fields</button><button type="button" className={mode === 'raw' ? 'active' : ''} onClick={() => setMode('raw')}><Code2 size={12} />JSON</button></div>}
                  </div>
                  <p className="config-description">{activeDocument.description}</p>
                  {current.error && <div className="config-error" role="alert">{current.error} Your draft is retained; use JSON to fix structural errors.</div>}
                  {activeDocument.format === 'text' || mode === 'raw' ? (
                    <textarea className="config-code-editor" aria-label={`${activeDocument.label} source`} spellCheck={false} value={draft[selected]} onChange={(event) => setDraft((previous) => ({ ...previous, [selected]: event.target.value }))} />
                  ) : selected === 'run' && runObject ? (
                    <div className="run-settings-form">
                      <JsonFields value={runObject.name ?? ''} label="Experiment name" path="run.name" onChange={(name) => updateDocument('run', { ...runObject, name })} />
                      <div className="config-two-columns">
                        <JsonFields value={runObject.iterations ?? 10} label="Number of calls" path="run.iterations" onChange={(iterations) => updateDocument('run', { ...runObject, iterations })} />
                        <div className="config-field">
                          <label htmlFor="run-model">Selected model</label>
                          <select id="run-model" value={String(runObject.model ?? '')} onChange={(event) => updateDocument('run', { ...runObject, model: event.target.value })}>
                            {!modelOptions.includes(String(runObject.model ?? '')) && <option value={String(runObject.model ?? '')} disabled>{String(runObject.model ?? 'Select a model')} (not in models)</option>}
                            {[...new Set(modelOptions)].map((model) => <option key={model} value={model}>{model.replace(/^openai:/, '')}{model === 'openai:gpt-4o' ? ' (legacy, non-reasoning)' : ''}</option>)}
                          </select>
                        </div>
                      </div>
                      <details className="run-details"><summary>Available models ({modelOptions.length})</summary><p>Edit the list here or in JSON. Changes sync to the models field in the local run-settings file. Keep the selected model in the list.</p><JsonFields value={runObject.models ?? []} label="Model identifier" path="run.models" onChange={(models) => updateDocument('run', { ...runObject, models })} /></details>
                      <JsonFields value={runObject.temperature ?? null} label="Temperature (optional)" path="run.temperature" onChange={(temperature) => updateDocument('run', { ...runObject, temperature })} />
                      <p className="results-footnote">Reasoning models may reject a custom temperature. Clear this field to omit it and use the provider default. Model access depends on your OpenAI account.</p>
                      <div className="config-field"><label htmlFor="run-personality">Analyst personality</label><select id="run-personality" value={String(runObject.personality ?? '')} onChange={(event) => updateDocument('run', { ...runObject, personality: event.target.value })}>{!personalityNames.includes(String(runObject.personality)) && <option value={String(runObject.personality ?? '')}>Select an available personality</option>}{personalityNames.map((name) => <option key={name}>{name}</option>)}</select><button type="button" className="text-button personality-edit-link" onClick={() => { setEditingPersonality(String(runObject.personality)); chooseDocument('personalities'); }}>View and edit instructions <ArrowRight size={12} /></button></div>
                      <JsonFields value={runObject.outputDirectory ?? ''} label="Results directory (project-relative)" path="run.outputDirectory" onChange={(outputDirectory) => updateDocument('run', { ...runObject, outputDirectory })} />
                      <div className="run-protocol"><ShieldCheck size={20} /><div><strong>A controlled batch, by design</strong><p>Sequential calls. Fixed inputs. No reused responses, silent retries or automatic pass/fail threshold.</p></div></div>
                      <div className="call-estimate"><span><strong>{iterations}</strong> live calls when connected</span><span>Credentials stay on the server</span></div>
                    </div>
                  ) : selected === 'personalities' && isObject(personalities) ? (
                    <div className="personality-editor">
                      <div className="config-field"><label htmlFor="editing-personality">Personality library</label><select id="editing-personality" value={currentPersonality} onChange={(event) => setEditingPersonality(event.target.value)}>{personalityNames.map((name) => <option key={name}>{name}</option>)}</select></div>
                      {currentPersonality && <><div className="personality-caption"><span>{Array.isArray(personalities[currentPersonality]) ? personalities[currentPersonality].length : 0} ordered instructions</span><button type="button" className="text-button" onClick={() => { const next = { ...personalities }; delete next[currentPersonality]; updateDocument('personalities', next); }}><Trash2 size={12} />Remove personality</button></div><JsonFields value={personalities[currentPersonality]} label="Instructions" path={`personalities.${currentPersonality}`} onChange={(instructions) => updateDocument('personalities', { ...personalities, [currentPersonality]: instructions })} /></>}
                      <div className="add-personality"><label htmlFor="new-personality">Create personality</label><div><input id="new-personality" placeholder="New analyst name" value={newPersonality} onChange={(event) => setNewPersonality(event.target.value)} /><button type="button" className="button button-outline" onClick={addPersonality}><Plus size={14} />Add</button></div>{personalityError && <p className="error-ink" role="alert">{personalityError}</p>}<small>Rename, duplicate or change the library structure in the JSON editor.</small></div>
                    </div>
                  ) : current.value !== null ? <JsonFields value={current.value} label={activeDocument.label} path={selected} onChange={(value) => updateDocument(selected, value)} /> : <div className="config-empty"><AlertCircle size={24} /><p>Switch to JSON to repair this document.</p><button className="button button-outline" type="button" onClick={() => setMode('raw')}>Open JSON editor</button></div>}
                  <div className="config-editor-footer"><span>{activeDocument.format === 'text' ? 'Text template / policy' : 'Fields and JSON share the same draft'}</span><button className="text-button" type="button" onClick={() => setConfirmReset(true)}><RotateCcw size={12} />Reset document</button></div>
                  {confirmReset && <div className="reset-confirm" role="alert"><p>Restore the bundled version? This will be saved to the local file after validation.</p><button className="button button-outline" type="button" onClick={() => setConfirmReset(false)}>Cancel</button><button className="button button-primary" type="button" onClick={() => { setDraft((previous) => ({ ...previous, [selected]: initialDraft[selected] })); setConfirmReset(false); }}>Reset {activeDocument.label}</button></div>}
                  </fieldset>
                </section>
                <aside className="config-inspector" aria-label="Configuration details">
                  <div className="inspector-card"><div className="inspector-heading"><FolderOpen size={14} />SOURCE DOCUMENT</div><code>{sync.remote?.[selected].path ?? activeDocument.path}</code><span className="source-badge">{sync.dirty.includes(selected) ? 'UNSAVED DRAFT' : 'LOCAL FILE'}</span><p>{sync.remote ? `Revision: ${sync.remote[selected].revision.slice(0, 12)}` : 'Waiting for the backend to load files.'}</p><p>Valid edits save automatically. Invalid drafts stay in the editor.</p>{sync.remote?.[selected].error && <p className="error-ink">File error: {sync.remote[selected].error}</p>}</div>
                  <div className="inspector-card"><div className="inspector-heading">{previewReady ? <Check size={14} /> : <AlertCircle size={14} />}DRAFT CHECKS</div><strong className={previewReady ? 'valid-ink' : 'error-ink'}>{previewReady ? 'Ready to preview' : sync.previewPending ? 'Validating with backend...' : !sync.connected ? 'Backend disconnected' : `${validationErrors.length} issue${validationErrors.length === 1 ? '' : 's'} to resolve`}</strong>{previewReady ? <p>Validated and rendered by the same backend helpers used for execution.</p> : <ul className="validation-list">{validationErrors.map((error, index) => <li key={index}>{error}</li>)}</ul>}<button type="button" className="text-button" onClick={() => setTab('Prompt preview')}>Inspect messages <ArrowRight size={12} /></button></div>
                  <div className="inspector-card return-context"><div className="inspector-heading"><Layers3 size={14} />RETURN CONTEXT</div><strong>{isObject(runtime) ? String(runtime.target_horizon ?? 'Not set') : 'Not set'}</strong><p>{isObject(runtime) ? String(runtime.q_return_convention ?? '') : ''}</p><div className="decimal-example"><code>0.04</code><ArrowRight size={12} /><strong>4%</strong></div><p>Abstention is missing data, never a zero return.</p></div>
                </aside>
              </div>
            )}
            {tab === 'Prompt preview' && (
              <section className="prompt-workspace">
                <div className="prompt-intro"><div><h2>Exactly what your draft builds</h2><p>Rendered on the backend with the execution helpers. Unsaved drafts can be previewed, but starting a run requires every input to be synced.</p></div><span className="source-badge"><Eye size={12} />{sync.allSaved ? 'SAVED FILES' : 'UNSAVED DRAFT'}</span></div>
                {!previewReady ? <div className="config-error" role="alert"><strong>{sync.previewPending ? 'Rendering updated messages...' : 'Resolve configuration issues or reconnect to render messages.'}</strong><ul>{validationErrors.map((error, index) => <li key={index}>{error}</li>)}</ul><button className="button button-outline" type="button" onClick={() => setTab('Setup')}>Back to setup</button></div> : <div className="prompt-columns">{sync.preview!.messages.map((message) => <article className="prompt-card" key={message.role}><header><div><h2>{message.role === 'system' ? 'System message' : 'User message'}</h2><p>{message.role === 'system' ? 'Template + shared policy + runtime + output schema' : 'Template + selected personality + evidence'}</p></div><span>{message.content.length.toLocaleString()} chars</span></header><pre tabIndex={0} aria-label={`${message.role === 'system' ? 'System' : 'User'} message`}>{message.content}</pre></article>)}</div>}
              </section>
            )}
            {tab === 'Run history' && <RunHistory listing={sync.listing} onSelect={(id) => { if (id !== selectedRunId) setSelectedRun(null); setSelectedRunId(id); setTab('Results'); }} />}
            {tab === 'Results' && <><div className="run-picker"><label htmlFor="selected-run">Inspect batch</label><select id="selected-run" value={selectedRunId} onChange={(event) => { setSelectedRun(null); setSelectedRunId(event.target.value); }}><option value="">Select a saved batch</option>{sync.listing.runs.map((run) => <option key={run.id} value={run.id}>{run.name || run.startedAt} | {run.status} | {run.completedIterations}/{run.requestedIterations}</option>)}</select></div>{selectedRun ? <RunResults key={selectedRun.id} run={selectedRun} onStop={() => void stopRun()} /> : <section className="convergence-empty"><div className="empty-icon"><FlaskConical size={28} /></div><h2>{selectedRunId ? 'Loading selected batch' : 'No batch selected'}</h2><p>Inspect a saved run from history or start a new experiment from Setup. Abstentions remain missing, never zero.</p></section>}</>}
          </div>
          <footer className="convergence-footer"><span><ShieldCheck size={12} />Repeatability is not forecast accuracy or proof of convergence.</span><span>{isObject(evidence) ? `Evidence as of ${String(evidence.asOf ?? 'not set')}` : 'Evidence unavailable'}<ChevronRight size={12} />{syncStatus}</span></footer>
        </div>
      </main>
    </div>
  );
}
