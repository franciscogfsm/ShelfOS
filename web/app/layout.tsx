import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
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
  title: "ShelfOS",
  description: "Shelf intelligence for fresh produce",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`} suppressHydrationWarning>
      <head>
        {/* the saved theme is applied before the first paint, so the page never flashes the other one */}
        <script dangerouslySetInnerHTML={{ __html: `try{if(localStorage.getItem("shelfos-theme")==="light")document.documentElement.dataset.theme="light"}catch(e){}` }} />
      </head>
      <body className="h-full">{children}</body>
    </html>
  );
}
