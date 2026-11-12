import {
  type CSSProperties,
  type FormEvent,
  type ReactNode,
  useEffect,
  useState,
} from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ErrorBoundary } from '@/components/error-boundary';
import { Toaster } from '@/components/ui/toaster';
import { TooltipProvider } from '@/components/ui/tooltip';
import SignInPage from '@/components/sign-in-page';
import {
  BrandLockup,
  IntroLoader,
  useBrandAssets,
} from '@/lib/brand-assets';
import NotFound from '@/pages/not-found';
import {
  ArrowDown, ArrowRight, ArrowUpRight, Bell, BookOpen, Check,
  ChevronDown, CircleHelp, Command, FilePlus2, FolderKanban, Grid2X2,
  Layers3, LifeBuoy, Plus, Search, Settings2, Sparkles, X,
} from 'lucide-react';
import {
  Route,
  Switch,
  useLocation,
  Router as WouterRouter,
} from 'wouter';

const queryClient = new QueryClient();

function Home({
  markUrl,
  landscapeAvailable,
}: {
  markUrl: string | null;
  landscapeAvailable: boolean;
}) {
  const [dialog, setDialog] = useState<'create' | 'search' | 'settings' | 'help' | null>(null);
  const [viewTitle, setViewTitle] = useState('');
  const [viewDescription, setViewDescription] = useState('');
  const [createdView, setCreatedView] = useState<{ title: string; description: string } | null>(null);
  const [workspaceName, setWorkspaceName] = useState('Omni');
  const [search, setSearch] = useState('');
  const [toast, setToast] = useState('');

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setDialog('search');
      }
      if (event.key === 'Escape') setDialog(null);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(''), 2600);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const openCreate = () => {
    setViewTitle('');
    setViewDescription('');
    setDialog('create');
  };
  const saveView = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!viewTitle.trim()) return;
    setCreatedView({ title: viewTitle.trim(), description: viewDescription.trim() || 'Your workspace, your starting point.' });
    setDialog(null);
    setToast('Your first view is ready to shape.');
  };
  const notifyComingSoon = (feature: string) => setToast(`${feature} is ready when you are.`);
  const searchItems = ['Create a view', 'Workspace preferences', 'Getting started guide'].filter((item) =>
    item.toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <div className={`workspace ${landscapeAvailable ? 'has-landscape' : ''}`}>
      <aside className="side-rail">
        <BrandLockup markUrl={markUrl} className="brand" />
        <button className="workspace-switcher" type="button" onClick={() => setDialog('settings')} data-testid="button-workspace-menu">
          <span className="workspace-avatar">DDG</span>
          <span className="workspace-meta"><strong>{workspaceName}</strong><span>Workspace</span></span>
          <ChevronDown size={14} />
        </button>
        <div className="section-label">Workspace</div>
        <nav aria-label="Workspace navigation">
          <button className="nav-item active" type="button" onClick={() => setCreatedView(null)} data-testid="nav-dashboard">
            <Grid2X2 size={15} /> <span>Overview</span>
          </button>
          <button className="nav-item" type="button" onClick={openCreate} data-testid="nav-views">
            <Layers3 size={15} /> <span>Views</span>
          </button>
          <button className="nav-item" type="button" onClick={() => notifyComingSoon('Your projects')} data-testid="nav-projects">
            <FolderKanban size={15} /> <span>Projects</span>
          </button>
        </nav>
        <div className="section-label">Your space</div>
        <button className="nav-item" type="button" onClick={openCreate} data-testid="button-add-view">
          <Plus size={15} /> <span>Add a view</span>
        </button>
        <div className="side-spacer" />
        <button className="nav-item" type="button" onClick={() => setDialog('help')} data-testid="nav-help">
          <LifeBuoy size={15} /> <span>Help &amp; notes</span>
        </button>
        <div className="rail-divider" />
        <div className="profile-row">
          <span className="profile-avatar">Y</span>
          <span className="profile-copy">Account<small><span className="status-dot status-dot-on-time" aria-hidden="true" />Signed in</small></span>
          <button className="icon-button" aria-label="Open workspace settings" type="button" onClick={() => setDialog('settings')} data-testid="button-settings">
            <Settings2 size={15} />
          </button>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div className="crumbs"><span>{workspaceName}</span><ArrowRight size={12} /><strong>Overview</strong></div>
          <div className="top-actions">
            <button className="search-trigger" type="button" onClick={() => setDialog('search')} data-testid="button-search">
              <Search size={14} /><span>Search workspace</span><kbd>⌘ K</kbd>
            </button>
            <button className="icon-button" aria-label="Open help" type="button" onClick={() => setDialog('help')} data-testid="button-help">
              <CircleHelp size={16} />
            </button>
          </div>
        </header>

        <section className="content">
          <div className="welcome-row">
            <div>
              <div className="eyebrow">Omni</div>
              <h1 className="welcome-title">Overview</h1>
              <p className="welcome-subtitle">No data yet. Create a view to get started.</p>
            </div>
            <button className="button-primary" type="button" onClick={openCreate} data-testid="button-create-view">
              <Plus size={15} /> Create a view
            </button>
          </div>

          {createdView ? (
            <div className="created-view" data-testid="card-created-view">
              <span className="created-mark"><Layers3 size={18} /></span>
              <span className="created-copy"><strong>{createdView.title}</strong><span>{createdView.description}</span></span>
              <span className="view-status"><span className="status-dot status-dot-empty" aria-hidden="true" />No data</span>
              <button className="icon-button" aria-label="Remove view" type="button" onClick={() => { setCreatedView(null); setToast('View removed from your workspace.'); }} data-testid="button-remove-view"><X size={15} /></button>
            </div>
          ) : (
            <div className="starter-panel" data-testid="panel-empty-state">
              <div className="starter-copy">
                <div className="eyebrow">Nothing here. Yet.</div>
                <h2>No data yet.</h2>
                <p>Create a view to organize this workspace.</p>
                <div className="starter-buttons">
                  <button className="button-primary" type="button" onClick={openCreate} data-testid="button-start-building">
                    <FilePlus2 size={14} /> Start building <ArrowUpRight size={13} />
                  </button>
                  <button className="button-secondary" type="button" onClick={() => setDialog('help')} data-testid="button-see-how">
                    <BookOpen size={14} /> See how it works
                  </button>
                </div>
              </div>
              <div className="starter-visual" aria-label="3D core placeholder">
                <div className="core-placeholder" data-testid="core-placeholder">
                  <span className="status-dot status-dot-empty" aria-hidden="true" />
                  <span>No data</span>
                </div>
              </div>
            </div>
          )}

          <div className="empty-footer">
            <div><div className="section-heading">Getting started</div><div className="section-caption">Choose a starting point.</div></div>
            <button className="button-secondary" type="button" onClick={() => setDialog('help')} data-testid="button-open-guide">
              Open the field guide <ArrowRight size={13} />
            </button>
          </div>
          <div className="tips-row">
            <button className="tip-card" type="button" onClick={openCreate} data-testid="tip-build-view">
              <span className="tip-icon"><Grid2X2 size={15} /></span>
              <span className="tip-copy"><strong>Make a view</strong><span>Give your project a place to take shape.</span></span>
            </button>
            <button className="tip-card" type="button" onClick={() => setDialog('help')} data-testid="tip-find-rhythm">
              <span className="tip-icon"><Sparkles size={15} /></span>
              <span className="tip-copy"><strong>Find your rhythm</strong><span>A few ideas for getting started, not rules.</span></span>
            </button>
            <button className="tip-card" type="button" onClick={() => setDialog('settings')} data-testid="tip-set-up">
              <span className="tip-icon"><Settings2 size={15} /></span>
              <span className="tip-copy"><strong>Set up your space</strong><span>Name it, tune it, make it feel like yours.</span></span>
            </button>
          </div>
          <div className="bottom-note"><span>Made for the work ahead</span><ArrowDown size={12} /></div>
        </section>
      </main>

      {dialog && (
        <div className="overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setDialog(null); }}>
          {dialog === 'create' ? (
            <form className="dialog" onSubmit={saveView} aria-labelledby="create-title">
              <div className="dialog-head"><div><div className="eyebrow">New starting point</div><h3 id="create-title">Create a view</h3></div><button className="icon-button" type="button" aria-label="Close dialog" onClick={() => setDialog(null)} data-testid="button-close-dialog"><X size={16} /></button></div>
              <p className="dialog-intro">Give this space a name. You can add the details and tools that make it useful later.</p>
              <label className="field-label" htmlFor="view-title">View name</label>
              <input className="text-field" id="view-title" autoFocus value={viewTitle} onChange={(event) => setViewTitle(event.target.value)} placeholder="A name that makes sense to you" maxLength={50} required data-testid="input-view-title" />
              <label className="field-label" htmlFor="view-description">A note to yourself <span className="field-optional">(optional)</span></label>
              <input className="text-field" id="view-description" value={viewDescription} onChange={(event) => setViewDescription(event.target.value)} placeholder="What will this help you keep track of?" maxLength={100} data-testid="input-view-description" />
              <div className="dialog-actions"><button className="button-secondary" type="button" onClick={() => setDialog(null)} data-testid="button-cancel-create">Not now</button><button className="button-primary" type="submit" data-testid="button-save-view"><Plus size={14} /> Create view</button></div>
            </form>
          ) : dialog === 'search' ? (
            <div className="dialog" role="dialog" aria-labelledby="search-title">
              <div className="dialog-head"><div><div className="eyebrow">Find your way</div><h3 id="search-title">Search</h3></div><button className="icon-button" type="button" aria-label="Close search" onClick={() => setDialog(null)} data-testid="button-close-search"><X size={16} /></button></div>
              <div className="search-box"><Search size={15} /><input autoFocus value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search this workspace…" aria-label="Search this workspace" data-testid="input-search" /><Command size={13} /></div>
              <div className="search-results">
                {searchItems.length ? searchItems.map((item) => (
                  <button className="search-result" type="button" key={item} onClick={() => { setDialog(item.includes('Create') ? 'create' : item.includes('preferences') ? 'settings' : 'help'); setSearch(''); }} data-testid={`search-result-${item.toLowerCase().replaceAll(' ', '-')}`}>
                    {item.includes('Create') ? <Plus size={14} /> : item.includes('preferences') ? <Settings2 size={14} /> : <BookOpen size={14} />} {item}
                  </button>
                )) : <div className="search-result">No matches in this workspace.</div>}
              </div>
            </div>
          ) : (
            <div className="dialog" role="dialog" aria-labelledby="info-title">
              <div className="dialog-head"><div><div className="eyebrow">{dialog === 'settings' ? 'Make it yours' : 'A note before you begin'}</div><h3 id="info-title">{dialog === 'settings' ? 'Workspace preferences' : 'A small field guide'}</h3></div><button className="icon-button" type="button" aria-label="Close dialog" onClick={() => setDialog(null)} data-testid="button-close-info"><X size={16} /></button></div>
              {dialog === 'settings' ? (
                <>
              <p className="dialog-intro">Set a name for this workspace.</p>
                  <label className="field-label" htmlFor="workspace-name">Workspace name</label><input className="text-field" id="workspace-name" value={workspaceName} onChange={(event) => setWorkspaceName(event.target.value)} data-testid="input-workspace-name" />
                  <div className="dialog-actions"><button className="button-primary" type="button" onClick={() => { setDialog(null); setToast('Preferences saved for this session.'); }} data-testid="button-save-settings"><Check size={14} /> Save preferences</button></div>
                </>
              ) : (
                <>
              <p className="dialog-intro">Omni is ready for your data. No data has been added yet.</p>
                  <div className="field-guide-list">
                    <div className="field-guide-item"><span className="tip-icon"><Plus size={14} /></span><span><strong>Start small.</strong> One useful place is better than a perfect system.</span></div>
                    <div className="field-guide-item"><span className="tip-icon"><Layers3 size={14} /></span><span><strong>Make it yours.</strong> Views are a starting point, not a template.</span></div>
                  </div>
                  <div className="dialog-actions"><button className="button-primary" type="button" onClick={() => { setDialog('create'); }} data-testid="button-guide-create"><Plus size={14} /> Create your first view</button></div>
                </>
              )}
            </div>
          )}
        </div>
      )}
      {toast && <div className="toast-message" role="status" data-testid="status-toast"><Bell size={13} style={{ verticalAlign: 'middle', marginRight: 7 }} />{toast}</div>}
    </div>
  );
}

function Router({
  markUrl,
  landscapeAvailable,
}: {
  markUrl: string | null;
  landscapeAvailable: boolean;
}) {
  return (
    // Keep a shared shell (sidebar, navbar) outside the boundary so it
    // survives a page crash.
    <RoutedErrorBoundary>
      <Switch>
        <Route
          path="/"
          component={() => (
            <Home
              markUrl={markUrl}
              landscapeAvailable={landscapeAvailable}
            />
          )}
        />
        <Route
          component={() => (
            <NotFound
              markUrl={markUrl}
              landscapeAvailable={landscapeAvailable}
            />
          )}
        />
      </Switch>
    </RoutedErrorBoundary>
  );
}

function RoutedErrorBoundary({ children }: { children: ReactNode }) {
  const [location] = useLocation();
  return <ErrorBoundary resetKey={location}>{children}</ErrorBoundary>;
}

function App() {
  const { markUrl, landscapeUrl } = useBrandAssets();
  const [authState, setAuthState] = useState<
    'checking' | 'signed-out' | 'signed-in'
  >('checking');

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    const timeout = window.setTimeout(() => controller.abort(), 2500);

    void fetch('/api/auth/session', {
      credentials: 'same-origin',
      signal: controller.signal,
    })
      .then((response) => {
        if (active) setAuthState(response.ok ? 'signed-in' : 'signed-out');
      })
      .catch(() => {
        if (active) setAuthState('signed-out');
      })
      .finally(() => window.clearTimeout(timeout));

    return () => {
      active = false;
      controller.abort();
      window.clearTimeout(timeout);
    };
  }, []);

  const appStyle = {
    '--owner-landscape-photo': landscapeUrl
      ? `url("${landscapeUrl}")`
      : 'none',
  } as CSSProperties;

  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <div className="app-frame" style={appStyle}>
          {authState === 'signed-in' ? (
            <WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, '')}>
              <Router
                markUrl={markUrl}
                landscapeAvailable={Boolean(landscapeUrl)}
              />
            </WouterRouter>
          ) : (
            <SignInPage
              markUrl={markUrl}
              landscapeAvailable={Boolean(landscapeUrl)}
              checkingSession={authState === 'checking'}
              onSignedIn={() => setAuthState('signed-in')}
            />
          )}
          <Toaster />
          <IntroLoader markUrl={markUrl} />
        </div>
      </TooltipProvider>
    </QueryClientProvider>
  );
}

export default App;
