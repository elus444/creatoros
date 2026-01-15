"use client";

import { Menu, Search } from "lucide-react";

import { UserMenu } from "@/components/layout/user-menu";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export function Header({ user, onMenuClick, onLogout }) {
  return (
    <header className="sticky top-0 z-30 border-b border-outline-variant/70 bg-surface/85 backdrop-blur-md">
      <div className="flex items-center gap-3 px-4 py-3 md:px-6">
        <Button variant="ghost" size="icon" className="lg:hidden" onClick={onMenuClick}>
          <Menu className="h-5 w-5" />
        </Button>

        <div className="relative hidden min-w-0 flex-1 md:block md:max-w-md">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-outline" />
          <Input
            disabled
            className="pl-9"
            placeholder="Search workspace (coming soon)"
            aria-label="Search workspace"
          />
        </div>

        <div className="ml-auto flex items-center gap-2">
          <UserMenu user={user} onLogout={onLogout} />
        </div>
      </div>
    </header>
  );
}
