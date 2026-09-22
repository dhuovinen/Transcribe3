import { useState } from 'react'
import HelpModal from './components/HelpModal'
import ReviewView from './components/ReviewView'
import SessionList from './components/SessionList'
import SettingsView from './components/SettingsView'
import ArchiveView from './components/ArchiveView'
import AdminView from './components/AdminView'
import UploadForm from './components/UploadForm'

type View = 'list' | 'upload' | 'review' | 'settings' | 'archive' | 'admin'

export default function App() {
  const [view, setView] = useState<View>('list')
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null)
  const [showHelp, setShowHelp] = useState(false)

  function goToList() {
    setView('list')
    setSelectedSessionId(null)
  }

  function goToReview(sessionId: string) {
    setSelectedSessionId(sessionId)
    setView('review')
  }

  function goToUpload() {
    setView('upload')
  }

  const isRoot = view === 'list'

  return (
    <div>
      <header className="app-header">
        <div className="header-left">
          {!isRoot && (
            <button className="nav-link" onClick={goToList}>
              &larr; All Sessions
            </button>
          )}
          <h1
            style={{ cursor: isRoot ? 'default' : 'pointer' }}
            onClick={isRoot ? undefined : goToList}
          >
            Transcribe3
          </h1>
        </div>

        <div className="header-right">
          {isRoot && (
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

      {view === 'list' && (
        <SessionList onSelectSession={goToReview} onNewSession={goToUpload} />
      )}

      {view === 'upload' && (
        <UploadForm
          onSuccess={(sessionId) => goToReview(sessionId)}
          onCancel={goToList}
        />
      )}

      {view === 'review' && selectedSessionId && (
        <ReviewView sessionId={selectedSessionId} onBack={goToList} />
      )}

      {view === 'settings' && (
        <SettingsView onBack={goToList} />
      )}

      {view === 'archive' && (
        <ArchiveView onBack={goToList} />
      )}

      {view === 'admin' && (
        <AdminView onBack={goToList} />
      )}

      {showHelp && <HelpModal onClose={() => setShowHelp(false)} />}
    </div>
  )
}
