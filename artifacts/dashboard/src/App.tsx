import { lazy, Suspense, useState, type CSSProperties, type FormEvent, type ReactNode } from 'react';
import { QueryClient, QueryClientProvider, useQueryClient } from '@tanstack/react-query';
import { ErrorBoundary } from '@/components/error-boundary';
import { Toaster } from '@/components/ui/toaster';
import { TooltipProvider } from '@/components/ui/tooltip';
import SignInPage from '@/components/sign-in-page';
import {
  BrandLockup,
  IntroLoader,
  PRODUCT_NAME,
  useBrandAssets,
} from '@/lib/brand-assets';
import {
  getHealthApiHealthGetQueryKey,
  getModelsApiModelsGetQueryKey,
  getPackApiPackGetQueryKey,
  getSessionInfoApiAuthSessionGetQueryKey,
  useHealthApiHealthGet,
  useModelsApiModelsGet,
  usePackApiPackGet,
  useSessionInfoApiAuthSessionGet,
} from '@workspace/api-client-react';
import { ArrowRight, ChevronDown, Grid2X2, LogOut, Settings2 } from 'lucide-react';
import {
  Link,
  Redirect,
  Route,
  Switch,
  useLocation,
  useRoute,
  Router as WouterRouter,
} from 'wouter';

const StageZeroCore = lazy(() => import('@/components/stage-zero-core'));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
});

type EvidenceCitation = { entity: string; record_id: string };
type AnswerStatement = {
  text: string;
  citations: EvidenceCitation[];
  unsupported: boolean;
};
type AskResponse = {
  statements: AnswerStatement[];
  unsupported_statements: string[];
  model: string;
  routing_reason: string;
  gateway_mode: string;
};
type EvidenceResponse = {
  entity: string;
  record: Record<string, unknown>;
  raw_record: { payload: unknown };
};

function displayValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'object') return JSON.stringify(value, null, 2) ?? '—';
  return String(value);
}

function LoadingScreen() {
  return (
    <main className="page-graphite page-state" aria-label="Loading">
      <div className="sign-in-card sign-in-skeleton">
        <div className="skeleton-block" />
        <div className="skeleton-block" />
        <div className="skeleton-block" />
      </div>
    </main>
  );
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <section className="glass-panel error-card" role="alert">
      <h2>Unable to load this page</h2>
      <p>{message}</p>
      <button className="button-secondary" type="button" onClick={onRetry} data-testid="button-retry">
        Try again
      </button>
    </section>
  );
}

function WorkspaceShell({
  children,
  markUrl,
  landscapeAvailable,
  activePath,
  email,
}: {
  children: ReactNode;
  markUrl: string | null;
  landscapeAvailable: boolean;
  activePath: string;
  email: string;
}) {
  const queryClient = useQueryClient();
  const [, setLocation] = useLocation();
  const [signingOut, setSigningOut] = useState(false);
  const [signOutError, setSignOutError] = useState(false);

  async function handleSignOut() {
    setSigningOut(true);
    setSignOutError(false);
    try {
      const response = await fetch('/api/auth/sign-out', {
        method: 'POST',
        credentials: 'same-origin',
      });
      if (!response.ok) throw new Error('Sign-out failed.');
      queryClient.clear();
      setLocation('/sign-in');
    } catch {
      setSignOutError(true);
      setSigningOut(false);
    }
  }

  return (
    <div
      className={`workspace ${activePath === '/' ? 'workspace-home' : 'page-graphite'} ${landscapeAvailable ? 'has-landscape' : ''}`}
    >
      <aside className="side-rail">
        <Link className="rail-brand" href="/" aria-label={`${PRODUCT_NAME} home`} data-testid="link-home-brand">
          <BrandLockup markUrl={markUrl} />
        </Link>
        <div className="workspace-switcher" aria-label="Current workspace">
          <span className="workspace-avatar">DDG</span>
          <span className="workspace-meta"><strong>{PRODUCT_NAME}</strong><span>Stage 1</span></span>
          <ChevronDown size={14} aria-hidden="true" />
        </div>
        <div className="section-label">Workspace</div>
        <nav className="rail-nav" aria-label="Main navigation">
          <Link className={`nav-item ${activePath === '/' ? 'active' : ''}`} href="/" data-testid="link-overview">
            <Grid2X2 size={15} aria-hidden="true" /><span>Overview</span>
          </Link>
          <Link className={`nav-item ${activePath === '/settings' ? 'active' : ''}`} href="/settings" data-testid="link-settings">
            <Settings2 size={15} aria-hidden="true" /><span>Settings</span>
          </Link>
        </nav>
        <div className="side-spacer" />
        <div className="rail-divider" />
        <div className="profile-row">
          <span className="user-avatar" aria-hidden="true">{email.slice(0, 1).toUpperCase()}</span>
          <span className="profile-copy" data-testid="text-signed-in-account">
            {email}<small>Signed in</small>
          </span>
          <button
            className="icon-button"
            type="button"
            onClick={() => void handleSignOut()}
            disabled={signingOut}
            aria-label="Sign out"
            title="Sign out"
            data-testid="button-sign-out"
          >
            <LogOut size={15} aria-hidden="true" />
          </button>
        </div>
        {signOutError && <div className="sign-out-error" role="status">Could not sign out. Try again.</div>}
      </aside>
      <main className="main-area">
        <header className="topbar">
          <div className="crumbs"><span>{PRODUCT_NAME}</span><ArrowRight size={12} aria-hidden="true" /><strong>{activePath === '/' ? 'Overview' : activePath === '/settings' ? 'Settings' : 'Workspace'}</strong></div>
          <div className="top-actions"><span className="top-account" title={email}>{email}</span></div>
        </header>
        {children}
      </main>
    </div>
  );
}

function HomePage() {
  const pack = usePackApiPackGet({ query: { queryKey: getPackApiPackGetQueryKey() } });
  const health = useHealthApiHealthGet({ query: { queryKey: getHealthApiHealthGetQueryKey() } });
  const harnesses = pack.data?.harnesses ?? [];

  if (pack.isLoading) {
    return <section className="content"><div className="core-frame"><div className="core-loading"><div className="skeleton-line" /></div></div></section>;
  }
  if (pack.isError) {
    return <section className="content"><ErrorState message="The workspace pack could not be reached." onRetry={() => { void pack.refetch(); }} /></section>;
  }

  return (
    <section className="content">
      <div className="home-heading">
        <div className="home-heading-copy">
          <div className="eyebrow">{PRODUCT_NAME} / Stage 1</div>
          <h1 className="page-heading">Core</h1>
          <p className="page-description">An advise-only workspace. Specialist workspaces will explain findings with source records.</p>
        </div>
        <div className="home-note" data-testid="status-health">
          {health.isLoading ? (
            <span className="health-state"><span className="status-dot status-dot-empty" aria-hidden="true" />No data</span>
          ) : health.data?.status === 'ok' ? (
            <span className="health-state"><span className="status-dot" aria-hidden="true" />On time</span>
          ) : health.data ? (
            <span className="health-state"><span className="status-dot status-dot-problem" aria-hidden="true" />Problem</span>
          ) : (
            <span className="health-state"><span className="status-dot status-dot-empty" aria-hidden="true" />No data</span>
          )}
        </div>
      </div>
      <div className="core-frame" data-testid="panel-core-placeholder">
        <Suspense fallback={<div className="core-loading" role="status">Loading core.</div>}>
          <StageZeroCore harnesses={harnesses} />
        </Suspense>
      </div>
    </section>
  );
}

function HarnessPage() {
  const [, params] = useRoute('/harness/:key');
  const pack = usePackApiPackGet({ query: { queryKey: getPackApiPackGetQueryKey() } });
  const harness = pack.data?.harnesses.find((item) => item.key === params?.key);
  const [question, setQuestion] = useState('');
  const [deepThink, setDeepThink] = useState(false);
  const [answer, setAnswer] = useState<AskResponse | null>(null);
  const [askError, setAskError] = useState('');
  const [asking, setAsking] = useState(false);
  const [evidence, setEvidence] = useState<EvidenceResponse | null>(null);
  const [evidenceError, setEvidenceError] = useState('');

  async function submitQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAsking(true);
    setAskError('');
    setAnswer(null);
    try {
      const response = await fetch('/api/ask', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          harness_key: params?.key,
          question: question.trim(),
          deep_think: deepThink,
        }),
      });
      if (!response.ok) throw new Error('The question could not be answered.');
      setAnswer((await response.json()) as AskResponse);
    } catch {
      setAskError('The question could not be answered right now.');
    } finally {
      setAsking(false);
    }
  }

  async function openEvidence(citation: EvidenceCitation) {
    setEvidence(null);
    setEvidenceError('');
    try {
      const response = await fetch(
        `/api/evidence/${encodeURIComponent(citation.entity)}/${encodeURIComponent(citation.record_id)}`,
        { credentials: 'same-origin' },
      );
      if (!response.ok) throw new Error('Evidence could not be loaded.');
      setEvidence((await response.json()) as EvidenceResponse);
    } catch {
      setEvidenceError('Evidence could not be loaded.');
    }
  }

  if (pack.isLoading) {
    return <section className="content"><div className="glass-panel page-state"><div className="skeleton-line" /></div></section>;
  }
  if (pack.isError) {
    return <section className="content"><ErrorState message="Workspace details could not be reached." onRetry={() => { void pack.refetch(); }} /></section>;
  }
  return (
    <section className="content">
      <div className="eyebrow">{PRODUCT_NAME} / Workspace</div>
      <h1 className="page-heading" data-testid="text-harness-label">{harness?.label ?? 'Workspace'}</h1>
      {harness?.available ? (
        <div className="harness-layout">
          <section className="glass-panel panel-pad" aria-labelledby="ask-heading">
            <h2 className="panel-heading" id="ask-heading">Ask a question</h2>
            <p className="panel-subtitle">Answers cite the records used.</p>
            <form className="ask-form" onSubmit={(event) => void submitQuestion(event)}>
              <label className="sr-only" htmlFor="harness-question">Question</label>
              <textarea
                id="harness-question"
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                rows={3}
                maxLength={4000}
                placeholder="Ask a question about the available records"
                required
                data-testid="input-harness-question"
              />
              <div className="ask-controls">
                <label className="toggle-label">
                  <input
                    type="checkbox"
                    checked={deepThink}
                    onChange={(event) => setDeepThink(event.target.checked)}
                    data-testid="toggle-deep-think"
                  />
                  <span>Deep think</span>
                </label>
                <button className="button-secondary" type="submit" disabled={asking || !question.trim()} data-testid="button-ask">
                  {asking ? 'Thinking…' : 'Ask'}
                </button>
              </div>
            </form>
            {askError && <p className="request-error" role="alert">{askError}</p>}
          </section>

          {answer && (
            <section className="glass-panel panel-pad answer-panel" aria-live="polite" data-testid="panel-answer">
              <h2 className="panel-heading">Answer</h2>
              {answer.gateway_mode === 'mock' && (
                <p className="panel-subtitle" data-testid="status-mock-model">
                  Gateway is running on the mock model; this answer uses the scripted sample.
                </p>
              )}
              <div className="answer-statements">
                {answer.statements.map((statement, index) => (
                  <div className="answer-statement" key={`${index}-${statement.text}`}>
                    <p>{statement.text}</p>
                    {statement.unsupported && (
                      <span className="unsupported-state">
                        <span className="status-dot status-dot-empty" aria-hidden="true" />
                        Unsupported
                      </span>
                    )}
                    {statement.citations.map((citation, citationIndex) => (
                      <button
                        className="citation-marker"
                        type="button"
                        key={citation.record_id}
                        onClick={() => void openEvidence(citation)}
                        aria-label={`Open source record ${citation.record_id}`}
                        data-testid="button-citation"
                      >
                        [{citationIndex + 1}]
                      </button>
                    ))}
                  </div>
                ))}
              </div>
              <div className="answer-routing">
                <div><span className="answer-label">Model</span><span className="mono">{answer.model || '—'}</span></div>
                <div><span className="answer-label">Why</span><span>{answer.routing_reason || '—'}</span></div>
              </div>
            </section>
          )}
        </div>
      ) : (
        <div className="glass-panel page-state" data-testid="panel-harness-empty">
          <div className="empty-inline"><span className="status-dot status-dot-empty" aria-hidden="true" /><span>No data</span></div>
        </div>
      )}

      {(evidence || evidenceError) && (
        <div className="drawer-backdrop" role="presentation" onClick={() => { setEvidence(null); setEvidenceError(''); }}>
          <aside
            className="evidence-drawer glass-panel"
            role="dialog"
            aria-modal="true"
            aria-labelledby="evidence-heading"
            onClick={(event) => event.stopPropagation()}
            data-testid="drawer-evidence"
          >
            <div className="drawer-heading">
              <div>
                <div className="eyebrow">Source record</div>
                <h2 className="panel-heading" id="evidence-heading">{evidence?.entity ?? 'Evidence'}</h2>
              </div>
              <button className="button-secondary" type="button" onClick={() => { setEvidence(null); setEvidenceError(''); }}>Close</button>
            </div>
            {evidenceError ? <p role="alert">{evidenceError}</p> : evidence ? (
              <>
                <h3 className="evidence-section-title">Record fields</h3>
                <dl className="evidence-fields">
                  {Object.entries(evidence.record).map(([name, value]) => (
                    <div key={name}><dt>{name}</dt><dd>{displayValue(value)}</dd></div>
                  ))}
                </dl>
                <h3 className="evidence-section-title">Raw source row</h3>
                <pre className="raw-source">{displayValue(evidence.raw_record.payload)}</pre>
              </>
            ) : <div className="empty-inline"><span className="status-dot status-dot-empty" />Loading evidence</div>}
          </aside>
        </div>
      )}
    </section>
  );
}

function SettingsPage() {
  const models = useModelsApiModelsGet({ query: { queryKey: getModelsApiModelsGetQueryKey() } });
  const pack = usePackApiPackGet({ query: { queryKey: getPackApiPackGetQueryKey() } });
  const loading = models.isLoading || pack.isLoading;

  if (loading) {
    return <section className="content"><div className="page-grid settings-grid"><div className="glass-panel panel-pad"><div className="skeleton-line" /></div><div className="glass-panel panel-pad"><div className="skeleton-line" /></div></div></section>;
  }
  if (models.isError || pack.isError) {
    return (
      <section className="content">
        <div className="eyebrow">{PRODUCT_NAME}</div><h1 className="page-heading">Settings</h1>
        <ErrorState message="Model or pack information could not be reached." onRetry={() => { void models.refetch(); void pack.refetch(); }} />
      </section>
    );
  }
  const modelEntries = Object.entries(models.data?.tiers ?? {});
  const spend = models.data?.daily_spend_usd ?? {};
  const packInfo = pack.data;

  return (
    <section className="content">
      <div className="eyebrow">{PRODUCT_NAME}</div>
      <h1 className="page-heading">Settings</h1>
      <p className="page-description">Model tiers and the active pack.</p>
      <div className="page-grid settings-grid">
        <section className="glass-panel panel-pad" aria-labelledby="models-heading">
          <h2 className="panel-heading" id="models-heading">API model tiers</h2>
          <p className="panel-subtitle">Configuration returned by the API.</p>
          {modelEntries.length ? (
            <div className="model-list">
              {modelEntries.map(([tier, details]) => (
                <div className="model-row" key={tier} data-testid={`row-model-tier-${tier}`}>
                  <div className="model-key">{tier}</div>
                  <div className="model-details">
                    <span>Model · {details.model}</span>
                    <span className="mono">Daily spend · ${spend[details.model] ?? '—'}</span>
                    {details.escalation_model && (
                      <>
                        <span>Escalation · {details.escalation_model}</span>
                        <span className="mono">Daily spend · ${spend[details.escalation_model] ?? '—'}</span>
                      </>
                    )}
                  </div>
                </div>
              ))}
              <div className="model-row">
                <div className="model-key">Daily escalation budget</div>
                <div className="model-details"><span className="mono">${models.data?.daily_escalation_budget_usd}</span></div>
              </div>
            </div>
          ) : <div className="empty-inline"><span className="status-dot status-dot-empty" aria-hidden="true" /><span>No data</span></div>}
        </section>
        <section className="glass-panel panel-pad" aria-labelledby="pack-heading">
          <h2 className="panel-heading" id="pack-heading">Pack</h2>
          <p className="panel-subtitle" data-testid="text-pack-name">{packInfo?.name ?? 'No data'}</p>
          {packInfo?.harnesses.length ? (
            <div className="pack-list">
              {packInfo.harnesses.map((harness) => (
                <div className="pack-row" key={harness.key} data-testid={`row-pack-harness-${harness.key}`}>
                  <span className="model-key">{harness.label}</span>
                  <span className="model-details mono">{harness.key}</span>
                </div>
              ))}
            </div>
          ) : <div className="empty-inline"><span className="status-dot status-dot-empty" aria-hidden="true" /><span>No data</span></div>}
        </section>
      </div>
    </section>
  );
}

function ProtectedRoutes({
  markUrl,
  landscapeAvailable,
}: {
  markUrl: string | null;
  landscapeAvailable: boolean;
}) {
  const session = useSessionInfoApiAuthSessionGet({
    query: {
      queryKey: getSessionInfoApiAuthSessionGetQueryKey(),
      retry: false,
      staleTime: 30_000,
    },
    request: { credentials: 'same-origin' },
  });
  const [location] = useLocation();

  if (location === '/sign-in') {
    return <SignInPage markUrl={markUrl} landscapeAvailable={landscapeAvailable} />;
  }
  if (session.isLoading) return <LoadingScreen />;
  if (session.isError || !session.data) return <Redirect to="/sign-in" />;

  const activePath = location.startsWith('/harness/') ? '/harness' : location;
  return (
    <WorkspaceShell
      markUrl={markUrl}
      landscapeAvailable={landscapeAvailable}
      activePath={activePath}
      email={session.data.email}
    >
      <Switch>
        <Route path="/" component={HomePage} />
        <Route path="/harness/:key" component={HarnessPage} />
        <Route path="/settings" component={SettingsPage} />
        <Route component={() => (
          <main className="page-graphite not-found-page">
            <section className="not-found-card">
              <h1>Page not found</h1>
              <p>This route is not available.</p>
              <Link className="nav-item" href="/" data-testid="link-return-home">Return to overview</Link>
            </section>
          </main>
        )} />
      </Switch>
    </WorkspaceShell>
  );
}

function RoutedErrorBoundary({ children }: { children: ReactNode }) {
  const [location] = useLocation();
  return <ErrorBoundary resetKey={location}>{children}</ErrorBoundary>;
}

function App() {
  const { markUrl, landscapeUrl } = useBrandAssets();
  const appStyle = {
    '--owner-landscape-photo': landscapeUrl ? `url("${landscapeUrl}")` : 'none',
  } as CSSProperties;

  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <div className="app-frame" style={appStyle}>
          <WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, '')}>
            <RoutedErrorBoundary>
              <ProtectedRoutes markUrl={markUrl} landscapeAvailable={Boolean(landscapeUrl)} />
            </RoutedErrorBoundary>
          </WouterRouter>
          <Toaster />
          <IntroLoader markUrl={markUrl} />
        </div>
      </TooltipProvider>
    </QueryClientProvider>
  );
}

export default App;
