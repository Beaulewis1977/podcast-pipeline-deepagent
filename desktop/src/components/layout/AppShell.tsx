/**
 * Main layout shell for the Podcast Pipeline desktop app.
 *
 * Composes the fixed Header, collapsible Sidebar, and scrollable
 * content area into the application frame. The h-screen + overflow-hidden
 * root prevents double scrollbars — only the main content area scrolls.
 *
 * Usage:
 *   <AppShell>
 *     <IngestionView />
 *   </AppShell>
 */

import React from "react";
import { Header } from "./Header";
import { Sidebar } from "./Sidebar";

interface AppShellProps {
  children: React.ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  return (
    <div className="flex flex-col h-screen overflow-hidden bg-[var(--color-bg-primary)]">
      <Header />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-auto p-6 text-[var(--color-text-primary)]">
          {children}
        </main>
      </div>
    </div>
  );
}
