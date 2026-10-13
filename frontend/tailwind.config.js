/** @type {import('tailwindcss').Config} */
// Every color is a CSS variable from src/index.css (the single token file).
const token = (name) => `rgb(var(--${name}) / <alpha-value>)`

export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  darkMode: 'class',
  // status and node-type swatches are composed at runtime (bg-${token}, bg-tier-${kind})
  safelist: ['bg-ok', 'bg-warn', 'bg-bad', 'bg-fg-muted', 'bg-accent', { pattern: /^(bg|text|border)-tier-(supplier|factory|warehouse|retailer|customer)$/ }],
  theme: {
    // Type scale: 11 / 12 / 13 / 14 / 16 / 20 / 24
    fontSize: {
      '2xs': ['11px', '16px'],
      xs: ['12px', '16px'],
      sm: ['13px', '20px'],
      base: ['14px', '20px'],
      md: ['16px', '24px'],
      lg: ['20px', '28px'],
      xl: ['24px', '32px'],
    },
    // Two weights for UI text, 600 for page titles only
    fontWeight: { normal: '400', medium: '500', semibold: '600' },
    // 6px controls, 8px panels
    borderRadius: { none: '0', sm: '4px', DEFAULT: '6px', md: '6px', lg: '8px', full: '9999px' },
    extend: {
      colors: {
        bg: token('bg'),
        surface: token('surface'),
        raised: token('raised'),
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
      fontFamily: {
        sans: ['var(--font-sans)'],
        mono: ['var(--font-mono)'],
      },
      boxShadow: { float: 'var(--shadow-float)' },
      transitionDuration: { DEFAULT: '150ms' },
      transitionTimingFunction: { DEFAULT: 'cubic-bezier(0.2, 0, 0, 1)' },
      keyframes: {
        'fade-in': { from: { opacity: '0' }, to: { opacity: '1' } },
        'slide-in': { from: { transform: 'translateX(8px)', opacity: '0' }, to: { transform: 'none', opacity: '1' } },
        'rise-in': { from: { transform: 'translateY(4px)', opacity: '0' }, to: { transform: 'none', opacity: '1' } },
        'pulse-soft': { '0%, 100%': { opacity: '1' }, '50%': { opacity: '0.55' } },
      },
      animation: {
        'fade-in': 'fade-in 150ms cubic-bezier(0.2, 0, 0, 1)',
        'slide-in': 'slide-in 180ms cubic-bezier(0.2, 0, 0, 1)',
        'rise-in': 'rise-in 150ms cubic-bezier(0.2, 0, 0, 1)',
        'pulse-soft': 'pulse-soft 1.6s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
