import { AnimatePresence, motion } from 'motion/react'
import { useState } from 'react'
import { plainName, rupees } from '../../format'
import {
  defaultChoices,
  describe,
  groupsFor,
  pick,
  setMeal,
  toRequest,
  unanswered,
  unitPrice,
  type Choices,
} from '../../lib/choices'
import type { Dish, LineRequest } from '../../types'
import { Button } from '../../ui/Button'
import { DishImage } from '../../ui/DishImage'
import { ChevronLeftIcon, CloseIcon } from '../../ui/Icons'
import { Sheet } from '../../ui/Sheet'
import { Stepper } from '../../ui/Stepper'
import { VegMark } from '../../ui/VegMark'
import { DishFacts } from './DishFacts'
import { MealChoice } from './MealChoice'
import { MealStrip } from './MealStrip'
import { OptionGroupPicker } from './OptionGroupPicker'

type Step = 'summary' | 'customize'

const slide = { type: 'spring', stiffness: 380, damping: 36 } as const

/** A dish in two steps, as in the reference: the summary (picture, price, how many, Customize or
 * Done), and Customize (the meal and the questions). The picture is shared, so it shrinks and
 * grows between the steps. */
function ItemForm({
  dish,
  busy,
  onAdd,
  onClose,
}: {
  dish: Dish
  busy: boolean
  onAdd: (line: LineRequest) => void
  onClose: () => void
}) {
  const [choices, setChoices] = useState<Choices>(() => defaultChoices(dish))
  const [step, setStep] = useState<Step>('summary')
  const [info, setInfo] = useState(false)
  const missing = unanswered(dish, choices)
  const kcal = Number(dish.nutrition.calories_kcal)
  const chosen = describe(dish, choices)

  function openMeal() {
    if (choices.mealSize === null) setChoices((c) => setMeal(dish, c, dish.meal_offers[0].size))
    setStep('customize')
  }

  const name = (
    <span className="flex items-center justify-center gap-2">
      <VegMark veg={dish.veg} />
      <span className="text-xl font-bold">{plainName(dish.name)}</span>
    </span>
  )

  return (
    <div className="relative flex h-[min(46rem,90dvh)] flex-col">
      {/* The tab cut into the top of the sheet: close on the summary, back on Customize. */}
      <button
        type="button"
        aria-label={step === 'summary' ? 'Close' : 'Back to the dish'}
        onClick={step === 'summary' ? onClose : () => setStep('summary')}
        className="absolute top-0 left-1/2 z-10 flex h-14 w-24 -translate-x-1/2 items-center justify-center rounded-b-3xl bg-tile"
      >
        {step === 'summary' ? <CloseIcon /> : <ChevronLeftIcon />}
      </button>
      {step === 'customize' && (
        <button
          type="button"
          aria-label="Calories and allergens"
          aria-pressed={info}
          onClick={() => setInfo((on) => !on)}
          className="absolute top-5 right-5 z-10 flex h-9 w-9 items-center justify-center rounded-full border border-line text-sm font-bold"
        >
          i
        </button>
      )}

      <AnimatePresence mode="popLayout" initial={false}>
        {step === 'summary' ? (
          <motion.div
            key="summary"
            className="flex min-h-0 flex-1 flex-col items-center gap-3 px-6 pt-20 pb-6 text-center"
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 24 }}
            transition={slide}
          >
            <motion.div layoutId="dish-picture" className="h-44 w-full">
              <DishImage src={dish.image_url} name={dish.name} className="h-full w-full" />
            </motion.div>
            {name}
            <p className="text-xl font-semibold text-accent">{rupees(unitPrice(dish, choices))}</p>
            {chosen.length > 0 && <p className="max-w-sm text-sm text-muted">{chosen.join(' · ')}</p>}
            <Stepper
              value={choices.quantity}
              min={1}
              max={20}
              label="quantity"
              onChange={(quantity) => setChoices((c) => ({ ...c, quantity }))}
            />
            <div className="mt-2 flex items-center gap-3">
              <Button look="soft" size="lg" onClick={() => setStep('customize')}>
                Customize
              </Button>
              <Button
                size="lg"
                disabled={busy}
                onClick={() => (missing.length > 0 ? setStep('customize') : onAdd(toRequest(dish, choices)))}
              >
                {missing.length > 0 ? 'Choose options' : 'Done'}
              </Button>
            </div>
            {dish.meal_offers.length > 0 && (
              <div className="mt-auto w-full">
                <MealStrip dish={dish} chosen={choices.mealSize} onOpen={openMeal} />
              </div>
            )}
          </motion.div>
        ) : (
          <motion.div
            key="customize"
            className="flex min-h-0 flex-1 flex-col pt-16"
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 24 }}
            transition={slide}
          >
            <header className="flex flex-col items-center gap-1 px-6 text-center">
              <motion.div layoutId="dish-picture" className="h-20 w-full">
                <DishImage src={dish.image_url} name={dish.name} className="h-full w-full" />
              </motion.div>
              {name}
              {Number.isFinite(kcal) && kcal > 0 && <p className="text-xs text-muted">{Math.round(kcal)} Cal.</p>}
              <p className="text-lg font-semibold text-accent">{rupees(unitPrice(dish, choices))}</p>
            </header>
            {info && (
              <div className="mx-6 mt-2 rounded-2xl bg-tile p-4">
                <DishFacts dish={dish} />
              </div>
            )}
            <div className="min-h-0 flex-1 space-y-8 overflow-y-auto p-6">
              {dish.meal_offers.length > 0 && (
                <MealChoice dish={dish} size={choices.mealSize} onChange={(size) => setChoices((c) => setMeal(dish, c, size))} />
              )}
              {groupsFor(dish, choices).map((group) => (
                <OptionGroupPicker
                  key={group.id}
                  group={group}
                  choices={choices}
                  onPick={(g, optionId, by) => setChoices((c) => pick(c, g, optionId, by))}
                />
              ))}
            </div>
            <footer className="flex justify-center p-4">
              <Button size="lg" className="min-w-56" disabled={missing.length > 0} onClick={() => setStep('summary')}>
                {missing.length > 0 ? `Choose ${missing[0].name.toLowerCase()}` : 'Apply'}
              </Button>
            </footer>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

/** The sheet for one dish. The form starts fresh every time the sheet opens (`opened` changes). */
export function ItemSheet({
  dish,
  opened,
  open,
  busy,
  onAdd,
  onClose,
}: {
  dish: Dish | null
  opened: number
  open: boolean
  busy: boolean
  onAdd: (line: LineRequest) => void
  onClose: () => void
}) {
  return (
    <Sheet open={open} label={dish ? plainName(dish.name) : 'Dish'} narrow onClose={onClose}>
      {dish && <ItemForm key={`${dish.id}-${opened}`} dish={dish} busy={busy} onAdd={onAdd} onClose={onClose} />}
    </Sheet>
  )
}
