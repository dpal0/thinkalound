import 'dotenv/config'
import express from 'express'
import cors from 'cors'
import multer from 'multer'
import { GoogleGenerativeAI } from '@google/generative-ai'

import { pipeline } from 'stream'
import { promisify } from 'util'

const streamPipeline = promisify(pipeline)

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

  "resumeSummary": "3-5 sentence, plain-language summary of the candidate from the resume (write simply, as if explaining to a hiring manager who needs a quick, human-readable snapshot)",
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

  // debug logging removed
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

  // debug logging removed
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

  const { resumeSummary, jobTitle, jobDescription, messages, fitScore: clientFitScore } = req.body || {}
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


    // If the model signalled the interview is done, attempt per-question scoring and overall aggregation.
    if (out && out.done) {
      try {
        const userMessages = (messages || []).map((m, i) => ({ ...m, i })).filter((m) => m.role === 'user')
        if (userMessages.length > 0) {
          const genAI = new GoogleGenerativeAI(GEMINI_API_KEY)
          const model = genAI.getGenerativeModel({ model: GEMINI_MODEL })

          const convo = (messages || [])
            .map((m) => (m.role === 'assistant' ? `Interviewer: ${m.content}` : `Candidate: ${m.content}`))
            .join('\n')

          const scorePrompt = `You are an experienced hiring manager. Given the resume summary and job description below, score each candidate answer in the conversation on a scale 0-10 (10 best). Return ONLY valid JSON: {"perQuestionScores": [{"index": <message index>, "score": <0-10 number>, "reason": "one-sentence reason"}], "answersAverage": <0-10 number>}.\n\nResume summary: ${resumeSummary}\nJob title: ${jobTitle}\nJob description: ${jobDescription}\n\nConversation:\n${convo}`

          const scoreResult = await model.generateContent(scorePrompt)
          const scoreResp = scoreResult.response
          if (scoreResp && typeof scoreResp.text === 'function') {
            const raw = scoreResp.text().trim()
            const jsonStr = raw.replace(/^```json?\s*/i, '').replace(/\s*```$/, '')
            try {
              const parsed = JSON.parse(jsonStr)
              if (Array.isArray(parsed.perQuestionScores)) {
                out.perQuestionScores = parsed.perQuestionScores
                const avg10 = typeof parsed.answersAverage === 'number'
                  ? parsed.answersAverage
                  : (parsed.perQuestionScores.reduce((s, p) => s + (typeof p.score === 'number' ? p.score : 0), 0) / parsed.perQuestionScores.length)
                const answersAvgPct = Math.round((avg10 / 10) * 100)
                const fit = typeof clientFitScore === 'number' ? clientFitScore : null
                if (fit != null) {
                  out.overallScore = Math.round(0.4 * fit + 0.6 * answersAvgPct)
                } else if (typeof out.overallScore !== 'number') {
                  out.overallScore = answersAvgPct
                }
              }
            } catch (e) {
              // ignore parse errors
            }
          }
        }
      } catch (e) {
        // ignore scoring errors
      }
    }

    // If the model signalled the interview is done but didn't include an overall score/feedback,
    // ask Gemini to evaluate the interview (score + short feedback) using the resume summary and job.
    if (out && out.done && (typeof out.overallScore !== 'number' || !out.overallFeedback)) {
      try {
        const genAI = new GoogleGenerativeAI(GEMINI_API_KEY)
        const model = genAI.getGenerativeModel({ model: GEMINI_MODEL })

        const convo = messages
          .map((m) => (m.role === 'assistant' ? `Interviewer: ${m.content}` : `Candidate: ${m.content}`))
          .join('\n')

  const evalPrompt = `You are an experienced interviewer and hiring manager. Based only on the candidate resume summary and the interview conversation below, produce a JSON object with these fields: {"done": true, "overallScore": <number 0-100>, "overallFeedback": "3-5 sentence, plain-language summary of how well the candidate answered relative to the job (clear strengths, most important improvement areas) — write simply and directly", "closingMessage": "brief closing message to candidate"}. Resume summary: ${resumeSummary}\nJob title: ${jobTitle}\nJob description: ${jobDescription}\n\nConversation:\n${convo}\n\nReturn ONLY valid JSON.`

        const evalResult = await model.generateContent(evalPrompt)
        const evalResp = evalResult.response
        if (evalResp && typeof evalResp.text === 'function') {
          const raw = evalResp.text().trim()
          const jsonStr = raw.replace(/^```json?\s*/i, '').replace(/\s*```$/, '')
          try {
            const parsed = JSON.parse(jsonStr)
            // merge evaluation fields into out
            out.overallScore = typeof parsed.overallScore === 'number' ? parsed.overallScore : out.overallScore
            out.overallFeedback = parsed.overallFeedback || out.overallFeedback
            out.closingMessage = parsed.closingMessage || out.closingMessage
          } catch (e) {
            // ignore parse errors and return out as-is
          }
        }
      } catch (e) {
        // ignore evaluation errors and return original out
      }
    }

    res.json(out)
  } catch (err) {
  // debug logging removed
    res.status(500).json({ error: 'Failed to get next question', details: err.message })
  }
})


// ElevenLabs TTS proxy: streams audio/mpeg back to the browser
app.post('/api/tts', async (req, res) => {
  try {
    const text = (req.body && req.body.text) ? String(req.body.text).trim() : ''
    const model_id = req.body && req.body.model_id
    if (!text) return res.status(400).json({ error: 'text is required' })

    const apiKey = process.env.ELEVENLABS_API_KEY
    const voiceId = process.env.ELEVENLABS_VOICE_ID
    if (!apiKey || !voiceId) {
      return res.status(503).json({ error: 'ElevenLabs not configured. Set ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID in .env' })
    }

    const ttsUrl = `https://api.elevenlabs.io/v1/text-to-speech/${voiceId}/stream`
    const headers = {
      'xi-api-key': apiKey,
      Accept: 'audio/mpeg',
      'Content-Type': 'application/json',
    }
    const payload = { text }
    if (model_id) payload.model_id = model_id

    const resp = await fetch(ttsUrl, { method: 'POST', headers, body: JSON.stringify(payload) })
    if (!resp.ok) {
      const errText = await resp.text()
      return res.status(502).json({ error: `ElevenLabs TTS error ${resp.status}: ${errText.slice(0, 300)}` })
    }

    res.setHeader('Content-Type', 'audio/mpeg')

    const body = resp.body
    // If body is a Node stream, pipe directly. Otherwise read as web stream.
    if (body && typeof body.pipe === 'function') {
      // Node stream
      body.pipe(res)
    } else if (body && typeof body.getReader === 'function') {
      // WHATWG ReadableStream
      const reader = body.getReader()
      try {
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          if (value) res.write(Buffer.from(value))
        }
      } catch (e) {
        // ignore stream errors; end the response
      } finally {
        res.end()
      }
    } else {
      // Fallback: buffer the whole body
      const buf = await resp.arrayBuffer()
      res.end(Buffer.from(buf))
    }
  } catch (err) {
    // minimal error reporting
    res.status(500).json({ error: 'TTS proxy failed', details: String(err) })
  }
})

app.listen(PORT, () => {
  // debug logs removed for cleaner output
})

// import 'dotenv/config'
// import express from 'express'
// import cors from 'cors'
// import multer from 'multer'
// import { GoogleGenerativeAI } from '@google/generative-ai'

// const app = express()
// const PORT = process.env.PORT || 3001
// const GEMINI_API_KEY = process.env.GEMINI_API_KEY

// // Updated model names that actually exist in current API
// // Try these in order: gemini-2.5-flash, gemini-2.5-pro, gemini-2.0-flash-exp
// const GEMINI_MODEL = process.env.GEMINI_MODEL || 'gemini-2.5-flash'

// const upload = multer({ storage: multer.memoryStorage() })

// app.use(cors())
// app.use(express.json())

// app.get('/api/health', (req, res) => {
//   res.json({ ok: true, model: GEMINI_MODEL })
// })

// // Test endpoint to verify API key and model work
// app.get('/api/test-gemini', async (req, res) => {
//   if (!GEMINI_API_KEY) {
//     return res.status(503).json({ error: 'GEMINI_API_KEY not set in .env file' })
//   }

//   // Try multiple models to see which one works
//   const modelsToTry = [
//     'gemini-2.5-flash'  ]

//   const results = []
  
//   for (const modelName of modelsToTry) {
//     try {
//       const genAI = new GoogleGenerativeAI(GEMINI_API_KEY)
//       const model = genAI.getGenerativeModel({ model: modelName })
//       const result = await model.generateContent('Say "works"')
//       const response = await result.response
//       const text = response.text()
//       results.push({ model: modelName, status: 'SUCCESS', response: text })
//       // If we found one that works, return it
//       return res.json({ 
//         success: true, 
//         workingModel: modelName,
//         message: 'API key is valid!',
//         allResults: results,
//         suggestion: `Update your .env file with: GEMINI_MODEL=${modelName}`
//       })
//     } catch (err) {
//       results.push({ model: modelName, status: 'FAILED', error: err.message })
//     }
//   }

//   // None worked
//   res.status(500).json({ 
//     error: 'No working models found', 
//     results,
//     suggestion: 'Your API key might be invalid or restricted. Get a new one from https://aistudio.google.com/app/apikey'
//   })
// })

// // Call Gemini: parse resume, score fit, generate questions
// async function analyzeWithGemini(file, jobTitle, jobDescription) {
//   const genAI = new GoogleGenerativeAI(GEMINI_API_KEY)
//   const model = genAI.getGenerativeModel({ model: GEMINI_MODEL })

//   const isPdf = file.mimetype === 'application/pdf'
//   const prompt = `You are a recruiter. Use the attached resume and this job info to:
// - Job title: ${jobTitle}
// - Job description: ${jobDescription}

// Respond with ONLY valid JSON (no markdown, no extra text) in this exact shape:
// {
//   "resumeSummary": "2-3 sentence summary of the candidate from the resume",
//   "fitScore": number from 0 to 100,
//   "fitReason": "one sentence on why this score",
//   "firstQuestion": "the first interview question to ask this candidate for this role (one question only)"
// }`

//   let result
//   if (isPdf) {
//     const base64 = file.buffer.toString('base64')
//     result = await model.generateContent([
//       {
//         inlineData: {
//           mimeType: 'application/pdf',
//           data: base64,
//         },
//       },
//       { text: prompt },
//     ])
//   } else {
//     // .txt or plain text: send as text
//     const text = file.buffer.toString('utf-8')
//     result = await model.generateContent([
//       { text: `Resume content:\n${text}\n\n${prompt}` },
//     ])
//   }

//   const response = result.response
//   if (!response) {
//     throw new Error('No response from Gemini')
//   }
//   let raw = ''
//   try {
//     raw = (typeof response.text === 'function' ? response.text() : '')?.trim() || ''
//   } catch (e) {
//     throw new Error('No response from Gemini')
//   }
//   if (!raw) {
//     throw new Error('Gemini returned empty text (possible safety block or error)')
//   }
//   const jsonStr = raw.replace(/^```json?\s*/i, '').replace(/\s*```$/, '').trim()
//   try {
//     return JSON.parse(jsonStr)
//   } catch (parseErr) {
//     console.error('Gemini returned non-JSON. Raw:', raw.slice(0, 500))
//     throw new Error('Gemini returned invalid JSON. Try again or use a different resume.')
//   }
// }

// // Get next interview question (or end) from conversation so far
// async function getNextQuestion(resumeSummary, jobTitle, jobDescription, messages) {
//   const genAI = new GoogleGenerativeAI(GEMINI_API_KEY)
//   const model = genAI.getGenerativeModel({ model: GEMINI_MODEL })

//   const convo = messages
//     .map((m) => (m.role === 'assistant' ? `Interviewer: ${m.content}` : `Candidate: ${m.content}`))
//     .join('\n')

//   const prompt = `You are an interviewer conducting a live interview.

// Candidate resume summary: ${resumeSummary}
// Job title: ${jobTitle}
// Job description: ${jobDescription}

// Conversation so far:
// ${convo}

// Based on the resume, job, and the candidate's answers so far, respond with ONLY valid JSON (no markdown):
// - If you have another relevant question to ask, use: {"nextQuestion": "your question here"}
// - If the interview should end (enough questions asked), use: {"done": true, "closingMessage": "Thank you for your time. We'll be in touch."}

// Ask 5-8 relevant questions total. Mix experience, skills, and role-fit. Then end the interview.`
//   const result = await model.generateContent(prompt)
//   const response = result.response
//   if (!response || !response.text()) throw new Error('No response from Gemini')
//   const raw = response.text().trim()
//   const jsonStr = raw.replace(/^```json?\s*/i, '').replace(/\s*```$/, '')
//   return JSON.parse(jsonStr)
// }

// app.post('/api/analyze', upload.single('resume'), async (req, res) => {
//   const file = req.file
//   const jobTitle = req.body.jobTitle || ''
//   const jobDescription = req.body.jobDescription || ''

//   if (!file) {
//     return res.status(400).json({ error: 'Resume file is required' })
//   }

//   if (!GEMINI_API_KEY) {
//     return res.status(503).json({
//       error: 'Gemini API key not set. Add GEMINI_API_KEY to backend/.env (see .env.example).',
//     })
//   }

//   try {
//     const analysis = await analyzeWithGemini(file, jobTitle, jobDescription)
//     if (!analysis.firstQuestion || typeof analysis.fitScore !== 'number') {
//       throw new Error('Invalid shape from Gemini (missing firstQuestion or fitScore)')
//     }
//     res.json(analysis)
//   } catch (err) {
//     console.error('Gemini error:', err)
//     res.status(500).json({
//       error: err.message || 'Analysis failed',
//       details: err.message || String(err),
//     })
//   }
// })

// // Continue live session: send messages so far, get next question or done
// app.post('/api/interview/next', async (req, res) => {
//   if (!GEMINI_API_KEY) {
//     return res.status(503).json({ error: 'Gemini API key not set.' })
//   }
//   const { resumeSummary, jobTitle, jobDescription, messages } = req.body || {}
//   if (!resumeSummary || !Array.isArray(messages) || messages.length === 0) {
//     return res.status(400).json({ error: 'resumeSummary and messages array required' })
//   }
//   try {
//     const out = await getNextQuestion(
//       resumeSummary,
//       jobTitle || '',
//       jobDescription || '',
//       messages
//     )
//     res.json(out)
//   } catch (err) {
//     console.error('Interview next error:', err)
//     res.status(500).json({ error: 'Failed to get next question', details: err.message })
//   }
// })

// app.listen(PORT, () => {
//   console.log(`Backend running at http://localhost:${PORT}`)
//   console.log(`Using Gemini model: ${GEMINI_MODEL}`)
//   console.log(`API key configured: ${GEMINI_API_KEY ? 'Yes' : 'No'}`)
//   console.log(`\nTest your setup at: http://localhost:${PORT}/api/test-gemini`)
//   console.log(`GEMINI_API_KEY: ${GEMINI_API_KEY}`)
// })