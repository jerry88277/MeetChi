import Link from "next/link";
import { cn } from "@/lib/utils"; // Assuming @/lib/utils.ts exists
import { Mic, History, Settings2, Users } from "lucide-react"; // Using lucide-react for icons

interface DashboardLayoutProps {
  children: React.ReactNode;
}

export default function DashboardLayout({ children }: DashboardLayoutProps) {
  const sidebarNavItems = [
    {
      title: "會議列表",
      href: "/dashboard/meetings",
      icon: <History className="mr-2 h-4 w-4" />,
    },
    {
      title: "模板管理",
      href: "/dashboard/templates",
      icon: <Settings2 className="mr-2 h-4 w-4" />,
    },
    {
      title: "使用者管理",
      href: "/dashboard/users",
      icon: <Users className="mr-2 h-4 w-4" />,
    },
  ];

  return (
    <div className="flex min-h-screen">
      {/* Sidebar */}
      <aside className="w-64 border-r bg-background p-4">
        <div className="flex h-16 items-center px-4">
          <Link href="/dashboard" className="flex items-center gap-2 font-semibold">
            <Mic className="h-6 w-6" />
            <span className="text-lg">TranscriptHub</span>
          </Link>
        </div>
        <nav className="flex-1 space-y-2">
          {sidebarNavItems.map((item) => (
            <Link key={item.href} href={item.href}>
              <div
                className={cn(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-primary transition-all hover:bg-muted",
                  // Add active state styling here based on current path
                  // pathname === item.href && "bg-muted"
                )}
              >
                {item.icon}
                {item.title}
              </div>
            </Link>
          ))}
        </nav>
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col">
        {/* Header */}
        <header className="flex h-16 items-center gap-4 border-b bg-background px-6">
          <h1 className="text-xl font-semibold">Dashboard</h1>
          {/* Add user menu or other header elements here */}
        </header>

        {/* Page Content */}
        <main className="flex-1 p-6 overflow-auto">
          {children}
        </main>
      </div>
    </div>
  );
}
