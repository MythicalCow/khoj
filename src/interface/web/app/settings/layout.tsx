import type { Metadata } from "next";
import { Noto_Sans } from "next/font/google";
import "../globals.css";
import { Toaster } from "@/components/ui/toaster";

const inter = Noto_Sans({ subsets: ["latin"] });

export const metadata: Metadata = {
    title: "Khoj AI - Settings",
    description: "Configure Khoj to get personalized, deeper assistance.",
    icons: {
        icon: "/static/favicon.ico",
    },
};

export default function RootLayout({
    children,
}: Readonly<{
    children: React.ReactNode;
}>) {
    return (
        <html lang="en">
            <meta
                httpEquiv="Content-Security-Policy"
                content="default-src 'self' https://assets.khoj.dev;
                        script-src 'self' https://assets.khoj.dev 'unsafe-inline' 'unsafe-eval';
                        connect-src 'self' data: blob: https://ipapi.co/json ws://localhost:42110;
                        style-src 'self' https://assets.khoj.dev 'unsafe-inline' https://fonts.googleapis.com;
                        img-src 'self' data: blob: https://*.khoj.dev https://*.googleusercontent.com;
                        font-src 'self' https://assets.khoj.dev https://fonts.gstatic.com;
                        child-src 'none';
                        object-src 'none';"
            ></meta>
            <body className={inter.className}>
                {children}
                <Toaster />
            </body>
        </html>
    );
}
