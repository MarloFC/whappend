import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "WhAppend — AI Video Analysis",
  description:
    "Upload a video and instantly get a timestamped event timeline. Ask questions about what happened using LLM-powered Q&A.",
  keywords: ["video analysis", "AI", "timeline", "LLM", "RAG", "event detection"],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={inter.variable}>
      <body>{children}</body>
    </html>
  );
}
