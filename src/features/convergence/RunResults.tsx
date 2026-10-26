import { useState } from 'react';
import { ArrowDownToLine, Square } from 'lucide-react';
import type { FactorSeries, RunDetail, RunListing } from './api';

export const isRunning = (status: string) => status === 'running' || status === 'stopping';
const percent = (value: number | null | undefined) => value === null || value === undefined ? 'Unavailable' : `${(value * 100).toFixed(2)}%`;
const dollars = (value: number | null) => value === null ? 'Unavailable' : `$${value.toFixed(8)}`;

function SeriesChart({ series, coverage = false, onSelect }: { series: FactorSeries; coverage?: boolean; onSelect: (call: number) => void }) {
  const values = coverage ? series.coverage : series.values;
  const extent = coverage ? [0, 1] : [0, ...series.values.filter((v): v is number => v !== null)];
  const low = Math.min(...extent);
  const high = Math.max(...extent);
  const range = high - low || 0.01;
  const min = coverage ? 0 : low - range * 0.12;
  const max = coverage ? 1 : high + range * 0.12;
  const x = (index: number) => values.length === 1 ? 168 : 48 + index / Math.max(1, values.length - 1) * 240;
  const y = (value: number) => 140 - (value - min) / (max - min) * 110;
  const path = (items: (number | null)[]) => {
    let gap = true;
    return items.map((value, index) => {
      if (value === null) { gap = true; return ''; }
      const command = `${gap ? 'M' : 'L'}${x(index)},${y(value)}`;
      gap = false;
      return command;
    }).join(' ');
  };
  return <svg viewBox="0 0 310 180" role="img" aria-label={coverage ? 'Cumulative active-view fraction' : 'Individual Q and active-only running mean'}>
    {[min, (min + max) / 2, max].map((tick, index) => <g key={index}><line x1="48" x2="288" y1={y(tick)} y2={y(tick)} stroke="#e4e9df" /><text x="42" y={y(tick) + 3} textAnchor="end">{(tick * 100).toFixed(1)}%</text></g>)}
    <path d={path(values)} stroke={coverage ? '#779344' : '#ba866b'} strokeWidth="1.5" fill="none" opacity=".7" />
    {!coverage && <path d={path(series.runningMean)} stroke="#315f44" strokeWidth="2.5" fill="none" />}
    {values.map((value, index) => value === null ? null : <circle key={index} cx={x(index)} cy={y(value)} r="3.5" fill={coverage ? '#779344' : '#ba866b'} role="button" tabIndex={0} aria-label={`Inspect call ${index + 1}: ${percent(value)}`} onClick={() => onSelect(index)} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onSelect(index); } }}><title>Call {index + 1}: {percent(value)}</title></circle>)}
    <text x={x(0)} y="156" textAnchor="middle">1</text>{values.length > 1 && <text x={x(values.length - 1)} y="156" textAnchor="middle">{values.length}</text>}
    <text x="168" y="174" textAnchor="middle">Call number</text>
  </svg>;
}

function Distribution({ values, onSelect }: { values: (number | null)[]; onSelect: (call: number) => void }) {
  const active = values.filter((value): value is number => value !== null).sort((a, b) => a - b);
  if (!active.length) return <div className="all-abstained">All calls abstained</div>;
  const quantile = (p: number) => {
    const index = (active.length - 1) * p;
    const lower = Math.floor(index);
    return active[lower] + (active[Math.ceil(index)] - active[lower]) * (index - lower);
  };
  const q1 = quantile(.25), median = quantile(.5), q3 = quantile(.75);
  const iqr = q3 - q1;
  const lower = active.find((value) => value >= q1 - 1.5 * iqr)!;
  const upper = [...active].reverse().find((value) => value <= q3 + 1.5 * iqr)!;
  const range = active[active.length - 1] - active[0] || .01;
  const min = active[0] - range * .15;
  const max = active[active.length - 1] + range * .15;
  const y = (v: number) => 140 - (v - min) / (max - min) * 110;
  return <svg viewBox="0 0 310 180" role="img" aria-label="Active Q box plot and every observation">
    {[min, (min + max) / 2, max].map((tick, index) => <g key={index}><line x1="48" x2="288" y1={y(tick)} y2={y(tick)} stroke="#e4e9df" /><text x="42" y={y(tick) + 3} textAnchor="end">{(tick * 100).toFixed(1)}%</text></g>)}
    <line x1="168" x2="168" y1={y(lower)} y2={y(upper)} stroke="#6c8a4d" />
    {[lower, upper].map((v, index) => <line key={index} x1="150" x2="186" y1={y(v)} y2={y(v)} stroke="#6c8a4d" />)}
    <rect x="140" y={y(q3)} width="56" height={Math.max(1, y(q1) - y(q3))} fill="#dce8c9" stroke="#6c8a4d" />
    <line x1="140" x2="196" y1={y(median)} y2={y(median)} stroke="#315f44" strokeWidth="2" />
    {values.map((v, index) => v === null ? null : <circle key={index} cx={168 + (values.length > 1 ? -15 + 30 * index / (values.length - 1) : 0)} cy={y(v)} r="3" fill="#b67d61" role="button" tabIndex={0} aria-label={`Inspect call ${index + 1}`} onClick={() => onSelect(index)} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onSelect(index); } }}><title>Call {index + 1}: {percent(v)}</title></circle>)}
    <text x="168" y="174" textAnchor="middle">Active observations only</text>
  </svg>;
}

export function RunHistory({ listing, onSelect }: { listing: RunListing; onSelect: (id: string) => void }) {
  return <section className="run-history">
    {listing.issues.map((issue) => <div className="config-error" role="alert" key={issue.path}>{issue.path}: {issue.error}</div>)}
    {!listing.runs.length && <div className="convergence-empty"><h2>No saved batches yet</h2><p>Start a run from Setup. Existing notebook files in the results directory will also appear here.</p></div>}
    <div className="results-table-scroll"><table className="results-table"><thead><tr><th>Experiment / started</th><th>Status</th><th>Calls</th><th>Model / personality</th><th /></tr></thead><tbody>{listing.runs.map((run) => <tr key={run.id}><td><strong>{run.name || 'Notebook batch'}</strong><small>{run.startedAt}</small></td><td><span className={`run-status ${run.status}`}>{run.status}</span>{run.legacy && <small>Legacy provenance</small>}</td><td>{run.completedIterations}/{run.requestedIterations}</td><td>{run.model}<small>{run.personalityKey}</small></td><td><button className="button button-outline" onClick={() => onSelect(run.id)}>Inspect</button></td></tr>)}</tbody></table></div>
  </section>;
}

export function RunResults({ run, onStop }: { run: RunDetail; onStop: () => void }) {
  const [selectedCall, setSelectedCall] = useState(0);
  const call = Math.min(selectedCall, Math.max(0, run.responses.length - 1));
  const response = run.responses[call];
  const context = run.responses[0];
  function download() {
    const blob = new Blob([JSON.stringify(run, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = run.id;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return <section className="run-results">
    <div className="results-heading"><div><h2>{run.name || 'Notebook batch'} <span className={`run-status ${run.status}`}>{run.status}</span></h2><p>{run.completedIterations}/{run.requestedIterations} calls | {run.model} | {run.personalityKey}</p><p>{context ? `${context.targetHorizon} | ${context.qReturnConvention}` : 'Waiting for the first validated response.'}</p></div><div className="heading-actions"><button className="button button-outline" onClick={download}><ArrowDownToLine size={14} />Export run</button>{isRunning(run.status) && <button className="button button-outline" disabled={run.status === 'stopping'} onClick={onStop}><Square size={12} />{run.status === 'stopping' ? 'Finishing current call...' : 'Stop after current call'}</button>}</div></div>
    <div className="run-file-path"><code>{run.outputPath}</code><span>{run.legacy ? 'Legacy batch: exact frozen prompt provenance is unavailable.' : 'Inputs frozen at start; edits apply only to the next batch.'}</span></div>
    {run.error && <div role="alert" className="config-error">{run.error}</div>}
    {run.persistenceError && <div role="alert" className="config-error">Checkpoint could not be saved: {run.persistenceError}. Export this run to preserve the available responses.</div>}
    {run.provenanceWarning && <div className="convergence-notice">{run.provenanceWarning}</div>}
    {!run.responses.length ? <div className="config-empty"><p>{isRunning(run.status) ? 'The live request is in progress. Closing this tab does not stop the backend batch.' : 'No validated responses were completed.'}</p></div> : <>
      <div className="factor-charts">{run.factorOrder.map((factor) => <article className="factor-diagnostic" key={factor}><h3>{factor}</h3><div className="factor-chart-grid"><div><h4>Q across calls</h4><SeriesChart series={run.diagnostics.series[factor]} onSelect={setSelectedCall} /><p><span className="legend-individual" />Individual Q <span className="legend-mean" />Running mean (active only)</p></div><div><h4>Active-Q distribution</h4><Distribution values={run.diagnostics.series[factor].values} onSelect={setSelectedCall} /><p>Box plot + every observed point</p></div><div><h4>Cumulative coverage</h4><SeriesChart coverage series={run.diagnostics.series[factor]} onSelect={setSelectedCall} /><p>Active-view fraction; abstentions are never zero Q</p></div></div></article>)}</div>
      <h3>Summary statistics</h3><div className="results-table-scroll"><table className="results-table"><thead><tr>{['Factor', 'Active', 'Abstained', 'Active fraction', 'Mean Q', 'Sample std Q', 'Min Q', 'Max Q'].map((label) => <th key={label}>{label}</th>)}</tr></thead><tbody>{run.diagnostics.summary.map((row) => <tr key={row.factor}><th>{row.factor}</th><td>{row.active}</td><td>{row.abstained}</td>{[row.activeFraction, row.mean, row.sampleStd, row.min, row.max].map((value, index) => <td key={index}>{percent(value)}</td>)}</tr>)}</tbody></table></div><p className="results-footnote">Sample standard deviation uses ddof=1; fewer than two active values is unavailable. A stable running mean can coexist with wide individual variability and frequent abstentions. These diagnostics do not prove convergence.</p>
      <h3>Q matrix</h3><div className="results-table-scroll"><table className="results-table"><thead><tr><th>Call</th>{run.factorOrder.map((factor) => <th key={factor}>{factor}</th>)}</tr></thead><tbody>{run.diagnostics.rows.map((row, index) => <tr key={index} className={index === call ? 'selected-call' : ''}><th><button className="text-button" onClick={() => setSelectedCall(index)}>Call {index + 1}</button></th>{run.factorOrder.map((factor) => <td key={factor}>{row[factor] === null ? 'Abstained' : percent(row[factor])}</td>)}</tr>)}</tbody></table></div>
      <div className="response-heading"><h3>Response inspector</h3><label>Call <select aria-label="Inspect call" value={call} onChange={(event) => setSelectedCall(Number(event.target.value))}>{run.responses.map((_, index) => <option value={index} key={index}>{index + 1}</option>)}</select></label></div>
      <p className="results-footnote">Confidence is model-reported and is not a calibrated probability.</p>
      {response?.factorAssessments?.map((assessment) => <article className="assessment-card" key={assessment.factor}><header><strong>{assessment.factor}</strong><span>{assessment.status}</span><span>Q: {percent(assessment.q)}</span><span>Confidence: {assessment.confidence === null ? 'Unavailable' : assessment.confidence}</span></header><p>{assessment.rationale}</p><small>Evidence: {assessment.evidenceRefs.join(', ') || 'None (abstention)'}</small></article>)}
      <div className="matrix-previews"><details><summary>P matrix</summary><pre>{JSON.stringify(response?.P, null, 2)}</pre></details><details><summary>Q matrix (decimal returns)</summary><pre>{JSON.stringify(response?.Q, null, 2)}</pre></details></div>
      <details className="run-details"><summary>Full validated response JSON</summary><pre>{JSON.stringify(response, null, 2)}</pre></details>
    </>}
    <details className="run-details"><summary>Frozen inputs and exact messages</summary>{run.frozen ? <><p>These are the messages and file revisions used for this batch, not the current editor contents.</p><pre>{JSON.stringify(run.frozen, null, 2)}</pre></> : <p>Unavailable for this legacy notebook run.</p>}</details>
    <details className="run-details" open><summary>Execution log</summary>{run.log?.length ? run.log.map((entry, index) => <p key={index}><code>{entry.at}</code> {entry.message}{entry.active !== undefined ? ` ${entry.active}/${run.factorOrder.length} active views.` : ''}</p>) : <p>{run.legacy ? 'No execution log was stored by the notebook.' : 'No completed calls yet.'}</p>}</details>
    <details className="run-details"><summary>Run metadata</summary>
      <p>Provider-reported token usage and estimated costs for the selected model. Reported token totals cover only available usage; complete is false if any attempted call has missing counts. Reasoning and cached tokens, when returned, are included in completion and prompt totals respectively, not additional tokens.</p>
      {run.metadata?.costs ? <>
        <p><strong>Estimated cost per iteration (USD)</strong> — standard token-only estimates using rates frozen at run start, not invoice amounts. Total of available estimates: <strong>{dollars(run.metadata.costs.reportedTotalUsd)}</strong>{!run.metadata.costs.complete && ' (partial; some iterations could not be priced)'}.</p>
        <div className="results-table-scroll"><table className="results-table"><thead><tr><th>Iteration</th><th>Estimated cost</th><th>Availability</th></tr></thead><tbody>{run.metadata.costs.iterations.map((entry) => <tr key={entry.iteration}><th>{entry.iteration}</th><td>{dollars(entry.estimatedUsd)}</td><td>{entry.reason ?? 'Estimated'}</td></tr>)}</tbody></table></div>
        {!run.metadata.costs.iterations.length && <p>No completed attempts yet.</p>}
      </> : <p>Cost estimates were not recorded for this historical run.</p>}
      <pre>{JSON.stringify(run.metadata ?? { tokenUsage: null, note: 'Token usage was not recorded for this run.' }, null, 2)}</pre>
    </details>
  </section>;
}
