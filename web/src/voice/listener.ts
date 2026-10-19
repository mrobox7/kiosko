import { MicVAD } from '@ricky0123/vad-web'
import { CLIP_RATE, encodeWav } from './wav'

export interface ListenerHandlers {
  /** The customer started talking: real speech, not a click or a cough. */
  onSpeechStart: () => void
  /** The customer stopped; `clip` is what they said. */
  onSpeechEnd: (clip: Blob) => void
  /** Something sounded like speech but was too short to be. */
  onMisfire: () => void
}

export interface Listener {
  stop: () => Promise<void>
}

/** Listens to the microphone continuously and reports where each utterance starts and ends. */
export async function startListening(handlers: ListenerHandlers): Promise<Listener> {
  const vad = await MicVAD.new({
    model: 'v5',
    baseAssetPath: '/vad/',
    onnxWASMBasePath: '/vad/',
    getStream: () =>
      navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      }),
    // Tuned for conversation: a sentence ends after 1.2 s of quiet, so a thinking pause does not
    // end it (the library's default of 1.4 s feels slow). Speech counts as real only after 0.3 s,
    // so a cough or an echo blip cannot cut the agent off.
    positiveSpeechThreshold: 0.5,
    negativeSpeechThreshold: 0.35,
    redemptionMs: 1200,
    minSpeechMs: 300,
    preSpeechPadMs: 400,
    onSpeechRealStart: handlers.onSpeechStart,
    onSpeechEnd: (audio: Float32Array) => handlers.onSpeechEnd(encodeWav(audio, CLIP_RATE)),
    onVADMisfire: handlers.onMisfire,
  })
  await vad.start()
  return { stop: () => vad.destroy() }
}
