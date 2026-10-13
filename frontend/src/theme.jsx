import { createContext, useCallback, useContext, useLayoutEffect, useMemo, useState } from 'react'

const ThemeContext = createContext(null)
const STORAGE_KEY = 'aegis-theme'

const TOKEN_NAMES = [
  'bg', 'surface', 'surface-2', 'surface-3', 'border', 'border-strong', 'fg', 'fg-2', 'fg-muted',
  'accent', 'accent-hover', 'accent-fg', 'ok', 'warn', 'bad',
  'tier-supplier', 'tier-factory', 'tier-warehouse', 'tier-retailer', 'tier-customer', 'map-bg',
]

function readStoredTheme() {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'dark' ? 'dark' : 'light'
  } catch {
    return 'light'
  }
}

function readTokens() {
  const css = getComputedStyle(document.documentElement)
  const rgb = {}
  const color = {}
  for (const name of TOKEN_NAMES) {
    const parts = css.getPropertyValue(`--${name}`).trim().split(/\s+/).map(Number)
    const triple = parts.length === 3 && parts.every(Number.isFinite) ? parts : [128, 128, 128]
    const key = name.replace(/-(\w)/g, (_, c) => c.toUpperCase())
    rgb[key] = triple
    // comma syntax: Cytoscape's color parser does not accept the space-separated CSS Color 4 form
    color[key] = `rgb(${triple.join(', ')})`
  }
  // rgba() helper for libraries that need explicit alpha (Recharts, Cytoscape)
  const alpha = (key, a) => `rgba(${rgb[key].join(', ')}, ${a})`
  return { rgb, color, alpha }
}

/** Light by default; dark is opt-in and remembered. Tokens are re-read whenever the theme changes. */
export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(readStoredTheme)
  const [tokens, setTokens] = useState(null)

  useLayoutEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark')
    try {
      localStorage.setItem(STORAGE_KEY, theme)
    } catch {
      /* storage unavailable: theme still applies for this session */
    }
    setTokens(readTokens())
  }, [theme])

  const toggle = useCallback(() => setTheme((t) => (t === 'dark' ? 'light' : 'dark')), [])
  const value = useMemo(() => ({ theme, toggle, tokens }), [theme, toggle, tokens])
  return <ThemeContext.Provider value={value}>{tokens ? children : null}</ThemeContext.Provider>
}

export function useTheme() {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme must be used inside <ThemeProvider>')
  return ctx
}

/** Design tokens as rgb() strings (color), [r,g,b] arrays (rgb) and alpha(key, a) for chart/graph libraries. */
export function useTokens() {
  return useTheme().tokens
}
