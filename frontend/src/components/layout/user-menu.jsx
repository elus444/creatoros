"use client";

import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { ChevronDown, LogOut, UserRound } from "lucide-react";

import { Button } from "@/components/ui/button";

function getInitials(user) {
  if (user?.full_name) {
    return user.full_name
      .split(" ")
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase())
      .join("");
  }
  return user?.email?.[0]?.toUpperCase() || "U";
}

export function UserMenu({ user, onLogout }) {
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <Button variant="outline" className="gap-2 pl-2 pr-3">
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/10 font-label text-xs font-semibold text-primary">
            {getInitials(user)}
          </span>
          <span className="hidden max-w-[140px] truncate text-left sm:block">
            <span className="block text-sm font-semibold text-on-surface">
              {user?.full_name || "Creator"}
            </span>
            <span className="block text-xs font-normal text-outline">{user?.email}</span>
          </span>
          <ChevronDown className="h-4 w-4 text-outline" />
        </Button>
      </DropdownMenu.Trigger>

      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="end"
          sideOffset={8}
          className="z-50 min-w-[220px] rounded-xl border border-outline-variant bg-surface-container-lowest p-1 shadow-[0_10px_25px_rgba(23,43,77,0.10)]"
        >
          <div className="px-3 py-2">
            <p className="text-sm font-semibold text-on-surface">
              {user?.full_name || "Creator"}
            </p>
            <p className="truncate text-xs text-outline">{user?.email}</p>
          </div>
          <DropdownMenu.Separator className="my-1 h-px bg-outline-variant" />
          <DropdownMenu.Item
            disabled
            className="flex cursor-default items-center gap-2 rounded-lg px-3 py-2 text-sm text-outline outline-none"
          >
            <UserRound className="h-4 w-4" />
            Profile (soon)
          </DropdownMenu.Item>
          <DropdownMenu.Item
            className="flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-sm text-on-surface outline-none hover:bg-surface-container-low"
            onSelect={(event) => {
              event.preventDefault();
              onLogout();
            }}
          >
            <LogOut className="h-4 w-4" />
            Log out
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
