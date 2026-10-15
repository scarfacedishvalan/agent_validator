export type MutationStrategy = 'explicit' | 'range' | 'random';
export type CombinationMode = 'one-at-a-time' | 'cartesian';

export interface MutationSettings {
  strategy: MutationStrategy;
  explicitValues: number[];
  rangeStart: number;
  rangeEnd: number;
  rangeStep: number;
  randomSpread: number;
  randomCount: number;
  seed: number;
}

export interface MutationProfile {
  id: string;
  name: string;
  fieldKeys: string[];
  settings: MutationSettings;
  combinationMode: CombinationMode;
  createdAt?: string;
  updatedAt: string;
}

export interface EvidenceVariant {
  id: string;
  values: Record<string, number>;
  changedFields: string[];
}

export interface VariantPreview {
  variants: EvidenceVariant[];
  totalCount: number;
  previewLimit?: number;
}

export const defaultMutationSettings: MutationSettings = {
  strategy: 'explicit',
  explicitValues: [0.5, 1, 2],
  rangeStart: 0.5,
  rangeEnd: 2,
  rangeStep: 0.5,
  randomSpread: 0.5,
  randomCount: 5,
  seed: 41,
};
