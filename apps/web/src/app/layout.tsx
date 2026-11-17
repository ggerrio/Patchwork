import type { Metadata } from "next";
import { Inter, JetBrains_Mono, Oswald } from "next/font/google";

import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
});

const oswald = Oswald({
  subsets: ["latin"],
  weight: ["700"],
  variable: "--font-display",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
});

export const metadata: Metadata = {
  title: "PATCHWORK // AUTONOMOUS OPS COMMAND CENTER",
  description: "Industrial-Gothic Autonomous Incident Response & Self-Healing DevOps Copilot",
  icons: {
    icon: "/logo.png",
    shortcut: "/logo.png",
    apple: "/logo.png",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`dark ${inter.variable} ${oswald.variable} ${jetbrainsMono.variable}`}
    >
      <body className="min-h-screen bg-[#0A0A0C] text-[#EAEAEF] antialiased selection:bg-[#C81E1E] selection:text-[#EAEAEF]">
        {children}
      </body>
    </html>
  );
}
