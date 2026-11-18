import type { ChatMessage } from '../../types'
import { CloseIcon } from '../../ui/Icons'
import { IconButton } from '../../ui/IconButton'
import { Sheet } from '../../ui/Sheet'
import { Avatar } from './Avatar'
import { Composer, type VoiceControls } from './Composer'
import { MessageList } from './MessageList'

/** Kiosko, the assistant: ask about the menu or say what you want, by typing or by voice.
 * It works on the same order as the touch screen. */
export function AssistantPanel({
  open,
  messages,
  customerName,
  busy,
  error,
  voice,
  onSend,
  onClose,
}: {
  open: boolean
  messages: ChatMessage[]
  customerName: string
  busy: boolean
  error: string
  voice?: VoiceControls
  onSend: (text: string) => void
  onClose: () => void
}) {
  return (
    <Sheet open={open} label="Ask Kiosko" onClose={onClose}>
      <div className="flex h-[85dvh] flex-col landscape:h-[80dvh]">
        <header className="flex items-center gap-3 border-b border-line px-4 py-3">
          <Avatar who="assistant" />
          <div className="flex-1 leading-tight">
            <h2 className="text-lg font-bold">Ask Kiosko</h2>
            <p className="text-sm text-muted">Your order is the same as on the screen</p>
          </div>
          <IconButton label="Close assistant" onClick={onClose}>
            <CloseIcon />
          </IconButton>
        </header>
        <MessageList messages={messages} customerName={customerName} busy={busy} />
        {error && <p className="mx-4 mb-2 rounded-xl bg-promo/10 px-4 py-2 text-sm text-promo md:mx-6">{error}</p>}
        <Composer busy={busy} voice={voice} onSend={onSend} />
      </div>
    </Sheet>
  )
}
