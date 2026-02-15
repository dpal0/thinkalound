// AIInterviewer.tsx
import { useState, useRef, useCallback, useEffect } from 'react'
import './AIInterviewer.css'

export default function AIInterviewer() {
  const [sessionSummary, setSessionSummary] = useState('')
  const [feedback, setFeedback] = useState('')
  const [fileName, setFileName] = useState('')
  const [resumeFile, setResumeFile] = useState<File | null>(null)
  const [jobTitle, setJobTitle] = useState('')
  const [jobDescription, setJobDescription] = useState('')
  const [analyzing, setAnalyzing] = useState(false)
  const [analysisError, setAnalysisError] = useState('')
  const [analysis, setAnalysis] = useState<{
    resumeSummary: string
    firstQuestion: string
  } | null>(null)
  const [messages, setMessages] = useState<{ role: 'assistant' | 'user'; content: string }[]>([])
  const [sessionContext, setSessionContext] = useState<{
    resumeSummary: string
    jobTitle: string
    jobDescription: string
  } | null>(null)
  const [voiceEnabled, setVoiceEnabled] = useState(false)
  const [answer, setAnswer] = useState('')
  const [sending, setSending] = useState(false)
  const [interviewDone, setInterviewDone] = useState(false)
  const [overallScore, setOverallScore] = useState<number | null>(null)
  const [overallFeedback, setOverallFeedback] = useState<string>('')

  const [savedSessions, setSavedSessions] = useState<any[]>([])
const [selectedSessionId, setSelectedSessionId] = useState('')
const [analytics, setAnalytics] = useState<any>(null)
const [, setLoadingAnalytics] = useState(false)

  // ── STT (Speech-to-Text) state ──
  const [isRecording, setIsRecording] = useState(false)
  const [sttPartial, setSttPartial] = useState('')
  const wsRef = useRef<WebSocket | null>(null)
  const mediaStreamRef = useRef<MediaStream | null>(null)
  const processorRef = useRef<ScriptProcessorNode | null>(null)
  const audioCtxRef = useRef<AudioContext | null>(null)

  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      mediaStreamRef.current = stream

      const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
      const ws = new WebSocket(`${protocol}://${window.location.host}/ws/stt`)
      wsRef.current = ws

      ws.onopen = () => {
        // Start capturing audio
        const audioCtx = new AudioContext({ sampleRate: 16000 })
        audioCtxRef.current = audioCtx
        const source = audioCtx.createMediaStreamSource(stream)
        const processor = audioCtx.createScriptProcessor(4096, 1, 1)
        processorRef.current = processor

        processor.onaudioprocess = (e) => {
          if (ws.readyState !== WebSocket.OPEN) return
          const float32 = e.inputBuffer.getChannelData(0)
          // Convert Float32 → Int16 PCM
          const int16 = new Int16Array(float32.length)
          for (let i = 0; i < float32.length; i++) {
            const s = Math.max(-1, Math.min(1, float32[i]))
            int16[i] = s < 0 ? s * 0x8000 : s * 0x7fff
          }
          ws.send(int16.buffer)
        }

        source.connect(processor)
        processor.connect(audioCtx.destination)
      }

      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data)
          if (payload.message_type === 'partial_transcript' && payload.text) {
            setSttPartial(payload.text)
          } else if (
            payload.message_type === 'committed_transcript' &&
            payload.text
          ) {
            // Append committed text to the answer
            setAnswer((prev) => {
              const sep = prev && !prev.endsWith(' ') ? ' ' : ''
              return prev + sep + payload.text
            })
            setSttPartial('')
          } else if (payload.message_type?.includes('error') || payload.message_type === 'server_error') {
            setAnalysisError(payload.detail || payload.error || 'STT error')
          }
        } catch {}
      }

      ws.onerror = () => {
        setAnalysisError('Speech-to-text connection failed')
        stopRecording()
      }

      ws.onclose = () => {
        // Cleanup handled in stopRecording
      }

      setIsRecording(true)
      setSttPartial('')
    } catch (err) {
      setAnalysisError(
        err instanceof Error ? err.message : 'Microphone access denied'
      )
    }
  }, [])

  const stopRecording = useCallback(() => {
    if (processorRef.current) {
      processorRef.current.disconnect()
      processorRef.current = null
    }
    if (audioCtxRef.current) {
      audioCtxRef.current.close().catch(() => {})
      audioCtxRef.current = null
    }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((t) => t.stop())
      mediaStreamRef.current = null
    }
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    setIsRecording(false)
    setSttPartial('')
  }, [])

  async function handleAnalyze() {
    if (!resumeFile || !jobTitle.trim()) {
      setAnalysisError('Please upload a resume and enter a job title.')
      return
    }
    setAnalysisError('')
    setAnalyzing(true)
    setAnalysis(null)
    setMessages([])
    setSessionContext(null)
    setInterviewDone(false)
    setOverallScore(null)
    setOverallFeedback('')
    try {
      const form = new FormData()
      form.append('resume', resumeFile)
      form.append('jobTitle', jobTitle)
      form.append('jobDescription', jobDescription)
      const res = await fetch('/api/analyze', {
        method: 'POST',
        body: form,
      })
      const text = await res.text()
      if (!text) {
        throw new Error('Server returned no data. Is the backend running? (npm run dev in backend folder)')
      }
      let data: { error?: string; details?: string; resumeSummary?: string; firstQuestion?: string }
      try {
        data = JSON.parse(text)
      } catch {
        throw new Error('Server returned invalid response. Is the backend running on port 3001?')
      }
      if (!res.ok) throw new Error(data.error || data.details || 'Request failed')
      if (data.resumeSummary == null || data.firstQuestion == null) throw new Error('Invalid response from server')
      setAnalysis({
        resumeSummary: data.resumeSummary,
        firstQuestion: data.firstQuestion,
      })
      setSessionContext({
        resumeSummary: data.resumeSummary,
        jobTitle,
        jobDescription,
      })
      const first = { role: 'assistant' as const, content: data.firstQuestion }
      setMessages([first])
      // Play the first question if voice is enabled
      if (voiceEnabled) {
        try {
          await playTTS(first.content)
        } catch {
          // ignore TTS errors silently
        }
      }
    } catch (e) {
      setAnalysisError(e instanceof Error ? e.message : 'Analysis failed')
    } finally {
      setAnalyzing(false)
    }
  }

  async function handleSendAnswer() {
    const text = answer.trim()
    if (!text || !sessionContext || sending || interviewDone) return
    const userMessage = { role: 'user' as const, content: text }
    setMessages((prev) => [...prev, userMessage])
    setAnswer('')
    setSending(true)
    setAnalysisError('')
    try {
      const nextMessages = [...messages, userMessage]
      const res = await fetch('/api/interview/next', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            sessionId: selectedSessionId,
          resumeSummary: sessionContext.resumeSummary,
          jobTitle: sessionContext.jobTitle,
          jobDescription: sessionContext.jobDescription,
          messages: nextMessages,
        }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || data.details || 'Request failed')
      if (data.done && data.closingMessage) {
        if (typeof data.overallScore === 'number') setOverallScore(data.overallScore)
        if (typeof data.overallFeedback === 'string' && data.overallFeedback) {
          setOverallFeedback(data.overallFeedback)
          setSessionSummary(data.overallFeedback)
        }
        const closing = { role: 'assistant' as const, content: data.closingMessage }
        setMessages((prev) => [...prev, closing])
        if (voiceEnabled) {
          try { await playTTS(closing.content) } catch {}
        }

        try {
            await fetch('/api/session/save', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                jobTitle: sessionContext.jobTitle,
                feedback: data.overallFeedback,
                messages: nextMessages,
                score: data.overallScore,
                resume_summary: sessionContext.resumeSummary,
              }),
            })
          } catch (err) {
            console.error('Failed to save session', err)
          }

        setInterviewDone(true)
      } else if (data.nextQuestion) {
        const next = { role: 'assistant' as const, content: data.nextQuestion }
        setMessages((prev) => [...prev, next])
        if (voiceEnabled) {
          try { await playTTS(next.content) } catch {}
        }
      }
    } catch (e) {
      setAnalysisError(e instanceof Error ? e.message : 'Failed to get next question')
    } finally {
      setSending(false)
    }
  }

  async function loadSessions() {
    try {
      const res = await fetch('/api/session/list')
      const data = await res.json()
      setSavedSessions(data || [])
    } catch (e) {
      console.error('Failed to load sessions')
    }
  }
  
  async function handleResumeSession() {
    const session = savedSessions.find(s => s._id === selectedSessionId)
    if (!session) return
  
    console.log('Resuming session:', session) // debug
  
    const messages = session.messages || []
  
    setSessionContext({
      resumeSummary: session.resume_summary,
      jobTitle: session.jobTitle,
      jobDescription: session.jobDescription || '',
    })
    setMessages(messages)
    setSessionSummary(session.feedback || '')
    setOverallScore(session.score ?? null)
    setOverallFeedback(session.feedback || '')
  
    // Determine if the interview is done:
    // If last message is from assistant and session has overall score, assume done
    const lastMessage = messages[messages.length - 1]
    const isDone = session.score != null && lastMessage?.role === 'assistant'
    setInterviewDone(isDone)
  
    // If interview is not done, prefill answer with last user input if any
    if (!isDone) {
      const lastUser = [...messages].reverse().find(m => m.role === 'user')
      if (lastUser) {
        setAnswer(lastUser.content)
      }
    }
  
    // Play last assistant message if TTS is enabled
    if (voiceEnabled && messages.length > 0) {
      const lastAssistant = [...messages].reverse().find(m => m.role === 'assistant')
      if (lastAssistant) {
        try {
          await playTTS(lastAssistant.content)
        } catch (err) {
          console.error('Failed to play TTS for resumed session:', err)
        }
      }
    }
  }
  

  // Play text via backend TTS proxy. Sends POST /api/tts and plays returned audio/mpeg.
  async function playTTS(text: string) {
    if (!text) return
    try {
      const res = await fetch('/api/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      })
      if (!res.ok) throw new Error('TTS request failed')
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const audio = new Audio(url)
      audio.autoplay = true
      // attempt to play and revoke url after playback
      await audio.play().catch(() => {})
      // revoke after a short delay to give the browser time to fetch
      setTimeout(() => URL.revokeObjectURL(url), 30000)
    } catch (e) {
      throw e
    }
  }

  useEffect(() => {
    loadSessions()
  }, [])

  async function fetchAnalytics() {
    setLoadingAnalytics(true)
    try {
      const res = await fetch('/api/analytics')
      const data = await res.json()
      setAnalytics(data)
    } catch (err) {
      console.error(err)
    } finally {
      setLoadingAnalytics(false)
    }
  }

  useEffect(() => {
    async function fetchAnalytics() {
      try {
        const res = await fetch('/api/analytics')
        const data = await res.json()
        setAnalytics(data)
      } catch (err) {
        console.error('Failed to fetch analytics', err)
      }
    }
  
    if (savedSessions.length > 0) {
      fetchAnalytics()
    }
  }, [savedSessions])
  
  return (
    <section className="chat">
      <div className="chat-inner">
        <div className="chat-header">
          <h2>AI Interviewer</h2>
          <div className="session-buttons">
            <button onClick={() => { setSessionSummary(''); setAnalysis(null); setMessages([]); setSessionContext(null); setInterviewDone(false); setOverallScore(null); setOverallFeedback(''); }}>New Session</button>
          </div>
        </div>

        <div className="chat-window">
          {analyzing ? (
            <p className="placeholder">Analyzing resume and starting interview…</p>
          ) : analysis && messages.length > 0 ? (
            <>
              <div className="messages">
                {messages.map((m, i) => (
                  <div key={i} className={`msg msg-${m.role}`}>
                    <span className="msg-label">{m.role === 'assistant' ? 'Interviewer' : 'You'}</span>
                    <p className="msg-content">{m.content}</p>
                  </div>
                ))}
                {sending && (
                  <div className="msg msg-assistant">
                    <span className="msg-label">Interviewer</span>
                    <p className="msg-content typing">Thinking of next question…</p>
                  </div>
                )}
              </div>
              {!interviewDone && (
                <div className="answer-area">
                  <textarea
                    placeholder="Type your answer or click the mic to speak…"
                    value={answer + (sttPartial ? (answer ? ' ' : '') + sttPartial : '')}
                    onChange={(e) => { setAnswer(e.target.value); setSttPartial('') }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault()
                        handleSendAnswer()
                      }
                    }}
                    rows={2}
                    disabled={sending}
                  />
                  {sttPartial && (
                    <p className="stt-partial">Hearing: <em>{sttPartial}</em></p>
                  )}
                  <div className="answer-actions">
                    <button
                      type="button"
                      className={`mic-btn ${isRecording ? 'mic-recording' : ''}`}
                      onClick={isRecording ? stopRecording : startRecording}
                      disabled={sending || interviewDone}
                      title={isRecording ? 'Stop recording' : 'Start speaking'}
                    >
                      {isRecording ? '⏹ Stop' : '🎤 Speak'}
                    </button>
                    <button
                      type="button"
                      className="send-btn"
                      onClick={handleSendAnswer}
                      disabled={sending || !answer.trim()}
                    >
                      {sending ? 'Sending…' : 'Send'}
                    </button>
                  </div>
                </div>
              )}
              {interviewDone && (
                <div className="session-ended-block">
                  {overallScore != null && (
                    <p className="overall-score">Interview score: <strong>{overallScore}/100</strong></p>
                  )}
                  {overallFeedback && (
                    <div className="overall-feedback">
                      <p className="overall-feedback-label">How you did (based on your answers, resume & job):</p>
                      <p className="overall-feedback-text">{overallFeedback}</p>
                    </div>
                  )}
                  <p className="session-ended">Session ended. Start a new session to try again.</p>
                </div>
              )}
            </>
          ) : analysis ? (
            <p className="placeholder">Something went wrong — no first question received.</p>
          ) : (
            <p className="placeholder">Upload resume, add job title & description, then click “Start interview”.</p>
          )}
          {analysisError && <p className="analysis-error">{analysisError}</p>}
        </div>
        <div className="controls">
          <button
            type="button"
            className="analyze-btn"
            onClick={handleAnalyze}
            disabled={analyzing || !resumeFile}
          >
            {analyzing ? 'Starting…' : 'Start interview'}
          </button>
          <div className="file-card">
            <label>Upload Resume</label>
            <input
              type="file"
              accept=".pdf,.doc,.docx,.txt"
              onChange={(e) => {
                const file = e.target.files?.[0]
                if (file) {
                  setResumeFile(file)
                  setFileName(file.name)
                } else {
                  setResumeFile(null)
                  setFileName('')
                }
              }}
            />
            <span className="file-name">{fileName || 'No file chosen'}</span>
          </div>

          <div className="file-card">
            <label>Voice</label>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <input
                id="voice-toggle"
                type="checkbox"
                checked={voiceEnabled}
                onChange={(e) => setVoiceEnabled(e.target.checked)}
              />
              <label htmlFor="voice-toggle" style={{ fontSize: 13 }}>Enable voice</label>
            </div>
          </div>

          <div className="job-card">
            <label>Job Title</label>
            <input
              type="text"
              placeholder="e.g. Software Engineer"
              value={jobTitle}
              onChange={(e) => setJobTitle(e.target.value)}
            />
          </div>
          <div className="job-card job-card-wide">
            <label>Job Description</label>
            <textarea
              placeholder="Paste the job description here..."
              value={jobDescription}
              onChange={(e) => setJobDescription(e.target.value)}
              rows={3}
            />
          </div>
        </div>
        <div className="file-card resume-card">
        <label>Reload Previous Session Summary</label>
        <select
            value={selectedSessionId}
            onChange={(e) => setSelectedSessionId(e.target.value)}
        >
            <option value="">Select a session…</option>
            {savedSessions.map((s) => (
            <option key={s._id} value={s._id}>
                {s.jobTitle} – {new Date(s.createdAt).toLocaleDateString()}
            </option>
            ))}
        </select>

        <button
            className="resume-btn"
            onClick={handleResumeSession}
        >
            Reload Summary
        </button>
        </div>
                <br></br>

        <div className="summary">
          <h3>Session Summary</h3>
          <p className="summary-hint">Summary of your performance (filled after the interview ends). You can copy or edit it.</p>
          <textarea
            placeholder="After the interview, the AI’s evaluation will appear here..."
            value={sessionSummary}
            onChange={(e) => setSessionSummary(e.target.value)}
          />

          <h3>Your notes (optional)</h3>
          <p className="summary-hint">Notes for yourself, e.g. what to improve for next time. Not sent anywhere.</p>
          <textarea
            placeholder="e.g. Practice explaining SQL optimizations more clearly..."
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
          />
        </div>

        <div className="analytics-section">
  <h3>Analytics</h3>

  {analytics ? (
    <div className="analytics-output">
      <div className="analytics-stats">
        <p>Total sessions: <strong>{analytics.count}</strong></p>
        <p>Average score: <strong>{analytics.avgScore?.toFixed(1)}</strong></p>
        <p>Min score: <strong>{analytics.minScore}</strong></p>
        <p>Max score: <strong>{analytics.maxScore}</strong></p>
      </div>

      {analytics.aiAnalysis && !analytics.aiAnalysis.error && (
        <div className="ai-insights">
          <h4>Overall Candidate Insights</h4>
          <p><strong>Fit score:</strong> {analytics.aiAnalysis.fitScore}/100</p>
          <p><strong>Reason:</strong> {analytics.aiAnalysis.fitReason}</p>
          <p><strong>First interview question suggested:</strong> {analytics.aiAnalysis.firstQuestion}</p>
          <p><strong>Resume summary:</strong> {analytics.aiAnalysis.resumeSummary}</p>
          <p><strong>Themes:</strong> {analytics.aiAnalysis.themes}</p>
          <p><strong>Sentiment Summary:</strong> {analytics.aiAnalysis.sentimentSummary}</p>
        </div>
      )}

      {analytics.aiAnalysis?.error && (
        <p className="analysis-error">{analytics.aiAnalysis.error}</p>
      )}
    </div>
  ) : (
    <p className="placeholder">Analytics will appear here once sessions exist.</p>
  )}
</div>


      </div>
    </section>
  )
}