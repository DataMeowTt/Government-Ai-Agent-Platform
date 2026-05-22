import type { Metadata } from "next";
import { Public_Sans } from "next/font/google";
import "./globals.css";
import QueryProvider from "@/components/providers/QueryProvider";

const publicSans = Public_Sans({ subsets: ["latin", "vietnamese"] });

export const metadata: Metadata = {
  title: "Nền tảng dữ liệu kinh tế chính phủ",
  description: "Bảng điều hành phân tích kinh tế dựa trên dữ liệu công khai và trợ lý dữ liệu AI",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="vi">
      <body className={publicSans.className}>
        <QueryProvider>{children}</QueryProvider>
      </body>
    </html>
  );
}
