import 'dotenv/config'
import express from 'express'
import cors from 'cors'
import multer from 'multer'
import { GoogleGenerativeAI } from '@google/generative-ai'

const app = express()
const PORT = process.env.PORT || 3001
const GEMINI_API_KEY = process.env.GEMINI_API_KEY

// Updated model names that actually exist in current API
// Try these in order: gemini-2.5-flash, gemini-2.5-pro, gemini-2.0-flash-exp
const GEMINI_MODEL = process.env.GEMINI_MODEL || 'gemini-2.5-flash'

const upload = multer({ storage: multer.memoryStorage() })

app.use(cors())
app.use(express.json())

app.get('/api/health', (req, res) => {
  res.json({ ok: true, model: GEMINI_MODEL })
})

// Test endpoint to verify API key and model work
app.get('/api/test-gemini', async (req, res) => {
  if (!GEMINI_API_KEY) {
    return res.status(503).json({ error: 'GEMINI_API_KEY not set in .env file' })
  }

  // Try multiple models to see which one works
  const modelsToTry = [
    'gemini-2.5-flash'  ]

  const results = []
  
  for (const modelName of modelsToTry) {
    try {
      const genAI = new GoogleGenerativeAI(GEMINI_API_KEY)
      const model = genAI.getGenerativeModel({ model: modelName })
      const result = await model.generateContent('Say "works"')
      const response = await result.response
      const text = response.text()
      results.push({ model: modelName, status: 'SUCCESS', response: text })
      // If we found one that works, return it
      return res.json({ 
        success: true, 
        workingModel: modelName,
        message: 'API key is valid!',
        allResults: results,
        suggestion: `Update your .env file with: GEMINI_MODEL=${modelName}`
      })
    } catch (err) {
      results.push({ model: modelName, status: 'FAILED', error: err.message })
    }
  }

  // None worked
  res.status(500).json({ 
    error: 'No working models found', 
    results,
    suggestion: 'Your API key might be invalid or restricted. Get a new one from https://aistudio.google.com/app/apikey'
  })
})

// Call Gemini: parse resume, score fit, generate questions
async function analyzeWithGemini(file, jobTitle, jobDescription) {
  const genAI = new GoogleGenerativeAI(GEMINI_API_KEY)
  const model = genAI.getGenerativeModel({ model: GEMINI_MODEL })

  const isPdf = file.mimetype === 'application/pdf'
  const prompt = `You are a recruiter. Use the attached resume and this job info to:
- Job title: ${jobTitle}
- Job description: ${jobDescription}

Respond with ONLY valid JSON (no markdown, no extra text) in this exact shape:
{
  "resumeSummary": "2-3 sentence summary of the candidate from the resume",
  "fitScore": number from 0 to 100,
  "fitReason": "one sentence on why this score",
  "firstQuestion": "the first interview question to ask this candidate for this role (one question only)"
}`

  let result
  if (isPdf) {
    const base64 = file.buffer.toString('base64')
    result = await model.generateContent([
      {
        inlineData: {
          mimeType: 'application/pdf',
          data: base64,
        },
      },
      { text: prompt },
    ])
  } else {
    // .txt or plain text: send as text
    const text = file.buffer.toString('utf-8')
    result = await model.generateContent([
      { text: `Resume content:\n${text}\n\n${prompt}` },
    ])
  }

  const response = result.response
  if (!response) {
    throw new Error('No response from Gemini')
  }
  let raw = ''
  try {
    raw = (typeof response.text === 'function' ? response.text() : '')?.trim() || ''
  } catch (e) {
    throw new Error('No response from Gemini')
  }
  if (!raw) {
    throw new Error('Gemini returned empty text (possible safety block or error)')
  }
  const jsonStr = raw.replace(/^```json?\s*/i, '').replace(/\s*```$/, '').trim()
  try {
    return JSON.parse(jsonStr)
  } catch (parseErr) {
    console.error('Gemini returned non-JSON. Raw:', raw.slice(0, 500))
    throw new Error('Gemini returned invalid JSON. Try again or use a different resume.')
  }
}

// Get next interview question (or end) from conversation so far
async function getNextQuestion(resumeSummary, jobTitle, jobDescription, messages) {
  const genAI = new GoogleGenerativeAI(GEMINI_API_KEY)
  const model = genAI.getGenerativeModel({ model: GEMINI_MODEL })

  const convo = messages
    .map((m) => (m.role === 'assistant' ? `Interviewer: ${m.content}` : `Candidate: ${m.content}`))
    .join('\n')

  const prompt = `You are an interviewer conducting a live interview.

Candidate resume summary: ${resumeSummary}
Job title: ${jobTitle}
Job description: ${jobDescription}

Conversation so far:
${convo}

Based on the resume, job, and the candidate's answers so far, respond with ONLY valid JSON (no markdown):
- If you have another relevant question to ask, use: {"nextQuestion": "your question here"}
- If the interview should end (enough questions asked), use: {"done": true, "closingMessage": "Thank you for your time. We'll be in touch."}

Ask 5-8 relevant questions total. Mix experience, skills, and role-fit. Then end the interview.`
  const result = await model.generateContent(prompt)
  const response = result.response
  if (!response || !response.text()) throw new Error('No response from Gemini')
  const raw = response.text().trim()
  const jsonStr = raw.replace(/^```json?\s*/i, '').replace(/\s*```$/, '')
  return JSON.parse(jsonStr)
}

app.post('/api/analyze', upload.single('resume'), async (req, res) => {
  const file = req.file
  const jobTitle = req.body.jobTitle || ''
  const jobDescription = req.body.jobDescription || ''

  if (!file) {
    return res.status(400).json({ error: 'Resume file is required' })
  }

  if (!GEMINI_API_KEY) {
    return res.status(503).json({
      error: 'Gemini API key not set. Add GEMINI_API_KEY to backend/.env (see .env.example).',
    })
  }

  try {
    const analysis = await analyzeWithGemini(file, jobTitle, jobDescription)
    if (!analysis.firstQuestion || typeof analysis.fitScore !== 'number') {
      throw new Error('Invalid shape from Gemini (missing firstQuestion or fitScore)')
    }
    res.json(analysis)
  } catch (err) {
    console.error('Gemini error:', err)
    res.status(500).json({
      error: err.message || 'Analysis failed',
      details: err.message || String(err),
    })
  }
})

// Continue live session: send messages so far, get next question or done
app.post('/api/interview/next', async (req, res) => {
  if (!GEMINI_API_KEY) {
    return res.status(503).json({ error: 'Gemini API key not set.' })
  }
  const { resumeSummary, jobTitle, jobDescription, messages } = req.body || {}
  if (!resumeSummary || !Array.isArray(messages) || messages.length === 0) {
    return res.status(400).json({ error: 'resumeSummary and messages array required' })
  }
  try {
    const out = await getNextQuestion(
      resumeSummary,
      jobTitle || '',
      jobDescription || '',
      messages
    )
    res.json(out)
  } catch (err) {
    console.error('Interview next error:', err)
    res.status(500).json({ error: 'Failed to get next question', details: err.message })
  }
})

app.listen(PORT, () => {
  console.log(`Backend running at http://localhost:${PORT}`)
  console.log(`Using Gemini model: ${GEMINI_MODEL}`)
  console.log(`API key configured: ${GEMINI_API_KEY ? 'Yes' : 'No'}`)
  console.log(`\nTest your setup at: http://localhost:${PORT}/api/test-gemini`)
  console.log(`GEMINI_API_KEY: ${GEMINI_API_KEY}`)
})