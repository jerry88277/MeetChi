interface DashboardLayoutProps {
  children: React.ReactNode;
}

export default function DashboardLayout({ children }: DashboardLayoutProps) {
  // The sidebar is managed by page.tsx directly
  // This layout just provides a simple wrapper
  return <>{children}</>;
}

