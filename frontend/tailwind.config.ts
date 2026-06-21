import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './contexts/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['var(--font-manrope)', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        display: ['var(--font-fraunces)', 'Georgia', 'serif'],
      },
      colors: {
        night: '#06120f',
        graphite: '#10171a',
        mist: '#d7e7df',
        ember: '#ffb86b',
      },
      boxShadow: {
        glow: '0 0 44px rgba(45, 212, 191, .22)',
        lift: '0 28px 80px rgba(0, 0, 0, .38)',
      },
    },
  },
  plugins: [],
};

export default config;
