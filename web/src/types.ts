// Shapes of the Python API (app/api/schemas.py).

export interface Fact {
  label: string
  value: string
}

export interface Booking {
  id: number
  slot_datetime: string
  party_size: number
  table_id: number
}

export interface SessionInfo {
  session_id: string
  customer: { id: number; name: string }
  greeting: string | null
  remembered: Fact[]
  memory_unavailable: boolean
  upcoming: Booking[] | null // null: the bookings could not be loaded
  voice: boolean // the server can take voice
}

export type TraceEvent = { event: string } & Record<string, unknown>

export interface Reply {
  text: string
  stop_reason: string
  trace: TraceEvent[]
}

/** A reply that came over the voice socket: the same reply plus how the speaking went. */
export interface VoiceReply extends Reply {
  first_audio_ms: number | null
  speech_error: string | null // set when the reply could not be spoken
  interrupted: boolean // the customer cut the speech off; the text is still the full reply
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  text: string
  trace?: TraceEvent[]
}
