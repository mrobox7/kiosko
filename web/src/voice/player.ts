/** Plays audio chunks while they are still arriving. Uses MediaSource where the browser has it
 * (the chunks are mp3); otherwise it keeps them and plays once the reply is complete. */
export class StreamPlayer {
  private readonly audio = new Audio()
  private readonly source?: MediaSource
  private buffer?: SourceBuffer
  private queue: ArrayBuffer[] = []
  private parts: ArrayBuffer[] = []
  private finished = false
  private stopped = false
  private url = ''
  private readonly mime: string
  private readonly onEnded: () => void

  constructor(mime: string, onEnded: () => void) {
    this.mime = mime
    this.onEnded = onEnded
    this.audio.addEventListener('ended', () => this.done())
    if (typeof MediaSource !== 'undefined' && MediaSource.isTypeSupported(mime)) {
      this.source = new MediaSource()
      this.url = URL.createObjectURL(this.source)
      this.audio.src = this.url
      this.source.addEventListener('sourceopen', () => {
        if (!this.source || this.buffer) return
        this.buffer = this.source.addSourceBuffer(mime)
        this.buffer.addEventListener('updateend', () => this.pump())
        this.pump()
      })
      void this.audio.play().catch(() => undefined)
    }
  }

  feed(chunk: ArrayBuffer): void {
    if (this.stopped) return
    if (this.source) {
      this.queue.push(chunk)
      this.pump()
    } else {
      this.parts.push(chunk)
    }
  }

  /** No more chunks are coming. */
  end(): void {
    if (this.stopped) return
    this.finished = true
    if (this.source) {
      this.pump()
    } else {
      this.url = URL.createObjectURL(new Blob(this.parts, { type: this.mime }))
      this.audio.src = this.url
      void this.audio.play().catch(() => this.done())
    }
  }

  stop(): void {
    this.stopped = true
    this.audio.pause()
    this.release()
  }

  private pump(): void {
    if (!this.buffer || this.buffer.updating || !this.source) return
    const next = this.queue.shift()
    if (next) {
      this.buffer.appendBuffer(next)
    } else if (this.finished && this.source.readyState === 'open') {
      this.source.endOfStream()
    }
  }

  private done(): void {
    if (this.stopped) return
    this.stopped = true
    this.release()
    this.onEnded()
  }

  private release(): void {
    if (this.url) URL.revokeObjectURL(this.url)
    this.url = ''
  }
}
