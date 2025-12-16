import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Sidebar } from "@/components/layout/sidebar";
import { Header } from "@/components/layout/header";
import { Providers } from "@/components/providers";
import { Toaster } from "sonner";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "IT-Friends Handwerk Dashboard",
  description:
    "Kundenservice-Plattform für deutsche Handwerksbetriebe - Aufgabenverwaltung, Routing und Analyse",
  keywords: [
    "Handwerk",
    "Kundenservice",
    "Aufgabenverwaltung",
    "SHK",
    "Elektro",
    "Sanitär",
    "Deutschland",
  ],
  authors: [{ name: "IT-Friends" }],
  robots: "noindex, nofollow", // Private dashboard
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="de" suppressHydrationWarning>
      <body className={`${inter.variable} font-sans antialiased`}>
        <Providers>
          <div className="flex min-h-screen">
            {/* Sidebar */}
            <Sidebar />

            {/* Main Content Area */}
            <div className="flex flex-1 flex-col pl-64">
              {/* Header */}
              <Header />

              {/* Page Content */}
              <main className="flex-1 overflow-y-auto bg-muted/30 p-6">
                {children}
              </main>
            </div>
          </div>

          {/* Toast Notifications */}
          <Toaster
            position="top-right"
            toastOptions={{
              className: "font-sans",
              duration: 4000,
            }}
            richColors
            closeButton
          />
        </Providers>
      </body>
    </html>
  );
}
