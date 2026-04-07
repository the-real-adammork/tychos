import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  LayoutDashboard,
  Settings2,
  Play,
  GitCompare,
  Database,
  LogOut,
} from "lucide-react";

interface SidebarProps {
  userName: string;
  userEmail: string;
}

const navItems = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/parameters", label: "Parameters", icon: Settings2 },
  { href: "/runs", label: "Runs", icon: Play },
  { href: "/datasets", label: "Datasets", icon: Database },
  { href: "/compare", label: "Compare", icon: GitCompare },
];

export function Sidebar({ userName, userEmail }: SidebarProps) {
  const { pathname } = useLocation();
  const navigate = useNavigate();

  async function handleSignOut() {
    await fetch("/api/auth/logout", { method: "POST" });
    navigate("/login");
  }

  return (
    <aside className="w-52 border-r bg-card h-screen sticky top-0 flex flex-col">
      <div className="flex-1 overflow-y-auto py-4">
        <nav className="flex flex-col gap-1 px-2">
          {navItems.map(({ href, label, icon: Icon }) => {
            const isActive = href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
              <Link
                key={href}
                to={href}
                className={`flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-accent text-accent-foreground"
                    : "text-muted-foreground hover:bg-accent/50"
                }`}
              >
                <Icon className="h-4 w-4 shrink-0" />
                {label}
              </Link>
            );
          })}
        </nav>
      </div>

      <div className="border-t p-3">
        <div className="mb-2 min-w-0">
          <p className="truncate text-sm font-medium">{userName}</p>
          <p className="truncate text-xs text-muted-foreground">{userEmail}</p>
        </div>
        <button
          onClick={handleSignOut}
          className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-accent/50 transition-colors"
        >
          <LogOut className="h-4 w-4 shrink-0" />
          Sign out
        </button>
      </div>
    </aside>
  );
}
