import type { EvidenceSnapshot, MetricDefinition } from '../evidence';
import { apiRequest } from '../../../shared/api/client';

interface SnapshotListResponse {
  snapshots: EvidenceSnapshot[];
  total: number;
}

export function listEvidenceSnapshots(): Promise<SnapshotListResponse> {
  return apiRequest('/evidence/snapshots?limit=100');
}

export function createEvidenceSnapshot(
  snapshot: Pick<EvidenceSnapshot, 'name' | 'asOf' | 'values'>,
): Promise<EvidenceSnapshot> {
  return apiRequest('/evidence/snapshots', {
    method: 'POST',
    body: JSON.stringify(snapshot),
  });
}

export function listMetricDefinitions(): Promise<MetricDefinition[]> {
  return apiRequest('/evidence/metrics');
}
