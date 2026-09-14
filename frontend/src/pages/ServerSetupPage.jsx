import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { setServerUrl } from '../api/client'
import axios from 'axios'

async function testConnection(url) {
  const base = url.replace(/\/$/, '')
  const res = await axios.get(`${base}/api/`, { timeout: 6000 })
  // Verify it's actually a Sprout server
  if (!res.data?.message?.toLowerCase().includes('sprout') &&
      !res.data?.message?.toLowerCase().includes('api')) {
    throw new Error('URL responded but does not look like a Sprout server.')
  }
  return true
}

export default function ServerSetupPage({ onConnected }) {
  const { t } = useTranslation()
  const [url, setUrl] = useState('')
  const [status, setStatus] = useState(null) // null | 'checking' | 'ok' | 'error'
  const [errorMsg, setErrorMsg] = useState('')
  const [autoDetected] = useState(false)

  // Try auto-detecting: the frontend is probably served from the same origin as the API.
  // Skip localhost — that's the Capacitor WebView's own origin, not a real Sprout server.
  // When auto-detected, connect silently without requiring user interaction.
  useEffect(() => {
    const origin = window.location.origin
    if (origin.includes('localhost') || origin.includes('127.0.0.1')) return
    axios.get(`${origin}/api/`, { timeout: 3000 })
      .then((res) => {
        const msg = res.data?.message?.toLowerCase() || ''
        if (!msg.includes('sprout') && !msg.includes('api')) return
        setServerUrl(origin)
        onConnected()
      })
      .catch(() => {})
  }, [onConnected])

  const handleConnect = async (e) => {
    e?.preventDefault()
    if (!url.trim()) return
    setStatus('checking')
    setErrorMsg('')
    try {
      await testConnection(url.trim())
      setServerUrl(url.trim())
      setStatus('ok')
      setTimeout(() => onConnected(), 400)
    } catch (err) {
      setStatus('error')
      setErrorMsg(
        err.code === 'ECONNABORTED' || err.message.includes('timeout')
          ? t('server.timeout')
          : err.response
            ? t('server.badStatus', { status: err.response.status })
            : err.message || t('server.unreachable')
      )
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-green-50 to-emerald-100 dark:from-gray-900 dark:to-gray-800 flex items-center justify-center p-4">
      <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-xl p-8 w-full max-w-md">

        <div className="text-center mb-8">
          <div className="text-6xl mb-3">🌱</div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">{t('server.welcome')}</h1>
          <p className="text-gray-500 dark:text-gray-400 text-sm mt-1">{t('server.subtitle')}</p>
        </div>

        {autoDetected && status !== 'error' && (
          <div className="bg-green-50 dark:bg-green-900/30 border border-green-200 dark:border-green-800 rounded-xl p-3 mb-4 flex items-center gap-2 text-sm text-green-700 dark:text-green-400">
            <span>✓</span>
            <span>Sprout server detected at <span className="font-mono font-medium">{url}</span></span>
          </div>
        )}

        <form onSubmit={handleConnect} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t('server.serverUrl')}</label>
            <input
              type="url"
              value={url}
              onChange={(e) => { setUrl(e.target.value); setStatus(null) }}
              placeholder={t('server.urlPlaceholder')}
              required
              className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-4 py-2.5 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-green-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500"
            />
            <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
              {t('server.urlHint')}, e.g. <span className="font-mono">http://192.168.1.100:3000</span>
            </p>
          </div>

          {status === 'error' && (
            <div className="bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-xl p-3 text-sm text-red-700 dark:text-red-400">
              ✗ {errorMsg}
            </div>
          )}

          {status === 'ok' && (
            <div className="bg-green-50 dark:bg-green-900/30 border border-green-200 dark:border-green-800 rounded-xl p-3 text-sm text-green-700 dark:text-green-400">
              {t('server.connectedRedirect')}
            </div>
          )}

          <button
            type="submit"
            disabled={status === 'checking' || status === 'ok' || !url.trim()}
            className="w-full bg-green-600 text-white py-3 rounded-xl font-medium hover:bg-green-700 disabled:opacity-50 transition-colors"
          >
            {status === 'checking' ? t('common.connecting') : status === 'ok' ? t('server.connected') : t('server.connect')}
          </button>
        </form>

        <p className="text-center text-xs text-gray-400 dark:text-gray-500 mt-6">
          {t('server.selfHosting')}{' '}
          <a href="https://github.com" className="text-green-600 dark:text-green-400 hover:underline">{t('server.setupDocs')}</a>
        </p>
      </div>
    </div>
  )
}
