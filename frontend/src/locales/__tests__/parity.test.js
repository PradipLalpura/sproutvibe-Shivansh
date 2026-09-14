import { describe, it, expect } from 'vitest'
import en from '../en.json'
import hi from '../hi.json'
import gu from '../gu.json'
import i18n, { normalizeLang, getStoredLanguage, applyLanguage, LANGS } from '../../i18n'

function leafKeys(obj, prefix = '') {
  const keys = []
  for (const [k, v] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${k}` : k
    if (v !== null && typeof v === 'object' && !Array.isArray(v)) {
      keys.push(...leafKeys(v, path))
    } else {
      keys.push(path)
    }
  }
  return keys.sort()
}

function getPath(obj, path) {
  return path.split('.').reduce((o, k) => o?.[k], obj)
}

describe('locale parity (en keys ⊆ hi, gu)', () => {
  const enKeys = leafKeys(en)

  it.each(['hi', 'gu'])('%s has exactly the same keys as en', (lng) => {
    const dict = lng === 'hi' ? hi : gu
    expect(leafKeys(dict)).toEqual(enKeys)
  })

  it.each(['hi', 'gu'])('%s has no empty translations', (lng) => {
    const dict = lng === 'hi' ? hi : gu
    const empties = enKeys.filter((k) => {
      const v = getPath(dict, k)
      return typeof v !== 'string' || v.trim() === ''
    })
    expect(empties).toEqual([])
  })

  it('every en key resolves in hi/gu with no missing-key fallback', async () => {
    for (const lng of ['hi', 'gu']) {
      await i18n.changeLanguage(lng)
      const missing = enKeys.filter((k) => i18n.t(k) === k)
      expect(missing).toEqual([])
    }
    await i18n.changeLanguage('en')
  })

  it('interpolation + plurals work in all languages', async () => {
    for (const lng of ['en', 'hi', 'gu']) {
      await i18n.changeLanguage(lng)
      expect(i18n.t('dashboard.hello', { name: 'Shiv' })).toContain('Shiv')
      expect(i18n.t('plants.addPlantTasks', { count: 1 })).toContain('1')
      expect(i18n.t('plants.addPlantTasks', { count: 3 })).toContain('3')
    }
    await i18n.changeLanguage('en')
  })
})

describe('language detection + fallback', () => {
  it('normalizes variants and rejects unknown languages', () => {
    expect(normalizeLang('hi')).toBe('hi')
    expect(normalizeLang('gu')).toBe('gu')
    expect(normalizeLang('HI')).toBe('hi')
    expect(normalizeLang('hi-IN')).toBe('hi')
    expect(normalizeLang('gu_IN')).toBe('gu')
    expect(normalizeLang('fr')).toBe('en')
    expect(normalizeLang('')).toBe('en')
    expect(normalizeLang(null)).toBe('en')
    expect(normalizeLang(undefined)).toBe('en')
  })

  it('supports exactly en/hi/gu', () => {
    expect(LANGS).toEqual(['en', 'hi', 'gu'])
  })

  it('reads stored language, defaults to en', () => {
    localStorage.clear()
    expect(getStoredLanguage()).toBe('en')
    localStorage.setItem('sprout_lang', 'gu')
    expect(getStoredLanguage()).toBe('gu')
    localStorage.setItem('sprout_lang', 'fr')
    expect(getStoredLanguage()).toBe('en')
  })

  it('applyLanguage switches i18n, persists, and sets <html lang>', async () => {
    applyLanguage('hi')
    expect(i18n.language).toBe('hi')
    expect(localStorage.getItem('sprout_lang')).toBe('hi')
    expect(document.documentElement.lang).toBe('hi')
    expect(i18n.t('nav.home')).toBe('होम')
    expect(i18n.t('dashboard.today')).toBe('आज')
    applyLanguage('gu')
    expect(i18n.t('nav.home')).toBe('હોમ')
    applyLanguage('en')
    expect(i18n.t('nav.home')).toBe('Home')
  })
})
