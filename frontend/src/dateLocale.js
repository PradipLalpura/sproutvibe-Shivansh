import { hi, gu } from 'date-fns/locale'

/** date-fns locale for the current app language (undefined = default English). */
export function dateLocaleFor(lang) {
  if (lang === 'hi') return hi
  if (lang === 'gu') return gu
  return undefined
}
