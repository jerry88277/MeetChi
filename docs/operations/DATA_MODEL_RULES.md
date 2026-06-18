# MeetChi 資料模型操作規則

## 重要原則

### 1. 會議可見性由 `meeting_participants` 決定，非 `owner_upn`

**規則**：API 列表端點 (`GET /api/v1/meetings`) 透過 `meeting_participants` 表過濾使用者可見的會議。`meetings.owner_upn` 僅為輔助欄位，不影響前端可見性。

**影響**：
- 建立會議時，必須**同時**在 `meetings` 和 `meeting_participants` 兩張表寫入
- 轉移會議所有權時，必須**同時更新** `meetings.owner_upn` 和 `meeting_participants.user_upn`
- 僅更新 `owner_upn` 不會讓新使用者在前端看到該會議

**正確做法**：
```sql
-- 建立會議後，必須建立 participant 記錄
INSERT INTO meeting_participants (id, meeting_id, user_upn, role, access_source)
VALUES (gen_random_uuid()::text, '<meeting_id>', '<user_upn>', 'owner', 'upload');

-- 轉移所有權（兩步都要做）
UPDATE meetings SET owner_upn = '<new_upn>' WHERE id = '<meeting_id>';
UPDATE meeting_participants SET user_upn = '<new_upn>' WHERE meeting_id = '<meeting_id>' AND role = 'owner';
```

**錯誤做法**：
```sql
-- ❌ 只更新 owner_upn，使用者在前端仍看不到
UPDATE meetings SET owner_upn = '<new_upn>' WHERE id = '<meeting_id>';
```

---

### 2. 會議狀態機

```
PENDING → PROCESSING → TRANSCRIBED → COMPLETED
                    ↘ FAILED
                    ↘ REFINING (re-transcription)
```

`processing_stage` 為前端顯示用的細粒度狀態：
- `queued` — 已入隊等待處理
- `transcribing` — GPU 轉錄中
- `summarizing` — LLM 生成摘要中
- `null` — 已完成或失敗（不顯示進度）

---

### 3. 資料庫長交易注意事項

- `/tasks/transcription` 會開啟 10-30 分鐘的長交易（同步處理）
- 長交易會 block DDL（如 ALTER TABLE）
- 執行 migration 前，先確認無 idle-in-transaction session：
  ```sql
  SELECT pid, state, query_start, query
  FROM pg_stat_activity
  WHERE state = 'idle in transaction'
  AND query_start < now() - interval '5 minutes';
  ```

---

### 4. 測試資料建立 Checklist

建立測試會議時，確認以下步驟全部完成：

- [ ] `meetings` 表：INSERT 含正確的 `owner_upn`
- [ ] `meeting_participants` 表：INSERT 含相同的 `user_upn` + `role='owner'`
- [ ] GCS 音檔已上傳且 `audio_url` 已設定
- [ ] 透過 API 驗證目標使用者可查詢到該會議

---

## 歷史事件記錄

| 日期 | 事件 | 根因 | 修正 |
|------|------|------|------|
| 2026-06-18 | jerry_tai 看不到壓測會議 | 只更新 `owner_upn` 未更新 `meeting_participants` | UPDATE participants.user_upn |
