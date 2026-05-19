import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CrawlerPro — LinkedIn Group Crawler",
  description:
    "Configure, run, and monitor LinkedIn group crawls with live logs and exportable results.",
};
import { Toaster } from "sonner"
import { AuthProvider } from "@/components/nguyen/shared/components/contexts/AuthContext";
export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="vi" className="light h-full antialiased" suppressHydrationWarning>
      <head>
        {/* Material Symbols — không có next/font; cần cho icon ligature */}
        {/* eslint-disable-next-line @next/next/no-page-custom-font */}
        <link
          href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,400,0,0&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="min-h-full">
        <AuthProvider>
          {children}
        </AuthProvider>
     
        <Toaster
            position="top-right"
            richColors        // màu xanh/đỏ đẹp cho success/error
            closeButton       // hiện nút X
            duration={4000}
          />
      </body>
    </html>
  );
}
