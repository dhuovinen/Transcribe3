import { useState } from 'react'
import HelpModal from './components/HelpModal'
import HomeView from './components/HomeView'
import ReviewView from './components/ReviewView'
import SessionList from './components/SessionList'
import SettingsView from './components/SettingsView'
import ArchiveView from './components/ArchiveView'
import AdminView from './components/AdminView'
import UploadForm from './components/UploadForm'

type View = 'home' | 'list' | 'upload' | 'review' | 'settings' | 'archive' | 'admin'
type ReturnView = 'home' | 'list'

export default function App() {
  const [view, setView] = useState<View>('home')
  // Where "back" from a drill-down screen (review, upload) should land —
  // whichever of home/list the user was on right before drilling in.
  const [returnView, setReturnView] = useState<ReturnView>('home')
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null)
  const [showHelp, setShowHelp] = useState(false)

  function rememberReturn() {
    if (view === 'home' || view === 'list') setReturnView(view)
  }

  function goHome() {
    setView('home')
    setSelectedSessionId(null)
  }

  function goToList() {
    setView('list')
    setSelectedSessionId(null)
  }

  function goBack() {
    setView(returnView)
    setSelectedSessionId(null)
  }

  function goToReview(sessionId: string) {
    rememberReturn()
    setSelectedSessionId(sessionId)
    setView('review')
  }

  function goToUpload() {
    rememberReturn()
    setView('upload')
  }

  const isHome = view === 'home'
  const showNewSessionInHeader = view === 'home' || view === 'list'

  // The header's back link is the only back control actually rendered across
  // every screen, so it has to be the one that knows where "back" means —
  // from review/upload that's wherever the user drilled in from (home or the
  // full session list), from the utility screens it's always home.
  const headerBack =
    view === 'review' || view === 'upload'
      ? { label: returnView === 'list' ? '← All Sessions' : '← Home', onClick: goBack }
      : { label: '← Home', onClick: goHome }

  return (
    <div>
      <header className="app-header">
        <div className="header-left">
          {!isHome && (
            <button className="nav-link" onClick={headerBack.onClick}>
              {headerBack.label}
            </button>
          )}
          <h1
            style={{ cursor: isHome ? 'default' : 'pointer' }}
            onClick={isHome ? undefined : goHome}
          >
            Transcribe3
          </h1>
        </div>

        <div className="header-right">
          {showNewSessionInHeader && (
            <button className="btn btn-primary" onClick={goToUpload}>
              New Session
            </button>
          )}
          <button className="btn" onClick={() => setView('archive')}>
            Archive
          </button>
          <button className="btn" onClick={() => setView('admin')}>
            Admin
          </button>
          <button
            className="icon-btn"
            title="Settings"
            aria-label="Settings"
            onClick={() => setView('settings')}
          >
            ⚙
          </button>
          <button
            className="icon-btn"
            title="Help"
            aria-label="Help"
            onClick={() => setShowHelp(true)}
          >
            ?
          </button>
        </div>
      </header>

      {view === 'home' && (
        <HomeView
          onNewSession={goToUpload}
          onViewSessions={goToList}
          onSelectSession={goToReview}
        />
      )}

      {view === 'list' && (
        <SessionList onSelectSession={goToReview} onNewSession={goToUpload} />
      )}

      {view === 'upload' && (
        <UploadForm
          onSuccess={(sessionId) => goToReview(sessionId)}
          onCancel={goBack}
        />
      )}

      {view === 'review' && selectedSessionId && (
        <ReviewView sessionId={selectedSessionId} onBack={goBack} />
      )}

      {view === 'settings' && (
        <SettingsView onBack={goHome} />
      )}

      {view === 'archive' && (
        <ArchiveView onBack={goHome} />
      )}

      {view === 'admin' && (
        <AdminView onBack={goHome} />
      )}

      {showHelp && <HelpModal onClose={() => setShowHelp(false)} />}
    </div>
  )
}
