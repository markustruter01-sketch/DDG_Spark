import { useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  getEntitiesApiIngestEntitiesGetQueryKey,
  getGetFileApiIngestFilesFileIdGetQueryKey,
  getListFilesApiIngestFilesGetQueryKey,
  useApproveApiIngestFilesFileIdMappingPost,
  useEntitiesApiIngestEntitiesGet,
  useGetFileApiIngestFilesFileIdGet,
  useListFilesApiIngestFilesGet,
  type SourceFile,
} from '@workspace/api-client-react';
import { PRODUCT_NAME } from '@/lib/brand-assets';

const NONE = '';

function statusDot(file: SourceFile): string {
  if (file.mapping?.status === 'approved') return 'status-dot';
  if (file.mapping?.entity) return 'status-dot status-dot-late';
  return 'status-dot status-dot-problem';
}

function statusText(file: SourceFile): string {
  const m = file.mapping;
  if (!m) return 'No mapping';
  if (m.status === 'approved') return `Approved · v${m.version}`;
  return `Proposed · ${Math.round(m.confidence * 100)}%`;
}

function errorText(error: unknown): string {
  const detail = (error as { data?: { detail?: unknown } } | null)?.data?.detail;
  return typeof detail === 'string' ? detail : 'The mapping could not be saved.';
}

function MappingEditor({ fileId, onClose }: { fileId: string; onClose: () => void }) {
  const queryClient = useQueryClient();
  const file = useGetFileApiIngestFilesFileIdGet(fileId, {
    query: { queryKey: getGetFileApiIngestFilesFileIdGetQueryKey(fileId) },
  });
  const entities = useEntitiesApiIngestEntitiesGet({
    query: { queryKey: getEntitiesApiIngestEntitiesGetQueryKey() },
  });
  const [entity, setEntity] = useState(NONE);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [refs, setRefs] = useState<Record<string, string>>({});
  const [sameFolder, setSameFolder] = useState(true);
  const approve = useApproveApiIngestFilesFileIdMappingPost({
    mutation: {
      onSuccess: () => {
        void queryClient.invalidateQueries({ queryKey: getListFilesApiIngestFilesGetQueryKey() });
        void queryClient.invalidateQueries({ queryKey: getGetFileApiIngestFilesFileIdGetQueryKey(fileId) });
      },
    },
  });

  const mapping = file.data?.mapping;
  useEffect(() => {
    setEntity(mapping?.entity ?? NONE);
    setFields({ ...(mapping?.fields ?? {}) });
    setRefs({ ...(mapping?.refs ?? {}) });
  }, [mapping]);

  const detail = file.data;
  const targetFields = entities.data?.find((e) => e.name === entity)?.fields ?? [];
  const entityNames = entities.data?.map((e) => e.name) ?? [];
  const columns = detail?.columns ?? [];
  const isDocument = detail?.format === 'document';

  const pick = (
    current: Record<string, string>,
    set: (next: Record<string, string>) => void,
    key: string,
    column: string,
  ) => {
    const next = { ...current };
    if (column === NONE) delete next[key];
    else next[key] = column;
    set(next);
  };

  return (
    <div className="drawer-backdrop" role="presentation" onClick={onClose}>
      <aside
        className="evidence-drawer glass-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="mapping-heading"
        onClick={(event) => event.stopPropagation()}
        data-testid="drawer-mapping"
      >
        <div className="drawer-heading">
          <div>
            <div className="eyebrow">{detail?.source_system ?? 'Source file'}</div>
            <h2 className="panel-heading mono" id="mapping-heading">{detail?.path ?? 'Loading'}</h2>
          </div>
          <button className="button-secondary" type="button" onClick={onClose}>Close</button>
        </div>
        {!detail ? (
          <div className="empty-inline"><span className="status-dot status-dot-empty" />Loading</div>
        ) : (
          <>
            {mapping && (
              <p className="panel-subtitle" data-testid="text-mapping-reasons">
                {mapping.proposed_by === 'person' ? 'Set by a person' : `Proposed by ${mapping.proposed_by}`}
                {' · '}{mapping.reasons.join(' · ')}
              </p>
            )}
            <h3 className="evidence-section-title">Feeds</h3>
            <select
              className="mapping-select"
              value={entity}
              onChange={(e) => { setEntity(e.target.value); setFields({}); }}
              disabled={isDocument}
              data-testid="select-entity"
            >
              <option value={NONE}>Choose an entity</option>
              {entityNames.map((name) => <option key={name} value={name}>{name}</option>)}
            </select>

            {!isDocument && entity && (
              <>
                <h3 className="evidence-section-title">Fields</h3>
                <dl className="evidence-fields">
                  {targetFields.map((target) => (
                    <div key={target}>
                      <dt>{target}</dt>
                      <dd>
                        <select
                          className="mapping-select"
                          value={fields[target] ?? NONE}
                          onChange={(e) => pick(fields, setFields, target, e.target.value)}
                          data-testid={`select-field-${target}`}
                        >
                          <option value={NONE}>—</option>
                          {columns.map((c) => <option key={c} value={c}>{c}</option>)}
                        </select>
                      </dd>
                    </div>
                  ))}
                </dl>
                <h3 className="evidence-section-title">Links to other entities</h3>
                <dl className="evidence-fields">
                  {Object.keys(refs).map((name) => (
                    <div key={name}>
                      <dt>{name}</dt>
                      <dd>
                        <select
                          className="mapping-select"
                          value={refs[name]}
                          onChange={(e) => pick(refs, setRefs, name, e.target.value)}
                          data-testid={`select-ref-${name}`}
                        >
                          <option value={NONE}>Remove link</option>
                          {columns.map((c) => <option key={c} value={c}>{c}</option>)}
                        </select>
                      </dd>
                    </div>
                  ))}
                </dl>
                <select
                  className="mapping-select"
                  value={NONE}
                  onChange={(e) => e.target.value && pick(refs, setRefs, e.target.value, columns[0] ?? NONE)}
                  data-testid="select-add-ref"
                >
                  <option value={NONE}>Add a link to…</option>
                  {entityNames.filter((n) => !(n in refs)).map((n) => <option key={n} value={n}>{n}</option>)}
                </select>
                <h3 className="evidence-section-title">First rows</h3>
                <pre className="raw-source">{JSON.stringify(detail.sample.slice(0, 3), null, 2)}</pre>
              </>
            )}

            <div className="ask-controls">
              {detail.same_folder_files > 0 ? (
                <label className="toggle-label">
                  <input
                    type="checkbox"
                    checked={sameFolder}
                    onChange={(e) => setSameFolder(e.target.checked)}
                    data-testid="checkbox-same-folder"
                  />
                  Also apply to {detail.same_folder_files} other files in this folder with the same columns
                </label>
              ) : <span />}
            </div>
            <div className="ask-controls">
              <span className="request-error" role="alert">{approve.isError ? errorText(approve.error) : ''}</span>
              <button
                className="button-secondary"
                type="button"
                disabled={!entity || approve.isPending}
                onClick={() => approve.mutate({ fileId, data: { entity, fields, refs, same_folder: sameFolder } })}
                data-testid="button-approve-mapping"
              >
                {approve.isPending ? 'Saving' : mapping?.status === 'approved' ? 'Save new version' : 'Approve'}
              </button>
            </div>
          </>
        )}
      </aside>
    </div>
  );
}

export default function MappingsPage() {
  const files = useListFilesApiIngestFilesGet({ query: { queryKey: getListFilesApiIngestFilesGetQueryKey() } });
  const [open, setOpen] = useState<string | null>(null);
  const rows = files.data ?? [];
  const approved = rows.filter((f) => f.mapping?.status === 'approved').length;

  return (
    <section className="content">
      <div className="eyebrow">{PRODUCT_NAME} / Data</div>
      <h1 className="page-heading">Mappings</h1>
      <p className="page-description">
        Each source file needs an approved mapping before it loads. {rows.length ? `${approved} of ${rows.length} approved.` : ''}
      </p>
      <div className="glass-panel page-grid" data-testid="panel-mappings">
        {files.isLoading ? (
          <div className="panel-pad"><div className="skeleton-line" /></div>
        ) : files.isError ? (
          <div className="panel-pad" role="alert">The file list could not be reached.</div>
        ) : rows.length === 0 ? (
          <div className="page-state"><div className="empty-inline"><span className="status-dot status-dot-empty" />No files catalogued yet</div></div>
        ) : (
          <div className="workspace-list">
            {rows.map((file) => (
              <button
                key={file.id}
                type="button"
                className="workspace-row mapping-row"
                onClick={() => setOpen(file.id)}
                data-testid={`row-file-${file.path}`}
              >
                <span className="mono">{file.path}</span>
                <span>{file.mapping?.entity ?? '—'}</span>
                <span className="mono">{file.records} {file.format === 'document' ? 'passages' : 'rows'}</span>
                <span className="health-state"><span className={statusDot(file)} aria-hidden="true" />{statusText(file)}</span>
              </button>
            ))}
          </div>
        )}
      </div>
      {open && <MappingEditor fileId={open} onClose={() => setOpen(null)} />}
    </section>
  );
}
