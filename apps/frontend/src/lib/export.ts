import type { Meeting } from '@/types/meeting';

function downloadFile(content: string, filename: string, mimeType: string) {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

export function exportAsTxt(meeting: Meeting) {
    let content = `${meeting.title}\n${'='.repeat(meeting.title.length)}\n`;
    content += `日期: ${meeting.date}  時長: ${meeting.duration}\n\n`;
    if (meeting.summary) {
        content += `【摘要】\n${meeting.summary}\n\n`;
    }
    if (meeting.actionItems.length > 0) {
        content += `【待辦事項】\n`;
        meeting.actionItems.forEach(item => {
            content += `- ${item.text} (${item.assignee}, Due: ${item.due})\n`;
        });
        content += '\n';
    }
    if (meeting.transcript.length > 0) {
        content += `【逐字稿】\n`;
        meeting.transcript.forEach(line => {
            content += `[${line.time}] ${line.speaker}: ${line.text}\n`;
        });
    }
    downloadFile(content, `${meeting.title}.txt`, 'text/plain;charset=utf-8');
}

export function exportAsSrt(meeting: Meeting) {
    if (meeting.transcript.length === 0) return;
    let content = '';
    meeting.transcript.forEach((line, idx) => {
        const startTime = line.time.replace(/^(\d+):(\d+)$/, '00:$1:$2,000');
        content += `${idx + 1}\n`;
        content += `${startTime} --> ${startTime}\n`;
        content += `${line.speaker}: ${line.text}\n\n`;
    });
    downloadFile(content, `${meeting.title}.srt`, 'text/srt;charset=utf-8');
}

export function exportAsJson(meeting: Meeting) {
    const data = {
        title: meeting.title,
        date: meeting.date,
        duration: meeting.duration,
        status: meeting.status,
        summary: meeting.summary,
        actionItems: meeting.actionItems,
        transcript: meeting.transcript
    };
    downloadFile(JSON.stringify(data, null, 2), `${meeting.title}.json`, 'application/json;charset=utf-8');
}
