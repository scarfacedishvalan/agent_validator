import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError } from '../../shared/api/client';
import { convergenceApi, type Preview, type RemoteDocuments, type RunListing } from './api';
import { documents, initialDraft, parseDocument, type DocumentId, type Draft } from './configuration';

const CACHE_KEY = 'signal-foundry.convergence-unsaved.v2';
type Cache = Partial<Record<DocumentId, { content: string; revision: string; conflict: boolean }>>;
const message = (error: unknown) => error instanceof Error ? error.message : 'Configuration sync failed.';

export function useConfigurationSync() {
  const [draft, setDraftState] = useState<Draft>({ ...initialDraft });
  const [remote, setRemote] = useState<RemoteDocuments | null>(null);
  const [dirty, setDirty] = useState<DocumentId[]>([]);
  const [conflicts, setConflicts] = useState<DocumentId[]>([]);
  const [saveErrors, setSaveErrors] = useState<Partial<Record<DocumentId, string>>>({});
  const [connected, setConnected] = useState(false);
  const [credentialsReady, setCredentialsReady] = useState(false);
  const [error, setError] = useState('');
  const [cacheError, setCacheError] = useState('');
  const [preview, setPreview] = useState<Preview | null>(null);
  const [previewError, setPreviewError] = useState('');
  const [previewPending, setPreviewPending] = useState(true);
  const [previewSource, setPreviewSource] = useState('');
  const [listing, setListing] = useState<RunListing>({ runs: [], issues: [] });
  const [saving, setSaving] = useState<DocumentId[]>([]);
  const draftRef = useRef(draft);
  const remoteRef = useRef<RemoteDocuments | null>(null);
  const dirtyRef = useRef(new Set<DocumentId>());
  const conflictsRef = useRef(new Set<DocumentId>());
  const inFlight = useRef(new Set<DocumentId>());
  const errorsRef = useRef<Partial<Record<DocumentId, string>>>({});
  const networkFailures = useRef(new Set<DocumentId>());
  const mounted = useRef(false);
  const refreshSequence = useRef(0);

  const publish = useCallback(() => {
    if (!mounted.current) return;
    setDraftState({ ...draftRef.current });
    setRemote(remoteRef.current ? { ...remoteRef.current } : null);
    setDirty([...dirtyRef.current]);
    setConflicts([...conflictsRef.current]);
    setSaving([...inFlight.current]);
    setSaveErrors({ ...errorsRef.current });
    if (remoteRef.current) {
      const cache: Cache = {};
      for (const id of dirtyRef.current) cache[id] = { content: draftRef.current[id], revision: remoteRef.current[id].revision, conflict: conflictsRef.current.has(id) };
      try {
        localStorage.setItem(CACHE_KEY, JSON.stringify(cache));
      } catch (storageError) {
        setCacheError(`Unsaved draft recovery is unavailable: ${message(storageError)}`);
      }
    }
  }, []);

  const applyRemote = useCallback((incoming: RemoteDocuments) => {
    const previous = remoteRef.current;
    const next = { ...incoming };
    for (const { id } of documents) {
      if (inFlight.current.has(id) && previous) {
        next[id] = previous[id];
        continue;
      }
      if (dirtyRef.current.has(id)) {
        if (incoming[id].content === draftRef.current[id]) {
          dirtyRef.current.delete(id);
          conflictsRef.current.delete(id);
          delete errorsRef.current[id];
        } else if (previous && incoming[id].revision !== previous[id].revision) {
          conflictsRef.current.add(id);
        }
      } else {
        draftRef.current[id] = incoming[id].content;
      }
    }
    remoteRef.current = next;
    publish();
  }, [publish]);

  const refresh = useCallback(async () => {
    const sequence = ++refreshSequence.current;
    try {
      const result = await convergenceApi.documents();
      if (!mounted.current || sequence !== refreshSequence.current) return;
      if (!remoteRef.current) {
        const serverDraft = { ...initialDraft };
        for (const { id } of documents) serverDraft[id] = result.documents[id].content;
        draftRef.current = serverDraft;
        try {
          const cached: unknown = JSON.parse(localStorage.getItem(CACHE_KEY) ?? '{}');
          if (typeof cached !== 'object' || cached === null) throw new Error('Invalid recovery cache.');
          for (const { id } of documents) {
            const entry: unknown = Reflect.get(cached, id);
            if (entry === undefined) continue;
            if (typeof entry !== 'object' || entry === null || !('content' in entry) || typeof entry.content !== 'string' || !('revision' in entry) || typeof entry.revision !== 'string') throw new Error('Invalid recovery cache entry.');
            if (entry.content !== result.documents[id].content) {
              draftRef.current[id] = entry.content;
              dirtyRef.current.add(id);
              if (entry.revision !== result.documents[id].revision || ('conflict' in entry && entry.conflict === true)) conflictsRef.current.add(id);
            }
          }
        } catch (storageError) {
          setCacheError(`Could not recover browser edits: ${message(storageError)}`);
        }
      }
      for (const id of networkFailures.current) delete errorsRef.current[id];
      networkFailures.current.clear();
      applyRemote(result.documents);
      setCredentialsReady(result.credentialsReady);
      setConnected(true);
      setError('');
    } catch (requestError) {
      if (mounted.current && sequence === refreshSequence.current) {
        setConnected(false);
        setError(message(requestError));
      }
    }
  }, [applyRemote]);

  useEffect(() => {
    mounted.current = true;
    void refresh();
    const events = new EventSource(convergenceApi.eventsUrl);
    const changed = () => { void refresh(); void convergenceApi.runs().then((result) => { if (mounted.current) setListing(result); }).catch((requestError: unknown) => { if (mounted.current) setError(message(requestError)); }); };
    events.addEventListener('changed', changed);
    events.addEventListener('sync-error', (event) => {
      setError(`File change feed error: ${(event as MessageEvent<string>).data}`);
      setConnected(false);
    });
    events.onopen = changed;
    events.onerror = () => {
      if (mounted.current) {
        setConnected(false);
        setError('Live sync disconnected. Reconnecting automatically; unsaved edits are retained.');
      }
    };
    return () => { mounted.current = false; events.close(); };
  }, [refresh]);

  const setDraft = (update: Draft | ((previous: Draft) => Draft)) => {
    setCacheError('');
    const next = typeof update === 'function' ? update(draftRef.current) : update;
    for (const { id } of documents) {
      if (next[id] !== draftRef.current[id]) {
        delete errorsRef.current[id];
        if (remoteRef.current && next[id] === remoteRef.current[id].content) {
          dirtyRef.current.delete(id);
          conflictsRef.current.delete(id);
        } else {
          dirtyRef.current.add(id);
        }
      }
    }
    draftRef.current = next;
    setPreviewPending(true);
    publish();
  };

  useEffect(() => {
    if (!connected || !remote) return;
    const timer = window.setTimeout(() => {
      for (const doc of documents) {
        const id = doc.id;
        if (!dirtyRef.current.has(id) || inFlight.current.has(id) || conflictsRef.current.has(id) || errorsRef.current[id] || parseDocument(doc, draftRef.current[id]).error) continue;
        const content = draftRef.current[id];
        const revision = remoteRef.current![id].revision;
        inFlight.current.add(id);
        publish();
        void convergenceApi.save(id, content, revision).then((saved) => {
          if (!remoteRef.current) return;
          remoteRef.current = { ...remoteRef.current, [id]: saved };
          if (draftRef.current[id] === content) dirtyRef.current.delete(id);
          delete errorsRef.current[id];
        }).catch((requestError: unknown) => {
          errorsRef.current[id] = message(requestError);
          if (!(requestError instanceof ApiError)) networkFailures.current.add(id);
          if (requestError instanceof ApiError && requestError.status === 409) {
            conflictsRef.current.add(id);
          }
        }).finally(() => {
          inFlight.current.delete(id);
          publish();
          // Re-fetch after write acknowledgement, including any concurrent external edit.
          void refresh();
        });
      }
    }, 600);
    return () => window.clearTimeout(timer);
  }, [draft, remote, connected, publish, refresh]);

  useEffect(() => {
    if (!connected) { setPreviewPending(false); setPreview(null); return; }
    const controller = new AbortController();
    setPreviewPending(true);
    const timer = window.setTimeout(() => {
      void convergenceApi.preview(draft, controller.signal).then((result) => {
        if (controller.signal.aborted) return;
        setPreview(result);
        setPreviewSource(JSON.stringify(draft));
        setPreviewError('');
      }).catch((requestError: unknown) => {
        if (controller.signal.aborted) return;
        setPreview(null);
        setPreviewError(message(requestError));
      }).finally(() => { if (!controller.signal.aborted) setPreviewPending(false); });
    }, 300);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [draft, connected]);

  const resolveConflict = (id: DocumentId, keepDraft: boolean) => {
    if (!remoteRef.current) return;
    if (!keepDraft) draftRef.current = { ...draftRef.current, [id]: remoteRef.current[id].content };
    conflictsRef.current.delete(id);
    delete errorsRef.current[id];
    if (keepDraft) dirtyRef.current.add(id); else dirtyRef.current.delete(id);
    publish();
  };
  const retrySaves = () => {
    for (const { id } of documents) if (!conflictsRef.current.has(id)) delete errorsRef.current[id];
    publish();
    void refresh();
  };
  const allSaved = !!remote && dirty.length === 0 && saving.length === 0 && conflicts.length === 0;
  return { draft, setDraft, remote, dirty, saving, conflicts, saveErrors, connected, credentialsReady,
    error, cacheError, preview, previewError, previewPending: previewPending || previewSource !== JSON.stringify(draft), listing, allSaved, refresh, resolveConflict, retrySaves };
}
