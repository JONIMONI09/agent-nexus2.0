import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Local Agent Studio",
  description: "A private multi-agent workspace powered by your local Ollama models.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
