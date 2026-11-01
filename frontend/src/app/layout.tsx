import type { Metadata } from "next";
import type { ReactNode } from "react";

// Minimal root layout. Theme, MUI cache and React Query providers come with T-PLT-30.
export const metadata: Metadata = {
  title: "Centro de Pagos Universal",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="es">
      <body>{children}</body>
    </html>
  );
}
