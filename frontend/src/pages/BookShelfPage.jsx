import { useState, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import Header from '@/components/Header'
import DisplayPanel from '@/components/DisplayPanel'

// Every view but chat lives at /<view>; chat is / and the fallback for any other path
const VIEWS = ['review', 'bookshelf', 'airglider', 'planjane']

function BookShelfPage() {
  const [activeView, setActiveView] = useState('chat')
  const navigate = useNavigate()
  const location = useLocation()

  // Sync URL with activeView state
  useEffect(() => {
    const view = location.pathname.slice(1)
    setActiveView(VIEWS.includes(view) ? view : 'chat')
  }, [location.pathname])

  // Custom setActiveView that also updates URL
  const handleViewChange = (view) => {
    setActiveView(view)
    navigate(view === 'chat' ? '/' : `/${view}`)
  }

  return (
    <div className="w-screen h-screen bg-[var(--bg-secondary)]" style={{ height: '100dvh' }}>
      <div className="mobile-safe-area w-full h-full relative max-w-4xl mx-auto bg-[var(--bg-secondary)]" style={{ height: '100dvh' }}>
        <div className="grid grid-rows-[auto_1fr] w-full h-full">
          <Header activeView={activeView} setActiveView={handleViewChange} />
          <DisplayPanel activeView={activeView} setActiveView={handleViewChange} />
        </div>
      </div>
    </div>
  )
}

export default BookShelfPage
