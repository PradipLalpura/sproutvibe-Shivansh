import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import en from './locales/en.json'
import hi from './locales/hi.json'
import gu from './locales/gu.json'

export const LANG_KEY = 'sprout_lang'
export const LANGS = ['en', 'hi', 'gu']

/** Keep only en/hi/gu — everything else falls back to English. */
export function normalizeLang(value) {
  const v = String(value || '').toLowerCase().split(/[-_]/)[0]
  return LANGS.includes(v) ? v : 'en'
}

/** Read the stored language without touching React (safe for api modules). */
export function getStoredLanguage() {
  try {
    return normalizeLang(localStorage.getItem(LANG_KEY))
  } catch {
    return 'en'
  }
}

function detectInitialLanguage() {
  try {
    const stored = localStorage.getItem(LANG_KEY)
    if (stored) return normalizeLang(stored)
  } catch {
    // storage unavailable — fall through to navigator
  }
  try {
    return normalizeLang(navigator.language)
  } catch {
    return 'en'
  }
}

i18n
  .use(initReactI18next)
  .init({
    resources: { en: { translation: en }, hi: { translation: hi }, gu: { translation: gu } },
    lng: detectInitialLanguage(),
    fallbackLng: 'en',
    interpolation: { escapeValue: false },
  })

/** Switch language everywhere: i18next + localStorage + <html lang>. */
export function applyLanguage(lang) {
  const next = normalizeLang(lang)
  if (i18n.language !== next) void i18n.changeLanguage(next)
  try {
    localStorage.setItem(LANG_KEY, next)
  } catch {
    // private mode — UI still switches for this session
  }
  try {
    document.documentElement.lang = next
  } catch {
    // non-DOM environment (tests import this module too)
  }
  return next
}

applyLanguage(i18n.language)

export default i18n
