import evidence from '../../../backend/fixtures/evidence_snapshot_example.json';
import personalities from '../../../backend/fixtures/personalities.json';
import defaults from '../../../backend/fixtures/factor_view_defaults.json';
import factors from '../../../backend/fixtures/factor_definitions.json';
import metrics from '../../../backend/fixtures/metric_definitions.json';
import contract from '../../../backend/fixtures/factor_view_output_contract.json';
import system from '../../../backend/prompts/system_prompt.txt?raw';
import user from '../../../backend/prompts/user_prompt.txt?raw';
import policy from '../../../backend/prompts/shared_financial_grounding_policy.txt?raw';
import runSettings from '../../../backend/fixtures/convergence_run_settings.json';

export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };
export type JsonObject = { [key: string]: JsonValue };
export type DocumentId = 'run' | 'evidence' | 'personalities' | 'defaults' | 'factors' | 'metrics' | 'system' | 'user' | 'policy' | 'contract';
export interface ConfigDocument {
  id: DocumentId;
  label: string;
  description: string;
  path: string;
  format: 'json' | 'text';
  initial: string;
}
const json = (value: unknown) => JSON.stringify(value, null, 2);
export const documents: ConfigDocument[] = [
  { id: 'run', label: 'Run settings', description: 'Define the repeated-call experiment. Each batch holds its inputs fixed.', path: 'backend/fixtures/convergence_run_settings.json', format: 'json', initial: json(runSettings) },
  { id: 'evidence', label: 'Evidence snapshot', description: 'The same dated observations are supplied to every call. Returns are stored as decimals.', path: 'backend/fixtures/evidence_snapshot_example.json', format: 'json', initial: json(evidence) },
  { id: 'personalities', label: 'Personalities', description: 'Select a personality to edit its ordered instructions. Shared policy always takes precedence.', path: 'backend/fixtures/personalities.json', format: 'json', initial: json(personalities) },
  { id: 'defaults', label: 'Runtime defaults', description: 'Forecast horizon, return convention and optional decimal Q bounds. Null means unbounded.', path: 'backend/fixtures/factor_view_defaults.json', format: 'json', initial: json(defaults) },
  { id: 'factors', label: 'Factor catalog', description: 'Eligible factors and positive-return meaning. Array order defines the columns of P.', path: 'backend/fixtures/factor_definitions.json', format: 'json', initial: json(factors) },
  { id: 'metrics', label: 'Metric catalog', description: 'Evidence meanings, units and display metadata. Edit any field without losing other properties.', path: 'backend/fixtures/metric_definitions.json', format: 'json', initial: json(metrics) },
  { id: 'system', label: 'System template', description: 'Shared instructions and runtime placeholders. The output schema is appended after rendering.', path: 'backend/prompts/system_prompt.txt', format: 'text', initial: system },
  { id: 'user', label: 'User template', description: 'The selected personality and evidence are injected into this message.', path: 'backend/prompts/user_prompt.txt', format: 'text', initial: user },
  { id: 'policy', label: 'Grounding policy', description: 'Financial grounding rules shared by every personality.', path: 'backend/prompts/shared_financial_grounding_policy.txt', format: 'text', initial: policy },
  { id: 'contract', label: 'Output contract', description: 'Full response JSON Schema, including the example. Edit raw JSON to change the contract.', path: 'backend/fixtures/factor_view_output_contract.json', format: 'json', initial: json(contract) },
];
export type Draft = Record<DocumentId, string>;
export const initialDraft = Object.fromEntries(documents.map((doc) => [doc.id, doc.initial])) as Draft;
export function isObject(value: JsonValue): value is JsonObject {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
export function parseDocument(doc: ConfigDocument, source: string): { value: JsonValue; error: string | null } {
  if (doc.format === 'text') return { value: source, error: source.trim() ? null : 'Document must not be blank.' };
  let value: JsonValue = null;
  try {
    value = JSON.parse(source, (_key, item: unknown) => {
      if (typeof item === 'number' && !Number.isFinite(item)) throw new Error('Numbers must be finite.');
      return item;
    });
    if (doc.id === 'factors' || doc.id === 'metrics') {
      if (!Array.isArray(value) || !value.length || !value.every(isObject)) throw new Error('Expected a non-empty array of objects.');
      const keys = value.map((item) => item.key);
      if (keys.some((key) => typeof key !== 'string' || !key.trim()) || new Set(keys).size !== keys.length) throw new Error('Catalog keys must be non-blank and unique.');
      if (doc.id === 'factors' && value.some((item) => typeof item.name !== 'string' || typeof item.positive_direction !== 'string' || !Array.isArray(item.evidence_metric_keys) || !item.evidence_metric_keys.every((key) => typeof key === 'string'))) throw new Error('Factors need a name, positive_direction and evidence_metric_keys array.');
    } else {
      if (!isObject(value)) throw new Error('Expected a JSON object.');
      const object = value;
      if (doc.id === 'personalities' && (!Object.keys(object).length || Object.entries(object).some(([key, instructions]) => !key.trim() || !Array.isArray(instructions) || !instructions.length || instructions.some((line) => typeof line !== 'string' || !line.trim())))) throw new Error('Each personality needs a name and a non-empty array of instructions.');
      if (doc.id === 'run' && (typeof object.iterations !== 'number' || !Number.isSafeInteger(object.iterations) || object.iterations < 1 || ['name', 'model', 'personality', 'outputDirectory'].some((key) => typeof object[key] !== 'string' || !String(object[key]).trim()))) throw new Error('Use a positive integer iteration count and non-blank run fields.');
      if (doc.id === 'evidence' && (typeof object.name !== 'string' || typeof object.asOf !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(object.asOf) || !isObject(object.values) || Object.values(object.values).some((item) => typeof item !== 'number'))) throw new Error('Evidence needs name, asOf (YYYY-MM-DD) and numeric values.');
      if (doc.id === 'defaults') {
        if (['target_horizon', 'q_return_convention'].some((key) => typeof object[key] !== 'string' || !String(object[key]).trim())) throw new Error('Horizon and return convention are required.');
        if (['q_min', 'q_max'].some((key) => object[key] !== null && typeof object[key] !== 'number')) throw new Error('Q bounds must be numbers or null.');
        if (typeof object.q_min === 'number' && typeof object.q_max === 'number' && object.q_min > object.q_max) throw new Error('Q minimum must not exceed maximum.');
      }
      if (doc.id === 'contract' && (object.type !== 'object' || !object.properties || !isObject(object.properties))) throw new Error('Expected an object JSON Schema with properties.');
    }
    return { value, error: null };
  } catch (error) {
    return { value, error: error instanceof Error ? error.message : 'Invalid document.' };
  }
}

export function resolveDraft(draft: Draft) {
  const parsed = Object.fromEntries(documents.map((doc) => [doc.id, parseDocument(doc, draft[doc.id])])) as Record<DocumentId, ReturnType<typeof parseDocument>>;
  const errors = documents.flatMap((doc) => parsed[doc.id].error ? [`${doc.label}: ${parsed[doc.id].error}`] : []);
  return { parsed, errors };
}
