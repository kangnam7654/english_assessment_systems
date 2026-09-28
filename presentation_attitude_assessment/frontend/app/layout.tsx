import type { Metadata } from "next";
import "../src/style.css";

export const metadata: Metadata = {
  title: "발표 영상 분석 | Presentation Attitude",
  description: "발표 영상의 얼굴과 손 움직임을 분석합니다.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko">
      <body className="antialiased">{children}</body>
    </html>
  );
}
