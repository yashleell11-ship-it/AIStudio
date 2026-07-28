import type { Metadata, Viewport } from "next";
import { Syne, DM_Sans } from "next/font/google";
import { AppShell } from "@/components/layout/app-shell";
import { ServiceWorkerBoundary } from "@/features/offline";
import { Providers } from "./providers";
import "./globals.css";

const syne = Syne({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
  variable: "--font-syne",
  display: "swap",
});

const dmSans = DM_Sans({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600"],
  variable: "--font-dm-sans",
  display: "swap",
});

export const metadata: Metadata = {
  title: "ManhwaManiacs",
  description: "ManhwaManiacs — read and manage your manga & manhwa library.",
  // `manifest.ts` in this directory generates /manifest.webmanifest; naming it
  // here is what makes the page installable.
  manifest: "/manifest.webmanifest",
  appleWebApp: {
    capable: true,
    title: "Manhwa",
    // iOS has no manifest support worth relying on: the home-screen icon and
    // the status-bar treatment come from these tags instead.
    statusBarStyle: "black-translucent",
  },
  icons: {
    icon: [{ url: "/icons/icon-192.png", sizes: "192x192", type: "image/png" }],
    apple: [{ url: "/icons/apple-touch-icon.png", sizes: "180x180" }],
  },
};

export const viewport: Viewport = {
  // Same near-black as --color-bg, so the OS chrome around an installed window
  // is the app's colour rather than white.
  themeColor: "#0A0A0A",
  // The reader runs edge to edge; without this an installed iOS window letterboxes.
  viewportFit: "cover",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={`${syne.variable} ${dmSans.variable} antialiased`}
    >
      <body>
        <Providers>
          {/*
            Registers the service worker and keeps it told which profile is
            looking. Inside Providers because it reads the storage scope that
            ProfileStorageBoundary publishes; a sibling of the shell because it
            renders only the update prompt and must survive every route change.
          */}
          <ServiceWorkerBoundary />
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
