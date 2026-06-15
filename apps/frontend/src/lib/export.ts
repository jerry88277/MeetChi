import type { Meeting, Chapter, KeyQuote } from '@/types/meeting';

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

function formatQuote(q: KeyQuote): string {
    return `「${q.text}」— ${q.speaker}`;
}

function formatChapters(chapters: Chapter[]): string {
    if (!chapters || chapters.length === 0) return '';
    let out = '';
    chapters.forEach((ch, i) => {
        out += `\n${'─'.repeat(40)}\n`;
        out += `章節 ${i + 1}：${ch.title}\n`;
        out += `${'─'.repeat(40)}\n`;
        if (ch.summary) out += `${ch.summary}\n\n`;
        if (ch.bullets?.length) {
            ch.bullets.forEach(b => { out += `  • ${b}\n`; });
            out += '\n';
        }
        if (ch.keyQuotes?.length) {
            out += `  重點引述：\n`;
            ch.keyQuotes.forEach(q => { out += `    ${formatQuote(q)}\n`; });
            out += '\n';
        }
        if (ch.subChapters?.length) {
            ch.subChapters.forEach((sc, j) => {
                const ts = `${Math.floor(sc.timeStart / 60)}:${String(Math.floor(sc.timeStart % 60)).padStart(2, '0')}`;
                const te = `${Math.floor(sc.timeEnd / 60)}:${String(Math.floor(sc.timeEnd % 60)).padStart(2, '0')}`;
                out += `  [${ts} ~ ${te}] 子章節 ${j + 1}\n`;
                if (sc.summary) out += `    ${sc.summary}\n`;
                if (sc.bullets?.length) {
                    sc.bullets.forEach(b => { out += `      • ${b}\n`; });
                }
                if (sc.keyQuotes?.length) {
                    sc.keyQuotes.forEach(q => { out += `      ${formatQuote(q)}\n`; });
                }
                out += '\n';
            });
        }
    });
    return out;
}

export function exportAsTxt(meeting: Meeting) {
    let content = `${meeting.title}\n${'='.repeat(meeting.title.length * 2)}\n`;
    content += `日期: ${meeting.date}  時長: ${meeting.duration}\n\n`;

    // TL;DR
    if (meeting.tldr) {
        content += `【一句話摘要】\n${meeting.tldr}\n\n`;
    }

    // Summary
    if (meeting.summary) {
        content += `【整體摘要】\n${meeting.summary}\n\n`;
    }

    // Decisions
    if (meeting.decisions?.length) {
        content += `【核心決策】\n`;
        meeting.decisions.forEach(d => { content += `  ✅ ${d}\n`; });
        content += '\n';
    }

    // Action Items
    if (meeting.actionItems?.length) {
        content += `【待辦事項】\n`;
        meeting.actionItems.forEach(item => {
            content += `  ⚡ ${item.text}`;
            if (item.assignee && item.assignee !== '待分配') content += ` (${item.assignee})`;
            if (item.due && item.due !== '待定') content += ` [截止: ${item.due}]`;
            content += '\n';
        });
        content += '\n';
    }

    // Risks
    if (meeting.risks?.length) {
        content += `【風險提醒】\n`;
        meeting.risks.forEach(r => { content += `  ⚠️ ${r}\n`; });
        content += '\n';
    }

    // Next Steps
    if (meeting.nextSteps?.length) {
        content += `【後續行動】\n`;
        meeting.nextSteps.forEach(ns => {
            content += `  → ${ns.task}`;
            if (ns.assignee) content += ` (${ns.assignee})`;
            if (ns.due) content += ` [${ns.due}]`;
            content += '\n';
        });
        content += '\n';
    }

    // Speaker Contributions
    if (meeting.speakerContributions?.length) {
        content += `【講者貢獻】\n`;
        meeting.speakerContributions.forEach(sc => {
            content += `  ${sc.speaker}${sc.role ? ` (${sc.role})` : ''} — 發言 ${sc.speakTimePct}%\n`;
            if (sc.keyContribution) content += `    主要貢獻: ${sc.keyContribution}\n`;
            if (sc.mainTopics?.length) content += `    參與主題: ${sc.mainTopics.join('、')}\n`;
        });
        content += '\n';
    }

    // Chapters (main content)
    if (meeting.chapters?.length) {
        content += `\n${'═'.repeat(40)}\n`;
        content += `主題章節詳細內容（${meeting.chapters.length} 章）\n`;
        content += `${'═'.repeat(40)}\n`;
        content += formatChapters(meeting.chapters);
    }

    // Key Quotes
    if (meeting.keyQuotes?.length) {
        content += `\n【精選引述】\n`;
        meeting.keyQuotes.forEach(q => { content += `  ${formatQuote(q)}\n`; });
        content += '\n';
    }

    // Transcript
    if (meeting.transcript?.length) {
        content += `\n${'═'.repeat(40)}\n`;
        content += `逐字稿\n`;
        content += `${'═'.repeat(40)}\n\n`;
        meeting.transcript.forEach(line => {
            content += `[${line.time}] ${line.speaker}: ${line.text}\n`;
        });
    }

    downloadFile(content, `${meeting.title}.txt`, 'text/plain;charset=utf-8');
}

export function exportAsSrt(meeting: Meeting) {
    if (!meeting.transcript?.length) return;
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
        tldr: meeting.tldr,
        summary: meeting.summary,
        decisions: meeting.decisions,
        risks: meeting.risks,
        actionItems: meeting.actionItems,
        nextSteps: meeting.nextSteps,
        chapters: meeting.chapters,
        speakerContributions: meeting.speakerContributions,
        keyQuotes: meeting.keyQuotes,
        transcript: meeting.transcript,
    };
    downloadFile(JSON.stringify(data, null, 2), `${meeting.title}.json`, 'application/json;charset=utf-8');
}
