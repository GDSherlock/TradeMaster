import type { Metadata } from "next";

import "./globals.css";
import "@fontsource/manrope/index.css";
import "@fontsource/source-serif-4/index.css";

export const metadata: Metadata = {
  title: "Crypto Analyst Dashboard",
  description: "Crypto signals, risk insights, portfolio intelligence, and alert automation"
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="scroll-smooth">
      <body className="bg-surface text-ink antialiased">
        {children}
      </body>
    </html>
  );
}
