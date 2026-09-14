import { useState, useEffect } from 'react'
import { getSettings, saveSettings } from '../api/settings'
import { applyLanguage, getStoredLanguage, LANGS } from '../i18n'

/** App language: localStorage + server Setting.language, mirroring useTheme. */
export function useLanguage() {
  const [language, setLanguageState] = useState(() => getStoredLanguage())

  useEffect(() => {
    const syncFromServer = () => {
      getSettings().then(s => {
        const serverLang = (s.language || '').toLowerCase()
        if (LANGS.includes(serverLang) && serverLang !== getStoredLanguage()) {
          setLanguageState(applyLanguage(serverLang))
        }
      }).catch(() => {})
    }

    syncFromServer()
    window.addEventListener('auth:login', syncFromServer)
    return () => window.removeEventListener('auth:login', syncFromServer)
  }, []) // once on mount

  const setLanguage = (next) => {
    setLanguageState(applyLanguage(next))
    saveSettings({ language: next }).catch(() => {})
  }

  return { language, setLanguage }
}
