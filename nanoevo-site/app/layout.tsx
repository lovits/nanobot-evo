import type { Metadata } from "next";
import { headers } from "next/headers";
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

export async function generateMetadata(): Promise<Metadata> {
  const requestHeaders = await headers();
  const host = requestHeaders.get("x-forwarded-host") ?? requestHeaders.get("host") ?? "localhost:3000";
  const protocol =
    requestHeaders.get("x-forwarded-proto") ?? (host.startsWith("localhost") ? "http" : "https");
  const origin = `${protocol}://${host}`;
  const socialImage = `${origin}/og.png`;

  return {
    title: "NanoEvo — 可审计的 Skill 演化控制层",
    description:
      "NanoEvo 从真实工作证据中生成 Skill 改进提案，并通过人工批准、冲突检测和版本回滚安全应用。",
    icons: {
      icon: "/nanoevo-icon.png",
      shortcut: "/nanoevo-icon.png",
    },
    openGraph: {
      title: "NanoEvo — Skills that learn from real work",
      description: "Evidence-driven, human-approved Skill evolution for nanobot.",
      type: "website",
      images: [{ url: socialImage, width: 1200, height: 630, alt: "NanoEvo" }],
    },
    twitter: {
      card: "summary_large_image",
      title: "NanoEvo — Skills that learn from real work",
      description: "Evidence-driven, human-approved Skill evolution for nanobot.",
      images: [socialImage],
    },
  };
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        {children}
      </body>
    </html>
  );
}
