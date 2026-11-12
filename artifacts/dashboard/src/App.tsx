import { type FormEvent, type ReactNode, useEffect, useState } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ErrorBoundary } from '@/components/error-boundary';
import { Toaster } from '@/components/ui/toaster';
import { TooltipProvider } from '@/components/ui/tooltip';
import NotFound from '@/pages/not-found';
import {
  ArrowDown, ArrowRight, ArrowUpRight, Bell, Blocks, BookOpen, Check,
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

function Home() {
  const [dialog, setDialog] = useState<'create' | 'search' | 'settings' | 'help' | null>(null);
  const [viewTitle, setViewTitle] = useState('');
  const [viewDescription, setViewDescription] = useState('');
  const [createdView, setCreatedView] = useState<{ title: string; description: string } | null>(null);
  const [workspaceName, setWorkspaceName] = useState('My workspace');
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
    <div className="workspace">
      <aside className="side-rail">
        <div className="brand" aria-label="Morrow workspace home">
          <span className="brand-mark"><Blocks size={16} strokeWidth={2.2} /></span>
          <span className="brand-name">morrow</span>
        </div>
        <button className="workspace-switcher" type="button" onClick={() => setDialog('settings')} data-testid="button-workspace-menu">
          <span className="workspace-avatar">MY</span>
          <span className="workspace-meta"><strong>{workspaceName}</strong><span>Personal space</span></span>
          <ChevronDown size={14} color="#888b84" />
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
          <span className="profile-copy">Your account<small>Personal plan</small></span>
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
              <div className="eyebrow">A workspace in the making</div>
              <h1 className="welcome-title">Good things<br />start <em>somewhere.</em></h1>
              <p className="welcome-subtitle">This is your blank canvas. Bring a project, a question, or just a hunch.<br className="desktop-break" /> We’ll leave the shape of it up to you.</p>
            </div>
            <button className="button-primary" type="button" onClick={openCreate} data-testid="button-create-view">
              <Plus size={15} /> Create a view
            </button>
          </div>

          {createdView ? (
            <div className="created-view" data-testid="card-created-view">
              <span className="created-mark"><Layers3 size={18} /></span>
              <span className="created-copy"><strong>{createdView.title}</strong><span>{createdView.description}</span></span>
              <span className="view-status"><Check size={11} /> yours to shape</span>
              <button className="icon-button" aria-label="Remove view" type="button" onClick={() => { setCreatedView(null); setToast('View removed from your workspace.'); }} data-testid="button-remove-view"><X size={15} /></button>
            </div>
          ) : (
            <div className="starter-panel" data-testid="panel-empty-state">
              <div className="starter-copy">
                <div className="eyebrow">Nothing here. Yet.</div>
                <h2>A little room to make it yours.</h2>
                <p>Start with one view. Add the pieces your work actually needs, and let this space grow alongside the project.</p>
                <div className="starter-buttons">
                  <button className="button-primary" type="button" onClick={openCreate} data-testid="button-start-building">
                    <FilePlus2 size={14} /> Start building <ArrowUpRight size={13} />
                  </button>
                  <button className="button-secondary" type="button" onClick={() => setDialog('help')} data-testid="button-see-how">
                    <BookOpen size={14} /> See how it works
                  </button>
                </div>
              </div>
              <div className="starter-visual" aria-hidden="true">
                <div className="visual-orbit" />
                <span className="visual-center"><Layers3 size={35} strokeWidth={1.15} /></span>
                <span className="orbit-node node-a"><Plus size={17} /></span>
                <span className="orbit-node node-b"><Grid2X2 size={14} /></span>
                <span className="orbit-node node-c"><ArrowUpRight size={14} /></span>
              </div>
            </div>
          )}

          <div className="empty-footer">
            <div><div className="section-heading">A few ways to begin</div><div className="section-caption">Small steps. No setup required.</div></div>
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
              <label className="field-label" htmlFor="view-description">A note to yourself <span style={{ color: '#a09f97', fontWeight: 400 }}>(optional)</span></label>
              <input className="text-field" id="view-description" value={viewDescription} onChange={(event) => setViewDescription(event.target.value)} placeholder="What will this help you keep track of?" maxLength={100} data-testid="input-view-description" />
              <div className="dialog-actions"><button className="button-secondary" type="button" onClick={() => setDialog(null)} data-testid="button-cancel-create">Not now</button><button className="button-primary" type="submit" data-testid="button-save-view"><Plus size={14} /> Create view</button></div>
            </form>
          ) : dialog === 'search' ? (
            <div className="dialog" role="dialog" aria-labelledby="search-title">
              <div className="dialog-head"><div><div className="eyebrow">Find your way</div><h3 id="search-title">Search</h3></div><button className="icon-button" type="button" aria-label="Close search" onClick={() => setDialog(null)} data-testid="button-close-search"><X size={16} /></button></div>
              <div className="search-box"><Search size={15} color="#858780" /><input autoFocus value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search this workspace…" aria-label="Search this workspace" data-testid="input-search" /><Command size={13} color="#a09f97" /></div>
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
                  <p className="dialog-intro">Your workspace is ready for a name and a point of view. For now, it belongs to you alone.</p>
                  <label className="field-label" htmlFor="workspace-name">Workspace name</label><input className="text-field" id="workspace-name" value={workspaceName} onChange={(event) => setWorkspaceName(event.target.value)} data-testid="input-workspace-name" />
                  <div className="dialog-actions"><button className="button-primary" type="button" onClick={() => { setDialog(null); setToast('Preferences saved for this session.'); }} data-testid="button-save-settings"><Check size={14} /> Save preferences</button></div>
                </>
              ) : (
                <>
                  <p className="dialog-intro">Morrow starts blank on purpose. There are no sample metrics to clear and no prescribed way to work. Make a view when you have something worth keeping close.</p>
                  <div style={{ display: 'grid', gap: 12, margin: '19px 0 3px', color: '#62676a', fontSize: 11, lineHeight: 1.6 }}>
                    <div style={{ display: 'flex', gap: 10 }}><span className="tip-icon"><Plus size={14} /></span><span><strong style={{ color: '#363b40' }}>Start small.</strong> One useful place is better than a perfect system.</span></div>
                    <div style={{ display: 'flex', gap: 10 }}><span className="tip-icon"><Layers3 size={14} /></span><span><strong style={{ color: '#363b40' }}>Make it yours.</strong> Views are a starting point, not a template.</span></div>
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

function Router() {
  return (
    // Keep a shared shell (sidebar, navbar) outside the boundary so it
    // survives a page crash.
    <RoutedErrorBoundary>
      <Switch>
        <Route path="/" component={Home} />
        <Route component={NotFound} />
      </Switch>
    </RoutedErrorBoundary>
  );
}

function RoutedErrorBoundary({ children }: { children: ReactNode }) {
  const [location] = useLocation();
  return <ErrorBoundary resetKey={location}>{children}</ErrorBoundary>;
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, '')}>
          <Router />
        </WouterRouter>
        <Toaster />
      </TooltipProvider>
    </QueryClientProvider>
  );
}

export default App;
