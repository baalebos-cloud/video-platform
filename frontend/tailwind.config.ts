import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#f2f5ff",
          100: "#e6ebff",
          500: "#4f5df7",
          600: "#3c47e0",
          700: "#2f38b3",
          900: "#191f6b",
        },
      },
    },
  },
  plugins: [],
};

export default config;
