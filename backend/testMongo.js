import 'dotenv/config'
import { saveSession, getSessions } from './mongo.js'

async function test() {
  try {
    // Save a dummy session
    const result = await saveSession({
      jobTitle: 'Software Engineer',
      feedback: 'This candidate is great!',
      messages: [
        { role: 'assistant', content: 'Tell me about your experience.' },
        { role: 'user', content: 'I have 3 years in full-stack development.' }
      ],
      score: 85,
      resume_summary: 'Experienced full-stack developer.',
      createdAt: new Date(),
    })
    console.log('Saved session _id:', result.insertedId)

    // Retrieve sessions
    const sessions = await getSessions()
    console.log('Sessions in DB:', sessions)
  } catch (err) {
    console.error('Mongo test failed:', err)
  }
}

test()
