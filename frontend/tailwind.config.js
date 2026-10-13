/** @type {import('tailwindcss').Config} */
const token = (name) => `rgb(var(--${name}) / <alpha-value>)`

export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  darkMode: 'class',
  // status swatches and node-type swatches are composed at runtime (bg-${token}, bg-tier-${kind})
  safelist: ['bg-ok', 'bg-warn', 'bg-bad', { pattern: /^(bg|text|border)-tier-(supplier|factory|warehouse|retailer|customer)$/ }],
  theme: {
    // Type scale: 12 / 14 / 16 / 20 / 28
    fontSize: {
      xs: ['12px', '16px'],
      sm: ['14px', '20px'],
      base: ['16px', '24px'],
      lg: ['20px', '28px'],
      xl: ['28px', '34px'],
    },
    extend: {
      colors: {
        bg: token('bg'),
        surface: { DEFAULT: token('surface'), 2: token('surface-2'), 3: token('surface-3') },
        border: { DEFAULT: token('border'), strong: token('border-strong') },
        fg: { DEFAULT: token('fg'), 2: token('fg-2'), muted: token('fg-muted') },
        accent: { DEFAULT: token('accent'), hover: token('accent-hover'), fg: token('accent-fg') },
        ok: token('ok'),
        warn: token('warn'),
        bad: token('bad'),
        tier: {
          supplier: token('tier-supplier'),
          factory: token('tier-factory'),
          warehouse: token('tier-warehouse'),
          retailer: token('tier-retailer'),
          customer: token('tier-customer'),
        },
        map: token('map-bg'),
      },
      fontFamily: { sans: ['"Inter Variable"', 'ui-sans-serif', 'system-ui', 'sans-serif'] },
      borderRadius: { card: '12px' },
      boxShadow: { card: 'var(--shadow)' },
      transitionDuration: { DEFAULT: '150ms' },
      keyframes: {
        'fade-in': { from: { opacity: '0' }, to: { opacity: '1' } },
        'slide-in': { from: { transform: 'translateX(16px)', opacity: '0' }, to: { transform: 'none', opacity: '1' } },
        shimmer: { '0%': { opacity: '0.55' }, '50%': { opacity: '1' }, '100%': { opacity: '0.55' } },
      },
      animation: {
        'fade-in': 'fade-in 180ms ease-out',
        'slide-in': 'slide-in 200ms ease-out',
        shimmer: 'shimmer 1.4s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
