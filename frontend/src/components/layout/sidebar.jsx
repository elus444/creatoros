"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  FolderKanban,
  LayoutDashboard,
  LogOut,
  PenSquare,
  Settings,
  Sparkles,
  TrendingUp,
  Workflow,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/create", label: "Create", icon: PenSquare, disabled: true },
  { href: "/trends", label: "Trends", icon: TrendingUp, disabled: true },
  { href: "/content", label: "Content", icon: Sparkles, disabled: true },
  { href: "/analytics", label: "Analytics", icon: BarChart3, disabled: true },
  { href: "/automation", label: "Automation", icon: Workflow, disabled: true },
  { href: "/projects", label: "Projects", icon: FolderKanban, disabled: true },
  { href: "/settings", label: "Settings", icon: Settings, disabled: true },
];

export function Sidebar({ open, onClose, onLogout }) {
  const pathname = usePathname();

  return (
    <>
      <div
        className={cn(
          "fixed inset-0 z-40 bg-on-surface/30 backdrop-blur-[2px] transition-opacity lg:hidden",
          open ? "opacity-100" : "pointer-events-none opacity-0",
        )}
        onClick={onClose}
      />

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex w-[240px] flex-col border-r border-outline-variant/80 bg-surface-container-lowest transition-transform duration-300 lg:static lg:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="flex items-center justify-between px-5 py-5">
          <div>
            <div className="flex items-center gap-2">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-sm font-bold text-on-primary">
                c
              </span>
              <div>
                <p className="font-display text-lg font-bold tracking-tight text-on-surface">
                  creatoros
                </p>
                <p className="font-label text-[10px] uppercase tracking-[0.08em] text-outline">
                  Premium workspace
                </p>
              </div>
            </div>
          </div>
          <Button variant="ghost" size="icon" className="lg:hidden" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        <nav className="flex-1 space-y-1 px-3">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = pathname === item.href;
            const className = cn(
              "flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
              active
                ? "bg-primary text-on-primary shadow-sm"
                : "text-on-surface-variant hover:bg-surface-container-low hover:text-on-surface",
              item.disabled && !active && "cursor-not-allowed opacity-55 hover:bg-transparent",
            );

            if (item.disabled) {
              return (
                <div key={item.label} className={className} title="Coming in a later milestone">
                  <Icon className="h-4 w-4" />
                  <span>{item.label}</span>
                </div>
              );
            }

            return (
              <Link key={item.label} href={item.href} className={className} onClick={onClose}>
                <Icon className="h-4 w-4" />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="border-t border-outline-variant/80 p-3">
          <Button
            variant="ghost"
            className="w-full justify-start text-on-surface-variant"
            onClick={onLogout}
          >
            <LogOut className="h-4 w-4" />
            Logout
          </Button>
        </div>
      </aside>
    </>
  );
}
