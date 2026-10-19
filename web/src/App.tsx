import { useState } from 'react'
import { api } from './api'
import { ChatPanel } from './components/ChatPanel'
import { LoginForm } from './components/LoginForm'
import { Sidebar } from './components/Sidebar'
import type { ChatMessage, SessionInfo } from './types'
import { useVoice } from './voice/useVoice'

const opening = (session: SessionInfo): ChatMessage[] =>
  session.greeting ? [{ role: 'assistant', text: session.greeting }] : []

const describe = (e: unknown) => (e instanceof Error ? e.message : 'Something went wrong')

export default function App() {
  const [session, setSession] = useState<SessionInfo | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  // Open on a wide screen, closed on a phone, where the sidebar is a drawer over the chat.
  const [sidebarOpen, setSidebarOpen] = useState(() => window.matchMedia('(min-width: 768px)').matches)

  async function refresh(id: string) {
    setSession(await api.session(id)) // bookings may have changed
  }

  const voice = useVoice(session?.session_id ?? null, session?.voice ?? false, {
    onHeard: (text) => {
      setError('')
      setMessages((m) => [...m, { role: 'user', text }])
    },
    onReply: (reply) => {
      setMessages((m) => [...m, { role: 'assistant', text: reply.text, trace: reply.trace }])
      if (reply.speech_error) setError('Voice reply unavailable; showing text only.')
      if (session) refresh(session.session_id).catch(() => undefined)
    },
    onError: setError,
  })

  if (!session) {
    return (
      <LoginForm
        onLogin={(s) => {
          setSession(s)
          setMessages(opening(s))
        }}
      />
    )
  }

  async function send(text: string) {
    if (!session) return
    setError('')
    setBusy(true)
    setMessages((m) => [...m, { role: 'user', text }])
    try {
      const reply = await api.send(session.session_id, text)
      setMessages((m) => [...m, { role: 'assistant', text: reply.text, trace: reply.trace }])
      await refresh(session.session_id)
    } catch (e) {
      setError(describe(e))
    } finally {
      setBusy(false)
    }
  }

  async function newChat() {
    if (!session) return
    setError('')
    try {
      const fresh = await api.newChat(session.session_id)
      setSession(fresh)
      setMessages(opening(fresh))
    } catch (e) {
      setError(describe(e))
    }
  }

  async function signOut() {
    if (session) await api.end(session.session_id).catch(() => undefined)
    setSession(null)
    setMessages([])
  }

  const waiting = busy || voice.state === 'working'

  return (
    <div className="flex h-full overflow-hidden">
      <Sidebar
        session={session}
        open={sidebarOpen}
        busy={waiting}
        onClose={() => setSidebarOpen(false)}
        onNewChat={newChat}
        onSignOut={signOut}
      />
      <ChatPanel
        messages={messages}
        customerName={session.customer.name}
        busy={waiting}
        error={error}
        sidebarOpen={sidebarOpen}
        onToggleSidebar={() => setSidebarOpen((open) => !open)}
        onSend={send}
        voice={
          session.voice
            ? {
                state: voice.state,
                handsFree: voice.handsFree,
                onMic: voice.toggle,
                onCancel: voice.cancel,
                onHandsFree: voice.toggleHandsFree,
              }
            : undefined
        }
      />
    </div>
  )
}
