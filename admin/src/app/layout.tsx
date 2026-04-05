import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { getSessionUser } from "@/lib/auth";
import { Sidebar } from "@/components/sidebar";

const inter = Inter({
  subsets: ["latin"],
});

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Tychos Admin",
  description: "Tychos simulation admin interface",
};

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const user = await getSessionUser();

  return (
    <html lang="en" className={inter.className}>
      <body>
        {user ? (
          <div className="flex h-screen overflow-hidden">
            <Sidebar userName={user.name} userEmail={user.email} />
            <main className="flex-1 overflow-y-auto p-6">{children}</main>
          </div>
        ) : (
          children
        )}
      </body>
    </html>
  );
}
