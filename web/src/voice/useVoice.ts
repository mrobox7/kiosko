import { useCallback, useEffect, useRef, useState } from 'react'
import type { VoiceReply } from '../types'
import type { Listener } from './listener'
import { StreamPlayer } from './player'
import { Recorder } from './recorder'
import { VoiceSocket } from './socket'

/**
 * idle        nothing going on
 * recording   push-to-talk: the mic is recording until the customer taps again
 * listening   hands-free: waiting for the customer to speak
 * hearing     hands-free: the customer is speaking
 * working     a clip was sent; the reply is being made
 * speaking    the reply is being played
 */
export type VoiceState = 'idle' | 'recording' | 'listening' | 'hearing' | 'working' | 'speaking'

export interface VoiceCallbacks {
  onHeard: (text: string) => void
  onReply: (reply: VoiceReply) => void
  onError: (message: string) => void
}

/** Voice for one chat: tap to talk, or hands-free where speaking over the agent interrupts it. */
export function useVoice(sessionId: string | null, available: boolean, callbacks: VoiceCallbacks) {
  const [state, setState] = useState<VoiceState>('idle')
  const [handsFree, setHandsFree] = useState(false)
  const recorder = useRef<Recorder | null>(null)
  const socket = useRef<VoiceSocket | null>(null)
  const player = useRef<StreamPlayer | null>(null)
  const listener = useRef<Listener | null>(null)
  const outstanding = useRef(0) // clips sent whose reply has not come back yet
  const hearing = useRef(false) // the customer is speaking right now (hands-free)
  const handsFreeOn = useRef(false)
  const latest = useRef(callbacks)
  useEffect(() => {
    latest.current = callbacks
  })

  /** Show what is going on now. The customer speaking always wins over everything else. */
  const settle = useCallback(() => {
    if (hearing.current) setState('hearing')
    else if (player.current) setState('speaking') // audio is playing even if the reply is not complete
    else if (outstanding.current > 0) setState('working')
    else setState(handsFreeOn.current ? 'listening' : 'idle')
  }, [])

  const stopPlayback = useCallback(() => {
    player.current?.stop()
    player.current = null
  }, [])

  // A different chat (or leaving the page) ends everything that belongs to this one.
  useEffect(
    () => () => {
      socket.current?.close()
      socket.current = null
      stopPlayback()
      recorder.current?.cancel()
      recorder.current = null
      void listener.current?.stop()
      listener.current = null
      outstanding.current = 0
      hearing.current = false
      handsFreeOn.current = false
      setHandsFree(false)
      setState('idle')
    },
    [sessionId, stopPlayback],
  )

  const connect = useCallback(async (): Promise<VoiceSocket> => {
    if (socket.current?.open) return socket.current
    if (!sessionId) throw new Error('No chat')
    const connection = new VoiceSocket(sessionId, {
      onHeard: (text) => latest.current.onHeard(text),
      onAudioStart: (mime) => {
        stopPlayback()
        if (hearing.current) return // the customer is talking over it: do not start speaking
        player.current = new StreamPlayer(mime, () => {
          player.current = null
          settle()
        })
        settle()
      },
      onAudio: (chunk) => player.current?.feed(chunk),
      onReply: (reply) => {
        outstanding.current = Math.max(0, outstanding.current - 1)
        player.current?.end() // no more chunks for the reply that is being played
        latest.current.onReply(reply)
        settle()
      },
      onError: (message) => {
        outstanding.current = Math.max(0, outstanding.current - 1)
        settle()
        latest.current.onError(message)
      },
      onClose: () => {
        socket.current = null
        if (outstanding.current > 0) {
          outstanding.current = 0
          stopPlayback()
          settle()
          latest.current.onError('The voice connection was lost. Please try again.')
        }
      },
    })
    socket.current = connection
    await connection.ready()
    return connection
  }, [sessionId, settle, stopPlayback])

  const sendClip = useCallback(
    async (clip: Blob) => {
      outstanding.current += 1
      settle()
      try {
        ;(await connect()).send(clip)
      } catch {
        outstanding.current = Math.max(0, outstanding.current - 1)
        settle()
        latest.current.onError('Voice is unavailable right now. Please type instead.')
      }
    },
    [connect, settle],
  )

  /** Push-to-talk: tap to record, tap to send, tap while it speaks to stop it. */
  const toggle = useCallback(async () => {
    if (!sessionId || !available || handsFreeOn.current) return
    if (state === 'idle') {
      const next = new Recorder()
      try {
        await next.start()
      } catch {
        latest.current.onError('Could not use the microphone. Check the browser permission.')
        return
      }
      recorder.current = next
      setState('recording')
      void connect().catch(() => undefined) // open the connection while the customer speaks
    } else if (state === 'recording') {
      const clip = await recorder.current?.stop()
      recorder.current = null
      if (!clip) {
        setState('idle')
        latest.current.onError('I did not catch that. Tap the mic, speak, then tap again.')
        return
      }
      await sendClip(clip)
    } else if (state === 'speaking') {
      stopPlayback()
      socket.current?.interrupt()
      settle()
    }
  }, [sessionId, available, state, connect, sendClip, settle, stopPlayback])

  const cancel = useCallback(() => {
    recorder.current?.cancel()
    recorder.current = null
    setState('idle')
  }, [])

  /** Hands-free on or off. While on, speaking over the agent interrupts it. */
  const toggleHandsFree = useCallback(async () => {
    if (!sessionId || !available) return
    if (handsFreeOn.current) {
      await listener.current?.stop()
      listener.current = null
      handsFreeOn.current = false
      hearing.current = false
      setHandsFree(false)
      if (player.current || outstanding.current > 0) socket.current?.interrupt()
      stopPlayback()
      settle()
      return
    }
    if (state !== 'idle') return
    try {
      // loaded on demand: the VAD runtime is large and most pages never turn hands-free on
      const { startListening } = await import('./listener')
      listener.current = await startListening({
        onSpeechStart: () => {
          hearing.current = true
          if (player.current || outstanding.current > 0) socket.current?.interrupt()
          stopPlayback()
          settle()
        },
        onSpeechEnd: (clip) => {
          hearing.current = false
          void sendClip(clip)
        },
        onMisfire: () => {
          hearing.current = false
          settle()
        },
      })
    } catch {
      latest.current.onError('Could not start hands-free listening. Check the microphone permission.')
      return
    }
    handsFreeOn.current = true
    setHandsFree(true)
    void connect().catch(() => undefined)
    settle()
  }, [sessionId, available, state, connect, sendClip, settle, stopPlayback])

  return { state, handsFree, toggle, cancel, toggleHandsFree }
}
