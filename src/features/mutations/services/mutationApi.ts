import { apiRequest } from '../../../shared/api/client';
import type {
  CombinationMode,
  EvidenceVariant,
  MutationProfile,
  MutationSettings,
  VariantPreview,
} from '../types';

interface ProfileListResponse {
  profiles: MutationProfile[];
  total: number;
}

interface VariantPreviewResponse extends VariantPreview {
  previewLimit: number;
}

interface VariantGenerateResponse {
  batchId: string;
  variantIds: string[];
  totalGenerated: number;
}

interface VariantBatchResponse {
  variants: EvidenceVariant[];
}

export function listMutationProfiles(): Promise<ProfileListResponse> {
  return apiRequest('/mutation-profiles');
}

export function saveMutationProfile(
  profile: Pick<MutationProfile, 'name' | 'fieldKeys' | 'settings' | 'combinationMode'>,
  profileId?: string,
): Promise<MutationProfile> {
  const path = profileId
    ? `/mutation-profiles/${encodeURIComponent(profileId)}`
    : '/mutation-profiles';
  return apiRequest(path, {
    method: profileId ? 'PUT' : 'POST',
    body: JSON.stringify(profile),
  });
}

export function previewEvidenceVariants(
  snapshotId: string,
  fieldKeys: string[],
  settings: MutationSettings,
  combinationMode: CombinationMode,
): Promise<VariantPreviewResponse> {
  return apiRequest('/variants/preview', {
    method: 'POST',
    body: JSON.stringify({ snapshotId, fieldKeys, settings, combinationMode }),
  });
}

export async function generateEvidenceVariants(
  snapshotId: string,
  fieldKeys: string[],
  settings: MutationSettings,
  combinationMode: CombinationMode,
  profileId?: string,
): Promise<EvidenceVariant[]> {
  const result = await apiRequest<VariantGenerateResponse>('/variants/generate', {
    method: 'POST',
    body: JSON.stringify({ snapshotId, fieldKeys, settings, combinationMode, profileId }),
  });
  const batch = await apiRequest<VariantBatchResponse>(
    `/variants?batch_id=${encodeURIComponent(result.batchId)}`,
  );
  return batch.variants;
}
