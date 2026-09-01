import type { Metadata } from "next";

import ActiveJobBar from "@/components/ActiveJobBar";
import ActiveJobProvider from "@/components/ActiveJobProvider";
import AuthProvider from "@/components/AuthProvider";
import ReferralCapture from "@/components/ReferralCapture";
import ThemeProvider from "@/components/ThemeProvider";
import "./globals.css";

export const metadata: Metadata = {
  title: "BrickForgerAI — Build anything with bricks",
  description:
    "Type a prompt. Get a custom brick model with a downloadable .ldr file, full parts list, and step-by-step PDF build instructions.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          href="https://fonts.googleapis.com/css2?family=Poppins:wght@600;700;800&family=Nunito:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        <ReferralCapture />
        <ThemeProvider>
          <AuthProvider>
            <ActiveJobProvider>
              {children}
              <ActiveJobBar />
            </ActiveJobProvider>
          </AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
