/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eef2ff",
          500: "#6366f1",
          600: "#4f46e5",
          700: "#4338ca",
        },
        surface: {
          900: "#0f1117",
          800: "#151823",
          700: "#1e2235",
          600: "#282d41",
        },
      },
    },
  },
  plugins: [],
};
