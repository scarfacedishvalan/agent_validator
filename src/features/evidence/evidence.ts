export type EvidenceValues = Record<string, number>;

export interface EvidenceSnapshot {
  id: string;
  name: string;
  asOf: string;
  values: EvidenceValues;
  createdAt?: string;
}

export interface MetricDefinition {
  key: string;
  label: string;
  group: string;
  unit: string;
  displayScale: number;
  precision: number;
  mutationEligible: boolean;
  description: string;
}

export const sampleSnapshot: EvidenceSnapshot = {
  id: 'factor-evidence-2026-10',
  name: 'Factor evidence · October 2026',
  asOf: '2026-10-01',
  values: {
    HML_valuation_zscore: 1.6,
    HML_return_1m: -0.032,
    HML_return_3m: -0.071,
    HML_return_12m: -0.045,
    RMW_return_3m: 0.042,
    RMW_return_12m: 0.083,
    MOM_return_1m: -0.025,
    MOM_return_12m: 0.124,
    treasury_yield_10y: 0.042,
  },
};
