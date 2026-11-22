import { ChessKnight } from "lucide-react";
import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
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
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col bg-ui-950 font-sans text-ui-100">
        <header className="border-b border-ui-800/80">
          {/* Phones: the links wrap onto their own row under the logo */}
          <nav className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-x-6 gap-y-2 px-4 py-3">
            <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
              <ChessKnight className="size-6 text-accent-400" aria-hidden />
              AI Chess Arena
            </Link>
            <div className="flex w-full justify-between gap-5 text-sm text-ui-400 sm:w-auto">
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
