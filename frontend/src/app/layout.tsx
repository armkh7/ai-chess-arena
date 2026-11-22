import { ChessKnight } from "lucide-react";
import type { Metadata } from "next";
import { JetBrains_Mono, Space_Grotesk } from "next/font/google";
import Link from "next/link";
import "./globals.css";

// Fonts are downloaded at build time and served from this site (no requests to Google).
// Space Grotesk for text and headings, JetBrains Mono for moves and code names.
const textFont = Space_Grotesk({
  variable: "--font-text",
  subsets: ["latin"],
});

const codeFont = JetBrains_Mono({
  variable: "--font-code",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: { default: "AI Chess Arena", template: "%s · AI Chess Arena" },
  description:
    "AI models play chess against each other, explain every move, and get scored by Stockfish.",
};

const NAV = [
  ["/", "Play"],
  ["/games", "Games"],
  ["/leaderboard", "Leaderboard"],
  ["/how-it-works", "How it works"],
] as const;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${textFont.variable} ${codeFont.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col bg-ui-950 font-sans text-ui-100">
        <header className="border-b border-ui-800/80">
          {/* Phones: the links wrap onto their own row under the logo */}
          <nav className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-x-6 gap-y-2 px-4 py-3">
            <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
              <ChessKnight className="size-6 text-accent-400" aria-hidden />
              AI Chess Arena
            </Link>
            <div className="flex w-full justify-between gap-6 text-base text-ui-300 sm:w-auto">
              {NAV.map(([href, label]) => (
                <Link key={href} href={href} className="whitespace-nowrap hover:text-ui-100">
                  {label}
                </Link>
              ))}
            </div>
          </nav>
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">{children}</main>
      </body>
    </html>
  );
}
