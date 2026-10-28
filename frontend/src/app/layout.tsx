import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";

import { TooltipProvider } from "@/components/ui/tooltip";
import { Providers } from "./providers";
import "./globals.css";

const inter = Inter({ variable: "--font-inter", subsets: ["latin"] });
const mono = JetBrains_Mono({ variable: "--font-jetbrains-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "TRAFIQON",
  description: "Transportation optimization and simulation workbench",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    // data-theme starts dark (command center default); the persisted choice is applied on
    // the client by ThemeSync, hence suppressHydrationWarning on this element only.
    <html
      lang="en"
      data-theme="dark"
      suppressHydrationWarning
      className={`${inter.variable} ${mono.variable} h-full`}
    >
      <body>
        <Providers>
          <TooltipProvider>{children}</TooltipProvider>
        </Providers>
      </body>
    </html>
  );
}
