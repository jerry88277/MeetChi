/**
 * /dashboard/meetings → redirect /dashboard
 *
 * 2026-05-24 audit：原檔為 mock 死頁（用假資料 + shadcn Table 與其他頁面手刻
 * 卡片風格不一致），跟主 dashboard 的 list 功能重複。直接 redirect 不再維護。
 * 已 bookmark /dashboard/meetings 的 user 自動轉到正確入口。
 *
 * 個別會議 deep link 走 /dashboard/meetings/[meeting_id]/page.tsx 不受影響。
 */
import { redirect } from 'next/navigation';

export default function MeetingsRedirect() {
    redirect('/dashboard');
}
