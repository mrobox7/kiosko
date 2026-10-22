import { useState } from 'react'
import { api, ApiError } from '../api'
import type { VoiceControls } from '../components/assistant/Composer'
import type { ChatMessage, SessionInfo } from '../types'
import { useVoice } from '../voice/useVoice'

const describe = (e: unknown) => (e instanceof Error ? e.message : 'Something went wrong')

/** The chat and voice side of an order: what was said, and sending a message. Created once per
 * order, so a new order starts with a fresh conversation. `onChanged` runs after the assistant
 * spoke, since it may have changed the order. */
export function useAssistant(session: SessionInfo, onChanged: () => void, onActivity: () => void) {
  const [messages, setMessages] = useState<ChatMessage[]>(() =>
    session.greeting ? [{ role: 'assistant', text: session.greeting }] : [],
  )
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const voice = useVoice(session.status === 'open' ? session.session_id : null, session.voice, {
    onHeard: (text) => {
      setError('')
      onActivity()
      setMessages((m) => [...m, { role: 'user', text }])
    },
    onReply: (reply) => {
      onActivity()
      setMessages((m) => [...m, { role: 'assistant', text: reply.text, trace: reply.trace }])
      if (reply.speech_error) setError('Voice reply unavailable; showing text only.')
      onChanged()
    },
    onError: setError,
  })

  async function send(text: string) {
    setError('')
    setBusy(true)
    onActivity()
    setMessages((m) => [...m, { role: 'user', text }])
    try {
      const reply = await api.send(session.session_id, text)
      setMessages((m) => [...m, { role: 'assistant', text: reply.text, trace: reply.trace }])
      onChanged()
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) onChanged() // the order ended: refreshing shows it
      else setError(e instanceof ApiError && e.status === 409 ? 'Hold on, still answering.' : describe(e))
    } finally {
      setBusy(false)
      onActivity()
    }
  }

  const controls: VoiceControls | undefined = session.voice
    ? {
        state: voice.state,
        handsFree: voice.handsFree,
        onMic: voice.toggle,
        onCancel: voice.cancel,
        onHandsFree: voice.toggleHandsFree,
      }
    : undefined

  return { messages, busy: busy || voice.state === 'working', error, send, voice: controls }
}
