"use client";

import { useState, useEffect } from "react";
import { useParams } from "next/navigation"; // For Next.js App Router
import { format } from "date-fns";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge"; // Assuming Badge component exists
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"; // Assuming DropdownMenu exists
import { Download } from "lucide-react";

type Segment = {
  text: string;
  start: number; // in seconds
  end: number; // in seconds
};

type MeetingDetail = {
  id: string;
  title: string;
  date: string; // ISO string
  duration: number; // seconds
  type: string;
  status: string;
  transcript: Segment[];
  summary: {
    overview?: string;
    actionItems?: string[];
    decisions?: string[];
    risks?: string[];
  };
};

const mockMeetingDetail: MeetingDetail = {
  id: "1",
  title: "產品規劃會議",
  date: "2025-12-15T10:00:00Z",
  duration: 3600,
  type: "R&D",
  status: "completed",
  transcript: [
    { start: 0, end: 3.5, text: "大家好，歡迎參加今天的產品規劃會議。" },
    { start: 4.0, end: 8.2, text: "這次會議主要討論第二季度的功能開發和資源分配。" },
    { start: 8.5, end: 12.1, text: "首先，由產品經理小明介紹最新市場調研結果。" },
    { start: 12.5, end: 17.8, text: "小明提到用戶對語音助手的要求越來越高，特別是降噪功能。" },
    { start: 18.2, end: 22.5, text: "因此，我們決定將前端音訊優化作為 Sprint 4.7 的核心任務。" },
    { start: 23.0, end: 27.5, text: "小華，請你負責評估 AudioWorklet 和 RNNoise 的整合方案。" },
    { start: 28.0, end: 32.8, text: "好的，我會盡快啟動調研，並提供技術可行性報告。" },
    { start: 33.2, end: 38.0, text: "另外，關於會議記錄的結構化摘要功能，我們需要定義不同的模板。" },
    { start: 38.5, end: 43.1, text: "例如，銷售部門需要 BANT 模板，人資部門需要 STAR 模板。" },
  ],
  summary: {
    overview: "會議討論了第二季度功能開發，確認了前端音訊優化為 Sprint 4.7 核心任務，並規劃了結構化摘要的模板定義。",
    actionItems: [
      "小華：負責評估 AudioWorklet 和 RNNoise 的整合方案。",
      "產品團隊：定義結構化摘要的銷售 (BANT) 和人資 (STAR) 模板。",
    ],
    decisions: [
      "前端音訊優化 (AudioWorklet & RNNoise) 為 Sprint 4.7 核心任務。",
      "會議記錄結構化摘要需支援多種模板。",
    ],
    risks: ["RNNoise 的 WASM 檔案獲取可能存在困難。"],
  },
};

export default function MeetingDetailPage() {
  const params = useParams();
  const meetingId = params.meeting_id;
  const [meeting, setMeeting] = useState<MeetingDetail | null>(null);

  useEffect(() => {
    // In a real application, fetch meeting details from your FastAPI backend
    // fetch(`/api/v1/meetings/${meetingId}`).then(res => res.json()).then(setMeeting);
    // For now, use mock data.
    if (meetingId === "1") {
      setMeeting(mockMeetingDetail);
    } else {
      setMeeting({
        ...mockMeetingDetail,
        id: meetingId as string,
        title: `Mock Meeting ${meetingId}`,
      });
    }
  }, [meetingId]);

  if (!meeting) {
    return (
      <div className="flex justify-center items-center h-full">
        <p>載入中或會議不存在...</p>
      </div>
    );
  }

  const formatTime = (seconds: number) => {
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.floor(seconds % 60);
    return `${minutes.toString().padStart(2, '0')}:${remainingSeconds.toString().padStart(2, '0')}`;
  };

  const handleDownload = (format: string) => {
    console.log(`Downloading meeting ${meeting.id} in ${format} format.`);
    // In a real app, trigger backend API download: `/api/v1/meetings/${meeting.id}/download?format=${format}`
  };

  return (
    <div className="space-y-6">
      <h2 className="text-3xl font-bold tracking-tight">{meeting.title}</h2>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex justify-between items-center">
              會議概覽
              <Badge variant="secondary">{meeting.type}</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p><strong>日期:</strong> {format(new Date(meeting.date), "yyyy-MM-dd HH:mm")}</p>
            <p><strong>時長:</strong> {Math.floor(meeting.duration / 60)} 分鐘</p>
            {meeting.summary.overview && (
              <div>
                <h3 className="font-semibold mt-2">概述:</h3>
                <p>{meeting.summary.overview}</p>
              </div>
            )}
            {meeting.summary.actionItems && meeting.summary.actionItems.length > 0 && (
              <div>
                <h3 className="font-semibold mt-2">行動項目:</h3>
                <ul className="list-disc pl-5">
                  {meeting.summary.actionItems.map((item, index) => (
                    <li key={index}>{item}</li>
                  ))}
                </ul>
              </div>
            )}
            {meeting.summary.decisions && meeting.summary.decisions.length > 0 && (
              <div>
                <h3 className="font-semibold mt-2">決策點:</h3>
                <ul className="list-disc pl-5">
                  {meeting.summary.decisions.map((item, index) => (
                    <li key={index}>{item}</li>
                  ))}
                </ul>
              </div>
            )}
            {meeting.summary.risks && meeting.summary.risks.length > 0 && (
              <div>
                <h3 className="font-semibold mt-2">風險:</h3>
                <ul className="list-disc pl-5">
                  {meeting.summary.risks.map((item, index) => (
                    <li key={index}>{item}</li>
                  ))}
                </ul>
              </div>
            )}

            <div className="pt-4">
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button><Download className="mr-2 h-4 w-4" /> 下載逐字稿</Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent>
                  <DropdownMenuItem onClick={() => handleDownload("txt")}>TXT</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => handleDownload("srt")}>SRT</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => handleDownload("json")}>JSON</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => handleDownload("pdf")}>PDF</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => handleDownload("docx")}>DOCX</DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>原始逐字稿</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {meeting.transcript.map((segment, index) => (
              <p key={index} className="text-sm">
                <span className="font-mono text-muted-foreground mr-2">[{formatTime(segment.start)}]</span>
                {segment.text}
              </p>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
