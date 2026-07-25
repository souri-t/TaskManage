import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Review Hub",
  description: "Codex code review finding tracker",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ja">
      <body>{children}</body>
    </html>
  );
}

