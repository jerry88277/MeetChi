import { SecurityWrapper } from '@/components/SecurityWrapper';

interface DashboardLayoutProps {
  children: React.ReactNode;
}

export default function DashboardLayout({ children }: DashboardLayoutProps) {
  // The sidebar is managed by page.tsx directly
  // This layout wraps the entire dashboard in enterprise security validation
  return (
    <SecurityWrapper>
      {children}
    </SecurityWrapper>
  );
}
