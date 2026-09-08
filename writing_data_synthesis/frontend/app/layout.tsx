import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "English Writing Assessment",
  description: "Multi-Agent English Essay Generation & Assessment System",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">
        {children}
      </body>
    </html>
  );
}
