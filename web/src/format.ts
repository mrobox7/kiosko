/** Prices from the server are rupees. */
export const rupees = (amount: number) => `₹${amount.toFixed(2)}`

/** A dish name as a person says it: the menu data carries trademark signs and footnote stars. */
export const plainName = (name: string) => name.replace(/[®*]/g, '').replace(/\s+/g, ' ').trim()
