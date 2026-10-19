import { CLIP_RATE, downsample, encodeWav } from './wav'

const WORKLET = `
class Capture extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0][0]
    if (channel) this.port.postMessage(channel.slice(0))
    return true
  }
}
registerProcessor('capture', Capture)
`

export const MIN_CLIP_SECONDS = 0.4

/** Records the microphone and hands back one WAV clip. */
export class Recorder {
  private stream?: MediaStream
  private context?: AudioContext
  private chunks: Float32Array[] = []

  async start(): Promise<void> {
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    })
    const context = new AudioContext()
    this.context = context
    const url = URL.createObjectURL(new Blob([WORKLET], { type: 'text/javascript' }))
    await context.audioWorklet.addModule(url)
    URL.revokeObjectURL(url)
    const source = context.createMediaStreamSource(this.stream)
    const capture = new AudioWorkletNode(context, 'capture')
    capture.port.onmessage = (event: MessageEvent<Float32Array>) => this.chunks.push(event.data)
    // A node with no path to the speakers may never be run, so route it through a silent gain.
    const silent = context.createGain()
    silent.gain.value = 0
    source.connect(capture).connect(silent).connect(context.destination)
  }

  /** Stop and return the clip, or null if it was too short to be speech. */
  async stop(): Promise<Blob | null> {
    const rate = this.context?.sampleRate ?? CLIP_RATE
    this.release()
    const total = this.chunks.reduce((n, c) => n + c.length, 0)
    const all = new Float32Array(total)
    let offset = 0
    for (const chunk of this.chunks) {
      all.set(chunk, offset)
      offset += chunk.length
    }
    this.chunks = []
    if (total / rate < MIN_CLIP_SECONDS) return null
    return encodeWav(downsample(all, rate, CLIP_RATE), Math.min(rate, CLIP_RATE))
  }

  cancel(): void {
    this.release()
    this.chunks = []
  }

  private release(): void {
    this.stream?.getTracks().forEach((t) => t.stop())
    void this.context?.close()
    this.stream = undefined
    this.context = undefined
  }
}
