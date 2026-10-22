import { rupees } from '../../format'
import { countIn, type Choices } from '../../lib/choices'
import type { OptionGroup } from '../../types'
import { ChoiceCard } from '../../ui/ChoiceCard'
import { Stepper } from '../../ui/Stepper'

function rule(group: OptionGroup) {
  if (group.max_select === 1) return group.min_select === 1 ? 'Choose 1' : 'Choose 1 if you like'
  if (group.min_select === group.max_select) return `Choose ${group.max_select}`
  return `Choose up to ${group.max_select}`
}

const extra = (delta: number) => (delta > 0 ? `+${rupees(delta)}` : undefined)

/** One question on a dish. A single choice is a set of cards; several are counters. */
export function OptionGroupPicker({
  group,
  choices,
  onPick,
}: {
  group: OptionGroup
  choices: Choices
  onPick: (group: OptionGroup, optionId: number, by: 1 | -1) => void
}) {
  const picked = choices.picks[group.id] ?? {}
  const left = group.max_select - countIn(choices, group)

  return (
    <fieldset className="space-y-3">
      <legend className="flex flex-wrap items-baseline gap-x-3">
        <span className="text-lg font-bold">{group.name}</span>
        <span className="text-sm text-muted">{rule(group)}</span>
        {group.min_select > 0 && <span className="rounded-full bg-accent-soft px-2 py-0.5 text-xs font-bold">Required</span>}
      </legend>
      {group.max_select === 1 ? (
        <div role="radiogroup" aria-label={group.name} className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {group.options.map((option) => {
            const on = picked[option.id] === 1
            return (
              <ChoiceCard
                key={option.id}
                title={option.name}
                note={extra(option.price_delta)}
                selected={on}
                onClick={() => onPick(group, option.id, on ? -1 : 1)}
              />
            )
          })}
        </div>
      ) : (
        <ul className="space-y-2">
          {group.options.map((option) => {
            const qty = picked[option.id] ?? 0
            return (
              <li key={option.id} className="flex items-center justify-between gap-3 rounded-2xl bg-tile px-4 py-2">
                <span className="font-semibold">
                  {option.name} <span className="text-sm font-normal text-muted">{extra(option.price_delta)}</span>
                </span>
                <Stepper
                  value={qty}
                  min={0}
                  max={qty + left}
                  label={option.name}
                  onChange={(next) => onPick(group, option.id, next > qty ? 1 : -1)}
                />
              </li>
            )
          })}
        </ul>
      )}
    </fieldset>
  )
}
