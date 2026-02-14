// AIInterviewer.tsx
import { useState } from 'react'
import './AIInterviewer.css'

export default function AIInterviewer() {
  const [voiceMode, setVoiceMode] = useState(false)
  const [limitType, setLimitType] = useState<'word' | 'time' | 'none'>('word')
  const [limitValue, setLimitValue] = useState(200)
  const [sessionSummary, setSessionSummary] = useState('')
  const [feedback, setFeedback] = useState('')
  const [fileName, setFileName] = useState('')

  return (
    <section className="chat">
      <div className="chat-inner">
        <div className="chat-header">
          <h2>AI Interviewer</h2>
          <div className="session-buttons">
            <button>Resume Session</button>
            <button onClick={() => setSessionSummary('')}>New Session</button>
          </div>
        </div>

        <div className="chat-window">
          <p className="placeholder">Conversation with AI will appear here...</p>
        </div>

        <div className="controls">
          <div className="toggle-card">
            <span>Voice Mode</span>
            <label className="switch">
              <input
                type="checkbox"
                checked={voiceMode}
                onChange={() => setVoiceMode(!voiceMode)}
              />
              <span className="slider" />
            </label>
          </div>

          {limitType !== 'none' && (
            <div className="limit-card">
              <label>
                {limitType === 'word' ? 'Word Limit' : 'Time Limit (sec)'}
              </label>
              <input
                type="number"
                value={limitValue}
                onChange={(e) => setLimitValue(Number(e.target.value))}
              />
            </div>
          )}

          <div className="file-card">
            <label>Upload File</label>
            <input
              type="file"
              onChange={(e) => setFileName(e.target.files?.[0]?.name || '')}
            />
            <span className="file-name">{fileName}</span>
          </div>
        </div>

        <div className="summary">
          <h3>Session Summary</h3>
          <textarea
            placeholder="AI-generated summary will appear here..."
            value={sessionSummary}
            onChange={(e) => setSessionSummary(e.target.value)}
          />

          <h3>User Feedback for Future Sessions</h3>
          <textarea
            placeholder="Notes for the agent to remember next time..."
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
          />
        </div>
      </div>
    </section>
  )
}