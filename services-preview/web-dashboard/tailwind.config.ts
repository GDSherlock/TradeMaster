import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#101c1a",
        muted: "#4f6360",
        surface: "#f7faf9",
        accent: {
          DEFAULT: "#147a68",
          soft: "#d7f2eb",
          deep: "#0f5f52"
        }
      },
      borderRadius: {
        "2.5xl": "1.5rem",
        "3xl": "1.9rem"
      },
      boxShadow: {
        card: "0 16px 40px rgba(16, 28, 26, 0.08)",
        hover: "0 22px 48px rgba(20, 122, 104, 0.16)"
      },
      fontFamily: {
        editorial: ["'Source Serif 4'", "serif"],
        sans: ["Manrope", "ui-sans-serif", "system-ui"]
      },
      backgroundImage: {
        "hero-glow":
          "radial-gradient(circle at 20% 10%, rgba(20,122,104,0.12), transparent 45%), radial-gradient(circle at 80% 20%, rgba(15,95,82,0.07), transparent 40%)"
      }
    }
  },
  plugins: []
};

export default config;
