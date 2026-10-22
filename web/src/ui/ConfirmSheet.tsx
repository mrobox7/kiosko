import { Button } from './Button'
import { Sheet } from './Sheet'

/** A question with two answers, for the taps that cannot be taken back. */
export function ConfirmSheet({
  open,
  title,
  body,
  confirmLabel,
  cancelLabel = 'Go back',
  busy = false,
  onConfirm,
  onCancel,
}: {
  open: boolean
  title: string
  body: string
  confirmLabel: string
  cancelLabel?: string
  busy?: boolean
  onConfirm: () => void
  onCancel: () => void
}) {
  return (
    <Sheet open={open} label={title} onClose={onCancel}>
      <div className="flex flex-col gap-6 p-8 text-center landscape:max-w-xl landscape:self-center">
        <div className="space-y-2">
          <h2 className="text-3xl font-black">{title}</h2>
          <p className="text-lg text-muted">{body}</p>
        </div>
        <div className="flex flex-col gap-3 landscape:flex-row-reverse">
          <Button size="lg" className="flex-1" disabled={busy} onClick={onConfirm}>
            {confirmLabel}
          </Button>
          <Button size="lg" look="soft" className="flex-1" disabled={busy} onClick={onCancel}>
            {cancelLabel}
          </Button>
        </div>
      </div>
    </Sheet>
  )
}
