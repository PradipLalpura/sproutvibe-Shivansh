import { useState, useEffect } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { createPlant, searchSpecies, getSpecies, getWikiDescription, getAiCare } from '../api/plants'
import { createSchedule } from '../api/watering'
import { resolveMediaUrl } from '../api/client'

function useDebounce(value, delay) {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(t)
  }, [value, delay])
  return debounced
}

const TASK_ICONS = { water: '💧', fertilize: '🌱', mist: '💨', repot: '🪴' }

const SOURCE_CONFIG = {
  perenual:    { label: 'Perenual',    cls: 'bg-blue-50 text-blue-500 dark:bg-blue-900/30 dark:text-blue-400' },
  floracodex:  { label: 'FloraCodex',  cls: 'bg-purple-50 text-purple-500 dark:bg-purple-900/30 dark:text-purple-400' },
  inaturalist: { label: 'iNaturalist', cls: 'bg-teal-50 text-teal-600 dark:bg-teal-900/30 dark:text-teal-400' },
  indian_catalogue: { badgeKey: 'plants.indianBadge', cls: 'bg-orange-50 text-orange-600 dark:bg-orange-900/30 dark:text-orange-400' },
}

const CATEGORY_OPTIONS = ['', 'vegetable', 'fruit', 'flower', 'herb_medicinal', 'spice', 'grain_pulse', 'tree', 'succulent', 'other']

// Display name first (Indian name when available), Latin kept small.
function displayOf(r) {
  return r.display_name || r.common_name || r.scientific_name
}

function indianLine(r) {
  if (!r.indian_names) return null
  const { hi, gu } = r.indian_names
  if (!hi && !gu) return null
  return [hi, gu].filter(Boolean).join(' · ')
}

// Suggested schedules based on species data — extend as needed
function buildSuggestedSchedules(species) {
  const schedules = []
  if (species.watering_days) {
    schedules.push({ task_type: 'water', frequency_days: species.watering_days, label: `every ${species.watering_days} days` })
  }
  return schedules
}

export default function AddPlantPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [form, setForm] = useState({ name: '', species: '', location: '', notes: '', photo_url: null })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // Species search
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [searching, setSearching] = useState(false)
  const [loadingDetails, setLoadingDetails] = useState(false)
  const [selected, setSelected] = useState(null)      // full species detail
  const [apiUnavailable, setApiUnavailable] = useState(false)
  const [schedules, setSchedules] = useState([])       // suggested care tasks
  const [category, setCategory] = useState('')
  const [kind, setKind] = useState('')
  const debouncedQuery = useDebounce(query, 400)

  useEffect(() => {
    if (!debouncedQuery.trim() || apiUnavailable) { setResults([]); return }
    setSearching(true)
    searchSpecies(debouncedQuery, { category: category || undefined, kind: kind || undefined })
      .then(setResults)
      .catch((err) => {
        if (err.response?.status === 503) setApiUnavailable(true)
        setResults([])
      })
      .finally(() => setSearching(false))
  }, [debouncedQuery, category, kind])

  const handleSelect = async (preview) => {
    setResults([])
    setQuery('')
    setLoadingDetails(true)
    try {
      // Try Perenual detail (has care data + description for paid plans)
      let species
      try {
        species = await getSpecies(preview.id, preview.source)
      } catch {
        // API failed (rate limit, key missing, etc.) — fall back to Wikipedia for description only
        const wiki = await getWikiDescription(preview.scientific_name).catch(() => ({}))
        species = { ...preview, description: wiki.description || null, thumbnail: wiki.thumbnail || preview.thumbnail }
      }
      setSelected(species)

      // Build schedules: start with anything Perenual gave us, then fill in with AI
      let tasks = buildSuggestedSchedules(species)
      if (tasks.length === 0) {
        // Try AI care recommendations as fallback
        try {
          const ai = await getAiCare(species.common_name, species.scientific_name)
          tasks = ai.tasks.map(t => ({
            task_type: t.task_type,
            frequency_days: t.frequency_days,
            label: `every ${t.frequency_days} day${t.frequency_days !== 1 ? 's' : ''}`,
            notes: t.notes,
          }))
          // If AI also gave a summary and we have no description yet, use it
          if (!species.description && ai.care_summary) {
            species = { ...species, description: ai.care_summary }
          }
        } catch {
          // AI not configured or failed — schedules stay empty, user can add manually
        }
      }
      setSchedules(tasks)

      setForm((f) => ({
        ...f,
        name: f.name || displayOf(species),
        species: species.scientific_name || species.common_name,
        notes: f.notes || species.description || '',
        photo_url: f.photo_url || species.thumbnail || null,
      }))
    } catch {
      setSelected(preview)
      setForm((f) => ({
        ...f,
        name: f.name || displayOf(preview),
        species: preview.scientific_name || preview.common_name,
        photo_url: f.photo_url || preview.thumbnail || null,
      }))
    } finally {
      setLoadingDetails(false)
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const plant = await createPlant(form)
      // Auto-create suggested care schedules
      await Promise.all(schedules.map(s => createSchedule(plant.id, {
        task_type: s.task_type,
        frequency_days: s.frequency_days,
      }).catch(() => null))) // don't block plant creation if a schedule fails
      navigate(`/plants/${plant.id}`)
    } catch (err) {
      setError(err.response?.data?.detail || t('plants.createFailed'))
    } finally {
      setLoading(false)
    }
  }

  const sourceBadge = (source) => {
    const src = SOURCE_CONFIG[source] || { label: source, cls: 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400' }
    return (
      <span className={`shrink-0 text-xs px-1.5 py-0.5 rounded font-medium ${src.cls}`}>{src.badgeKey ? t(src.badgeKey) : src.label}</span>
    )
  }

  const categoryLabel = (slug) => (slug ? t(`plants.cat.${slug}`, { defaultValue: slug.replace('_', ' ') }) : '')

  return (
    <div className="p-4 md:p-8 max-w-2xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <Link to="/" className="text-gray-400 hover:text-gray-600 text-lg">←</Link>
        <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100">{t('plants.addTitle')}</h1>
      </div>

      {/* Species search */}
      <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 p-5 mb-6">
        <h2 className="font-semibold text-gray-700 dark:text-gray-300 mb-1">{t('plants.searchTitle')}</h2>
        <p className="text-xs text-gray-400 dark:text-gray-500 mb-3">{t('plants.searchSub')}</p>

        {apiUnavailable ? (
          <div className="text-sm text-amber-700 bg-amber-50 dark:bg-amber-900/20 rounded-lg p-3 flex items-center justify-between gap-3">
            <span>{t('plants.noDb')}</span>
            <Link to="/settings" className="font-medium text-amber-700 underline whitespace-nowrap">{t('plants.goSettings')}</Link>
          </div>
        ) : (
          <div className="relative">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t('plants.searchPlaceholder')}
              className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-green-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500"
            />
            {(searching || loadingDetails) && (
              <span className="absolute right-3 top-2.5 text-gray-400 text-sm">
                {loadingDetails ? t('common.loadingDetails') : t('common.searching')}
              </span>
            )}
            <div className="flex gap-2 mt-2">
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="text-xs border border-gray-300 dark:border-gray-600 rounded-lg px-2 py-1.5 bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300"
                title={t('plants.searchTitle')}
              >
                {CATEGORY_OPTIONS.map((c) => (
                  <option key={c} value={c}>{c === '' ? t('plants.allCategories') : categoryLabel(c)}</option>
                ))}
              </select>
              <select
                value={kind}
                onChange={(e) => setKind(e.target.value)}
                className="text-xs border border-gray-300 dark:border-gray-600 rounded-lg px-2 py-1.5 bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300"
                title={t('plants.species')}
              >
                <option value="">{t('plants.plantAndSeed')}</option>
                <option value="plant">{t('plants.kindPlant')}</option>
                <option value="seed">{t('plants.kindSeed')}</option>
              </select>
              {(category || kind) && (
                <button type="button" onClick={() => { setCategory(''); setKind('') }}
                  className="text-xs text-gray-400 hover:text-gray-600 underline">{t('common.clear')}</button>
              )}
            </div>
            {results.length > 0 && (
              <div className="absolute z-20 w-full mt-1 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl shadow-lg overflow-hidden">
                {results.map((r) => (
                  <button
                    key={r.id}
                    type="button"
                    onClick={() => handleSelect(r)}
                    className="w-full flex items-center gap-3 px-4 py-3 hover:bg-green-50 dark:hover:bg-green-900/20 text-left transition-colors"
                  >
                    {r.thumbnail ? (
                      <img src={r.thumbnail} className="w-10 h-10 rounded-lg object-cover shrink-0" />
                    ) : (
                      <div className="w-10 h-10 rounded-lg bg-green-100 dark:bg-green-900/30 flex items-center justify-center shrink-0 text-lg">🪴</div>
                    )}
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <p className="font-medium text-gray-800 dark:text-gray-100 text-sm truncate">{displayOf(r)}</p>
                        {sourceBadge(r.source)}
                        {r.kind === 'seed' && (
                          <span className="shrink-0 text-xs px-1.5 py-0.5 rounded font-medium bg-amber-50 text-amber-600 dark:bg-amber-900/30 dark:text-amber-400">{t('plants.seedBadge')}</span>
                        )}
                      </div>
                      {indianLine(r) && (
                        <p className="text-xs text-gray-500 dark:text-gray-400 truncate">{indianLine(r)}</p>
                      )}
                      <p className="text-xs text-gray-400 dark:text-gray-500 italic truncate">
                        {r.scientific_name}{r.category ? ` · ${categoryLabel(r.category)}` : ''}
                      </p>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Selected species card */}
        {selected && (
          <div className="mt-4 bg-green-50 dark:bg-green-900/20 rounded-xl p-4">
            <div className="flex gap-4 mb-3">
              {selected.thumbnail && (
                <img src={selected.thumbnail} className="w-16 h-16 rounded-xl object-cover shrink-0" />
              )}
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <p className="font-semibold text-gray-800 dark:text-gray-100">{displayOf(selected)}</p>
                  {selected.kind === 'seed' && (
                    <span className="text-xs px-1.5 py-0.5 rounded font-medium bg-amber-50 text-amber-600 dark:bg-amber-900/30 dark:text-amber-400">{t('plants.seedSowNote')}</span>
                  )}
                  {selected.category && (
                    <span className="text-xs px-1.5 py-0.5 rounded font-medium bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400">{categoryLabel(selected.category)}</span>
                  )}
                </div>
                {indianLine(selected) && (
                  <p className="text-sm text-gray-500 dark:text-gray-400">{indianLine(selected)}</p>
                )}
                <p className="text-sm text-gray-500 dark:text-gray-400 italic">{selected.scientific_name}</p>
                {selected.common_name && selected.common_name !== displayOf(selected) && (
                  <p className="text-xs text-gray-400 dark:text-gray-500">{t('plants.englishName', { name: selected.common_name })}</p>
                )}
              </div>
              <button type="button" onClick={() => { setSelected(null); setSchedules([]); setForm(f => ({ ...f, photo_url: null })) }}
                className="text-gray-300 dark:text-gray-600 hover:text-gray-500 self-start text-lg leading-none">×</button>
            </div>

            {selected.description && (
              <p className="text-sm text-gray-600 dark:text-gray-300 mb-3 leading-relaxed">{selected.description}</p>
            )}

            {schedules.length > 0 && (
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">{t('plants.careAuto')}</p>
                  <span className="text-xs bg-purple-50 dark:bg-purple-900/20 text-purple-500 dark:text-purple-400 border border-purple-200 dark:border-purple-800 px-2 py-0.5 rounded-full">{t('plants.aiBadge')}</span>
                </div>
                <div className="flex flex-wrap gap-2">
                  {schedules.map((s) => (
                    <span key={s.task_type} className="inline-flex items-center gap-1.5 bg-white dark:bg-gray-700 border border-green-200 dark:border-green-800 text-green-700 dark:text-green-400 text-xs px-3 py-1.5 rounded-full font-medium">
                      {TASK_ICONS[s.task_type]} {s.task_type} {s.label}
                    </span>
                  ))}
                </div>
                <p className="text-xs text-gray-400 dark:text-gray-500 mt-2">{t('plants.careNote')}</p>
              </div>
            )}

            {schedules.length === 0 && !selected.description && (
              <p className="text-xs text-gray-400 dark:text-gray-500 italic">{t('plants.noCareData')}</p>
            )}
          </div>
        )}
      </div>

      {/* Plant form */}
      <form onSubmit={handleSubmit} className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 p-5 space-y-4">
        <h2 className="font-semibold text-gray-700 dark:text-gray-300">{t('plants.addTitle')}</h2>

        {/* Photo preview from species database */}
        {form.photo_url && (
          <div className="flex items-center gap-3 p-3 bg-green-50 dark:bg-green-900/20 rounded-xl">
            <img src={resolveMediaUrl(form.photo_url)} className="w-14 h-14 rounded-lg object-cover shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium text-green-700 dark:text-green-400">{t('plants.dbPhoto')}</p>
              <p className="text-xs text-gray-500 dark:text-gray-400">{t('plants.dbPhotoSub')}</p>
            </div>
            <button type="button" onClick={() => setForm(f => ({ ...f, photo_url: null }))}
              className="text-gray-300 dark:text-gray-600 hover:text-gray-500 text-lg leading-none shrink-0">×</button>
          </div>
        )}

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t('plants.nickname')}</label>
          <input
            type="text"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            required
            placeholder={t('plants.nicknamePh')}
            className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-green-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t('plants.species')}</label>
          <input
            type="text"
            value={form.species}
            onChange={(e) => setForm({ ...form, species: e.target.value })}
            placeholder={t('plants.speciesPh')}
            className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-green-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t('plants.location')}</label>
          <input
            type="text"
            value={form.location}
            onChange={(e) => setForm({ ...form, location: e.target.value })}
            placeholder={t('plants.locationPh')}
            className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-green-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t('plants.notes')}</label>
          <textarea
            value={form.notes}
            onChange={(e) => setForm({ ...form, notes: e.target.value })}
            rows={4}
            placeholder={t('plants.notesPh')}
            className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-green-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500"
          />
        </div>

        {error && <p className="text-red-500 text-sm">{error}</p>}
        <button
          type="submit"
          disabled={loading}
          className="w-full bg-green-600 text-white py-3 rounded-xl font-medium hover:bg-green-700 disabled:opacity-50 transition-colors"
        >
          {loading
            ? t('plants.adding')
            : schedules.length > 0
              ? t('plants.addPlantTasks', { count: schedules.length })
              : t('plants.addPlantBtn')}
        </button>
      </form>
    </div>
  )
}
