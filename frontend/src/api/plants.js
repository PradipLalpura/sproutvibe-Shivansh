import api from './client'

export const getPlants = () => api.get('/plants/').then(r => r.data)
export const getHealthSummary = () => api.get('/plants/health-summary').then(r => r.data)
export const getPlant = (id) => api.get(`/plants/${id}`).then(r => r.data)
export const createPlant = (data) => api.post('/plants/', data).then(r => r.data)
export const updatePlant = (id, data) => api.patch(`/plants/${id}`, data).then(r => r.data)
export const deletePlant = (id) => api.delete(`/plants/${id}`)
export const uploadPlantPhoto = (id, file) => {
  const form = new FormData()
  form.append('file', file)
  return api.post(`/plants/${id}/photo`, form).then(r => r.data)
}

export const searchSpecies = (q, { lang = 'en', category, kind } = {}) =>
  api.get('/plants/species/search', { params: { q, lang, category, kind } }).then(r => r.data)
export const getSpecies = (id, source = 'perenual', lang = 'en') =>
  api.get(`/plants/species/${id}`, { params: { source, lang } }).then(r => r.data)
export const getWikiDescription = (scientificName, lang = 'en') =>
  api.get('/plants/species/wiki-description', { params: { scientific_name: scientificName, lang } }).then(r => r.data)

// Phase 1 — Indian catalogue (works with no external API keys).
export const getCategories = () => api.get('/plants/categories').then(r => r.data)
export const searchIndianCatalogue = ({ q = '', category, kind, lang = 'en', limit = 20, offset = 0 } = {}) =>
  api.get('/plants/indian-catalogue', { params: { q, category, kind, lang, limit, offset } }).then(r => r.data)

export const getAiCare = (commonName, scientificName) =>
  api.post('/plants/species/ai-care', { common_name: commonName, scientific_name: scientificName }).then(r => r.data)
