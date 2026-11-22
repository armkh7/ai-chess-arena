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

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col bg-zinc-950 font-sans text-zinc-100">
        <header className="border-b border-zinc-800/80">
          <nav className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
            <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
              <span className="text-xl text-amber-400">♞</span>
              AI Chess Arena
            </Link>
            <div className="flex gap-5 text-sm text-zinc-400">
              <Link href="/" className="hover:text-zinc-100">
                New game
              </Link>
              <Link href="/games" className="hover:text-zinc-100">
                Games
              </Link>
            </div>
          </nav>
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">{children}</main>
      </body>
    </html>
  );
}
