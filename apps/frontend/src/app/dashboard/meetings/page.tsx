"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { format } from "date-fns"; // For date formatting
import { Button } from "@/components/ui/button"; // Assuming Shadcn Button
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"; // Assuming Shadcn Table

type Meeting = {
  id: string;
  title: string;
  date: string; // ISO string
  duration: number; // seconds
  type: string;
  status: string;
};

const mockMeetings: Meeting[] = [
  {
    id: "1",
    title: "產品規劃會議",
    date: "2025-12-15T10:00:00Z",
    duration: 3600,
    type: "R&D",
    status: "completed",
  },
  {
    id: "2",
    title: "客戶需求訪談 - Acme Corp",
    date: "2025-12-14T14:30:00Z",
    duration: 2700,
    type: "Sales",
    status: "completed",
  },
  {
    id: "3",
    title: "新人面試 - AI Engineer",
    date: "2025-12-13T09:00:00Z",
    duration: 1800,
    type: "HR",
    status: "processing",
  },
];

export default function MeetingsPage() {
  const [meetings, setMeetings] = useState<Meeting[]>([]);

  useEffect(() => {
    // In a real application, you would fetch data from your FastAPI backend here.
    // Example: fetch('/api/v1/meetings').then(res => res.json()).then(setMeetings);
    setMeetings(mockMeetings);
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-3xl font-bold tracking-tight">會議列表</h2>
        <Button asChild>
          <Link href="/dashboard/meetings/new">新建會議</Link>
        </Button>
      </div>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>標題</TableHead>
            <TableHead>日期</TableHead>
            <TableHead>時長</TableHead>
            <TableHead>類型</TableHead>
            <TableHead>狀態</TableHead>
            <TableHead className="text-right">操作</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {meetings.map((meeting) => (
            <TableRow key={meeting.id}>
              <TableCell className="font-medium">{meeting.title}</TableCell>
              <TableCell>{format(new Date(meeting.date), "yyyy-MM-dd HH:mm")}</TableCell>
              <TableCell>{Math.floor(meeting.duration / 60)} 分鐘</TableCell>
              <TableCell>{meeting.type}</TableCell>
              <TableCell>
                <span 
                  className={`px-2 py-1 rounded-full text-xs font-semibold
                    ${meeting.status === 'completed' ? 'bg-green-100 text-green-800' : ''}
                    ${meeting.status === 'processing' ? 'bg-yellow-100 text-yellow-800 animate-pulse' : ''}
                    ${meeting.status === 'failed' ? 'bg-red-100 text-red-800' : ''}
                  `}
                >
                  {meeting.status === 'completed' ? '已完成' : meeting.status === 'processing' ? '處理中' : '失敗'}
                </span>
              </TableCell>
              <TableCell className="text-right">
                <Button variant="ghost" size="sm" asChild>
                  <Link href={`/dashboard/meetings/${meeting.id}`}>查看詳情</Link>
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
