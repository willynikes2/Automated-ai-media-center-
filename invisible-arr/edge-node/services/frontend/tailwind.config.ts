import type { Config } from 'tailwindcss';

export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: {
          primary: '#101010',
          secondary: '#181818',
          tertiary: '#202020',
        },
        accent: {
          DEFAULT: '#E53935',
          hover: '#EF5350',
          muted: '#C62828',
        },
        status: {
          available: '#22c55e',
          requested: '#6366f1',
          processing: '#f59e0b',
          failed: '#ef4444',
          downloading: '#3b82f6',
        },
        text: {
          primary: '#f1f5f9',
          secondary: '#94a3b8',
          tertiary: '#64748b',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
      },
    },
  },
  plugins: [],
} satisfies Config;
