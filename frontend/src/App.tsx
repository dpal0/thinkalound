// App.tsx
import { useState } from 'react'
import './App.css'
import AIInterviewer from './AIInterviewer'

const experts = [
    { id: 1, name: 'AI Interviewer' },
    { id: 2, name: 'AI Mode 2' },

]

function App() {
  const [selectedExpert, setSelectedExpert] = useState(experts[0])
  const [voiceMode, setVoiceMode] = useState(false)

  // Limits will come from agent question later
  const [limitType, setLimitType] = useState<'word' | 'time' | 'none'>('word')
  const [limitValue, setLimitValue] = useState(200)

  const [sessionSummary, setSessionSummary] = useState('')
  const [feedback, setFeedback] = useState('')
  const [fileName, setFileName] = useState('')

  return (
    <div className="app">
      <header className="header">
        <h1>ThinkAloud</h1>
        <p>Your multi‑expert AI workspace for deep thinking, planning, and collaboration.</p>
      </header>

      <div className="main">
        <aside className="sidebar">
          <h2>AI Experts</h2>
          {experts.map((expert) => (
            <button
              key={expert.id}
              className={`expert-btn ${selectedExpert.id === expert.id ? 'active' : ''}`}
              onClick={() => setSelectedExpert(expert)}
            >
              {expert.name}
            </button>
          ))}
        </aside>

        <section className="chat">
            {selectedExpert.name === 'AI Interviewer' && <AIInterviewer />}
        </section>
      </div>
    </div>
  )
}

export default App