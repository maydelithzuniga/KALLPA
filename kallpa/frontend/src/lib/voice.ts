// Grabación con MediaRecorder y, como respaldo, reconocimiento de voz del navegador.
export function pickMime(): string {
  const cands = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4', 'audio/aac']
  for (const c of cands) {
    try { if (typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(c)) return c } catch { /* */ }
  }
  return ''
}

export function extFor(mime: string): string {
  if (mime.includes('ogg')) return '.ogg'
  if (mime.includes('mp4') || mime.includes('aac')) return '.m4a'
  return '.webm'
}

export class Recorder {
  private rec?: MediaRecorder
  private chunks: Blob[] = []
  private stream?: MediaStream
  mime = ''

  static supported(): boolean {
    return typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== 'undefined'
  }

  async start(): Promise<void> {
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } })
    this.mime = pickMime()
    this.chunks = []
    this.rec = new MediaRecorder(this.stream, this.mime ? { mimeType: this.mime } : undefined)
    this.rec.ondataavailable = (e) => { if (e.data.size) this.chunks.push(e.data) }
    this.rec.start()
  }

  stop(): Promise<Blob> {
    return new Promise((resolve) => {
      if (!this.rec) return resolve(new Blob())
      this.rec.onstop = () => {
        this.stream?.getTracks().forEach((t) => t.stop())
        resolve(new Blob(this.chunks, { type: this.mime || 'audio/webm' }))
      }
      this.rec.stop()
    })
  }

  cancel() {
    try { this.rec?.stop() } catch { /* */ }
    this.stream?.getTracks().forEach((t) => t.stop())
  }
}

type SR = { lang: string; interimResults: boolean; maxAlternatives: number; start(): void; stop(): void;
  onresult: ((e: { results: { 0: { transcript: string } }[] }) => void) | null; onerror: ((e: unknown) => void) | null; onend: (() => void) | null }

export function browserRecognizer(): SR | null {
  const w = window as unknown as { SpeechRecognition?: new () => SR; webkitSpeechRecognition?: new () => SR }
  const C = w.SpeechRecognition || w.webkitSpeechRecognition
  if (!C) return null
  const r = new C()
  r.lang = 'es-PE'
  r.interimResults = false
  r.maxAlternatives = 1
  return r
}

export function speak(text: string) {
  try {
    if (!('speechSynthesis' in window)) return
    window.speechSynthesis.cancel()
    const u = new SpeechSynthesisUtterance(text.replace(/S\/ ?/g, '').replace(/(\d),(\d{3})/g, '$1$2') )
    u.lang = 'es-PE'
    u.rate = 1.05
    const v = window.speechSynthesis.getVoices().find((x) => x.lang.startsWith('es'))
    if (v) u.voice = v
    window.speechSynthesis.speak(u)
  } catch { /* */ }
}
