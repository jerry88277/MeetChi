// Compile-time feature flags — flip UAT_MODE=false for production
export const UAT_MODE = true;
export const TOUR_STORAGE_KEY = 'meetchi_tour_completed_v1';
// CS-1：跳過導覽只寫「本次略過」旗標（非永久完成），零會議首頁仍常駐「觀看導覽」入口，
// 直到使用者真正看完（completed）或完成第一場會議。避免反射性跳過後永遠失去導覽。
export const TOUR_DISMISSED_KEY = 'meetchi_tour_dismissed_v1';
// CS-6：會議詳情頁首次開啟的 coachmark 只顯示一次。
export const DETAIL_COACHMARK_KEY = 'meetchi_detail_coachmark_v1';
export const RAG_INACTIVITY_MS = 30 * 60 * 1000; // 30 minutes


// 模板領域分類 → 中文標籤（單一來源）。
// DetailView 右上角模板下拉 & TemplateGallery 皆共用，避免顯示不一致
// （曾發生詳情頁下拉直接秀英文碼 general，與模板管理頁的「通用」不一致，造成混淆）。
export const TEMPLATE_CATEGORY_LABELS: Record<string, string> = {
    all: '全部',
    general: '通用',
    sales: '業務',
    hr: '人資',
    engineering: '工程',
    custom: '自訂',
};
export const getTemplateCategoryLabel = (category?: string): string =>
    (category && TEMPLATE_CATEGORY_LABELS[category]) || category || '通用';
