import type { Metadata, Viewport } from "next";
import "@/styles/globals.css";

export const metadata: Metadata = {
  title: "J.A.R.V.I.S.",
  description: "Just A Rather Very Intelligent System",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "JARVIS",
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
  viewportFit: "cover",
  themeColor: "#000a19",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        {/* iOS standalone web app */}
        <link rel="apple-touch-icon" href="/icon-192.png" />
      </head>
      <body className="antialiased">
        {children}
      </body>
    </html>
  );
}
