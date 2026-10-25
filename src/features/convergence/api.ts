import { apiRequest, apiRoot } from '../../shared/api/client';
import type { DocumentId, Draft, JsonValue } from './configuration';

export interface RemoteDocument {
  id: DocumentId;
  path: string;
  content: string;
  revision: string;
  error: string | null;
}
export type RemoteDocuments = Record<DocumentId, RemoteDocument>;
export interface Message { role: string; content: string }
export interface Preview { messages: Message[]; configuration: Record<string, JsonValue> }
export interface RunSummary {
  id: string;
  name: string | null;
  status: string;
  startedAt: string;
  finishedAt: string | null;
  requestedIterations: number;
  completedIterations: number;
  complete: boolean;
  model: string | null;
  personalityKey: string | null;
  outputPath: string;
  error: string | null;
  persistenceError: string | null;
  legacy: boolean;
}
export interface Assessment {
  factor: string;
  status: 'view' | 'abstain';
  q: number | null;
  confidence: number | null;
  evidenceRefs: string[];
  rationale: string;
}
export interface FactorResponse {
  factorOrder: string[];
  activeFactors: string[];
  factorAssessments: Assessment[];
  Q: number[][];
  P: number[][];
  targetHorizon: string;
  qReturnConvention: string;
  asOf: string;
}
export interface SummaryRow {
  factor: string; active: number; abstained: number; activeFraction: number | null;
  mean: number | null; sampleStd: number | null; min: number | null; max: number | null;
}
export interface FactorSeries { values: (number | null)[]; runningMean: (number | null)[]; coverage: number[] }
export interface RunDetail extends RunSummary {
  factorOrder: string[];
  evidenceSnapshot: JsonValue;
  responses: FactorResponse[];
  log?: { at: string; message: string; iteration?: number; active?: number }[];
  provenanceWarning?: string;
  frozen?: Preview & { sourceDocuments: RemoteDocuments };
  diagnostics: {
    rows: Record<string, number | null>[];
    summary: SummaryRow[];
    series: Record<string, FactorSeries>;
  };
}
export interface RunListing { runs: RunSummary[]; issues: { path: string; error: string }[] }
export const convergenceApi = {
  documents: () => apiRequest<{ documents: RemoteDocuments; credentialsReady: boolean }>('/convergence/config/documents'),
  save: (id: DocumentId, content: string, revision: string) => apiRequest<RemoteDocument>(`/convergence/config/documents/${id}`, { method: 'PUT', body: JSON.stringify({ content, revision }) }),
  preview: (documents: Draft, signal?: AbortSignal) => apiRequest<Preview>('/convergence/preview', { method: 'POST', body: JSON.stringify({ documents }), signal }),
  runs: () => apiRequest<RunListing>('/convergence/runs'),
  run: (id: string) => apiRequest<RunDetail>(`/convergence/runs/${encodeURIComponent(id)}`),
  start: (revisions: Record<DocumentId, string>) => apiRequest<RunSummary>('/convergence/runs', { method: 'POST', body: JSON.stringify({ revisions, confirmLiveCalls: true }) }),
  stop: (id: string) => apiRequest<RunSummary>(`/convergence/runs/${encodeURIComponent(id)}/stop`, { method: 'POST' }),
  eventsUrl: `${apiRoot}/convergence/events`,
};
