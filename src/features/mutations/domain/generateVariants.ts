import type { EvidenceValues } from '../../evidence/evidence';
import type {
  CombinationMode,
  MutationSettings,
  VariantPreview,
} from '../types';

const previewLimit = 100;

export function validateMutation(
  fieldKeys: string[],
  settings: MutationSettings,
): string | null {
  if (fieldKeys.length === 0) return 'Select at least one evidence field.';

  if (settings.strategy === 'explicit') {
    if (settings.explicitValues.length === 0) return 'Add at least one explicit value.';
    if (settings.explicitValues.some((value) => !Number.isFinite(value))) {
      return 'Explicit values must be valid numbers.';
    }
  }

  if (settings.strategy === 'range') {
    if (![settings.rangeStart, settings.rangeEnd, settings.rangeStep].every(Number.isFinite)) {
      return 'Range values must be valid numbers.';
    }
    if (settings.rangeStep <= 0 || settings.rangeEnd < settings.rangeStart) {
      return 'Use a positive step and an end value greater than or equal to the start.';
    }
  }

  if (settings.strategy === 'random') {
    if (![settings.randomSpread, settings.randomCount, settings.seed].every(Number.isFinite)) {
      return 'Random settings must be valid numbers.';
    }
    if (settings.randomSpread < 0 || !Number.isInteger(settings.randomCount)
      || settings.randomCount < 1 || settings.randomCount > previewLimit) {
      return 'Use a non-negative spread and 1 to 100 whole-number samples.';
    }
  }

  return null;
}

function valuesForField(
  baseline: number,
  settings: MutationSettings,
  random: () => number,
): number[] {
  if (settings.strategy === 'explicit') return settings.explicitValues.slice(0, previewLimit);

  if (settings.strategy === 'range') {
    const values: number[] = [];
    for (let value = settings.rangeStart; value <= settings.rangeEnd + 1e-9 && values.length < previewLimit; value += settings.rangeStep) {
      values.push(Number(value.toFixed(8)));
    }
    return values;
  }

  return Array.from({ length: Math.min(settings.randomCount, previewLimit) }, () =>
    Number((baseline + (random() * 2 - 1) * settings.randomSpread).toFixed(6)),
  );
}

function seededRandom(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state * 1664525 + 1013904223) >>> 0;
    return state / 4294967296;
  };
}

export function generateVariantPreview(
  baseValues: EvidenceValues,
  fieldKeys: string[],
  settings: MutationSettings,
  combinationMode: CombinationMode,
  displayScales: Record<string, number> = {},
): VariantPreview {
  const random = seededRandom(settings.seed);
  const valuesByField = fieldKeys.map((key) => {
    const displayScale = displayScales[key] || 1;
    return valuesForField(baseValues[key] * displayScale, settings, random)
      .map((value) => value / displayScale);
  });
  const countsByField = fieldKeys.map(() => {
    if (settings.strategy === 'explicit') return settings.explicitValues.length;
    if (settings.strategy === 'random') return settings.randomCount;
    return Math.floor((settings.rangeEnd - settings.rangeStart) / settings.rangeStep + 1e-9) + 1;
  });
  const totalCount = combinationMode === 'one-at-a-time'
    ? countsByField.reduce((sum, count) => sum + count, 0)
    : countsByField.reduce((product, count) => product * count, 1);
  const variants: VariantPreview['variants'] = [];

  if (combinationMode === 'one-at-a-time') {
    fieldKeys.forEach((fieldKey, fieldIndex) => {
      valuesByField[fieldIndex].forEach((value) => {
        if (variants.length >= previewLimit) return;
        variants.push({
          id: `variant-${variants.length + 1}`,
          values: { ...baseValues, [fieldKey]: value },
          changedFields: [fieldKey],
        });
      });
    });
  } else {
    const visit = (fieldIndex: number, nextValues: Record<string, number>) => {
      if (variants.length >= previewLimit) return;
      if (fieldIndex === fieldKeys.length) {
        variants.push({
          id: `variant-${variants.length + 1}`,
          values: { ...baseValues, ...nextValues },
          changedFields: [...fieldKeys],
        });
        return;
      }

      const fieldKey = fieldKeys[fieldIndex];
      valuesByField[fieldIndex].forEach((value) => {
        if (variants.length >= previewLimit) return;
        visit(fieldIndex + 1, { ...nextValues, [fieldKey]: value });
      });
    };
    visit(0, {});
  }

  return { variants, totalCount };
}
