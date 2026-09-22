import '@/index.css'
import { useEffect } from 'react'
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import BookShelfPage from '@/pages/BookShelfPage'
import api from '@/api'

function App() {
  // TODO: add a server not available page or message
  useEffect(() => {
    const checkBackendHealth = async () => {
      const res = await api.backEndPing()
      console.log(res)
    }
    checkBackendHealth()
  }, [])


  return (
    <Router>
      <Routes>
        <Route path="/" element={<BookShelfPage />} />
        <Route path="/blog" element={<BookShelfPage />} />
        <Route path="/review" element={<BookShelfPage />} />
        {/* Catch all other routes and redirect to home */}
        <Route path="*" element={<BookShelfPage />} />
      </Routes>
    </Router>
  )
}

export default App
