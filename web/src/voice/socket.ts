import type { VoiceReply } from '../types'

export interface VoiceHandlers {
  onHeard: (text: string) => void
  onAudioStart: (mime: string) => void
  onAudio: (chunk: ArrayBuffer) => void
  onReply: (reply: VoiceReply) => void
  onError: (message: string) => void
  onClose: () => void
}

/** The voice connection of one chat: one clip in, events and audio chunks out. */
export class VoiceSocket {
  private readonly socket: WebSocket

  constructor(sessionId: string, handlers: VoiceHandlers) {
    const scheme = location.protocol === 'https:' ? 'wss' : 'ws'
    this.socket = new WebSocket(`${scheme}://${location.host}/api/sessions/${sessionId}/voice`)
    this.socket.binaryType = 'arraybuffer'
    this.socket.onmessage = (event) => {
      if (typeof event.data !== 'string') return handlers.onAudio(event.data as ArrayBuffer)
      const message = JSON.parse(event.data)
      if (message.type === 'heard') handlers.onHeard(message.text)
      else if (message.type === 'audio_start') handlers.onAudioStart(message.mime)
      else if (message.type === 'reply') handlers.onReply(message)
      else if (message.type === 'error') handlers.onError(message.message)
    }
    this.socket.onclose = () => handlers.onClose()
  }

  get open(): boolean {
    return this.socket.readyState === WebSocket.OPEN
  }

  /** Wait until the connection is ready to carry a clip. */
  ready(): Promise<void> {
    if (this.open) return Promise.resolve()
    return new Promise((resolve, reject) => {
      this.socket.addEventListener('open', () => resolve(), { once: true })
      this.socket.addEventListener('error', () => reject(new Error('Voice is unavailable')), { once: true })
    })
  }

  send(clip: Blob): void {
    this.socket.send(clip)
  }

  /** Tell the server to stop speaking: the customer started talking. */
  interrupt(): void {
    if (this.open) this.socket.send(JSON.stringify({ type: 'interrupt' }))
  }

  close(): void {
    this.socket.close()
  }
}
