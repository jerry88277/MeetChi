"""
Multi-Pass Summarization Engine (2026-06-12)

Solves: Single-shot Gemini call exceeds 65K output token limit for
complex multi-topic meetings.

Architecture (inspired by FinanceSummary project):
  Pass 0: Topic Segmentation — identify main topics + time boundaries
  Pass 1: Per-Topic Summary — full-granularity chapter per topic (parallel)
  Pass 2: Merge — combine chapters + generate meta fields (tldr, speaker, next_steps)

Each pass stays well under the 65K token output limit because:
  - Pass 0 output: ~2K tokens (just topic list)
  - Pass 1 output: ~8-15K tokens per topic (1 chapter with full sub_chapters)
  - Pass 2 output: ~5K tokens (meta fields only, no chapters)
"""

import json
import logging
import os
import time
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# Threshold: use multi-pass when transcript exceeds this length
MULTI_PASS_THRESHOLD = int(os.getenv("MULTI_PASS_THRESHOLD", "15000"))


def _get_model() -> str:
    """Get model name from llm_utils (single source of truth)."""
    from app.llm_utils import GEMINI_MODEL
    return GEMINI_MODEL


def _safe_json_parse(text: str) -> dict:
    """Parse JSON robustly — handles 'Extra data' (concatenated objects) by truncating."""
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        if "Extra data" in str(e):
            # Gemini sometimes appends a second JSON object; parse only the first
            decoder = json.JSONDecoder()
            result, _ = decoder.raw_decode(text)
            return result
        raise


def should_use_multi_pass(transcript_text: str) -> bool:
    """Determine if multi-pass summarization should be used."""
    return len(transcript_text) >= MULTI_PASS_THRESHOLD


# ============================================
# Pass 0: Topic Segmentation
# ============================================

PASS0_PROMPT = """你是會議主題分析專家。請閱讀以下會議逐字稿，識別出主要討論主題。

## 規則
1. 識別 3-8 個主要主題（依會議實際內容，不可硬湊）
2. 每個主題標記其在逐字稿中的「起始行號」和「結束行號」
3. 主題應按議題聚類，非按時間順序
4. 如果某主題特別長（佔逐字稿 40% 以上），標記 needs_split: true

## 輸出格式 (JSON)
{
  "topics": [
    {
      "id": "topic_1",
      "title": "主題名稱",
      "line_start": 0,
      "line_end": 150,
      "needs_split": false,
      "estimated_importance": "high|medium|low"
    }
  ]
}

注意：行號從 0 開始計算。逐字稿每一行是一個發言段落。
"""


def _pass0_segment_topics(client, transcript_lines: List[str]) -> List[Dict[str, Any]]:
    """Pass 0: Identify topics and their line boundaries."""
    # Provide line numbers for reference
    numbered_transcript = "\n".join(
        f"[L{i}] {line}" for i, line in enumerate(transcript_lines)
    )

    # Sample if too long (pass 0 only needs overview)
    if len(numbered_transcript) > 30000:
        step = max(1, len(transcript_lines) // 1500)
        sampled = [f"[L{i}] {transcript_lines[i]}" for i in range(0, len(transcript_lines), step)]
        numbered_transcript = "\n".join(sampled)

    prompt = f"{PASS0_PROMPT}\n\n## 逐字稿（共 {len(transcript_lines)} 行）\n\n{numbered_transcript}"

    try:
        response = client.models.generate_content(
            model=_get_model(),
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "temperature": 0.1,
                "max_output_tokens": 4096
            }
        )
        result = _safe_json_parse(response.text)
        topics = result.get("topics", [])
        logger.info(f"[MultiPass] Pass 0: identified {len(topics)} topics")
        return topics
    except Exception as e:
        logger.error(f"[MultiPass] Pass 0 failed: {e}")
        # Fallback: split evenly into 4 chunks
        chunk_size = len(transcript_lines) // 4
        return [
            {"id": f"topic_{i}", "title": f"段落 {i+1}", 
             "line_start": i * chunk_size, 
             "line_end": min((i+1) * chunk_size, len(transcript_lines) - 1),
             "needs_split": False}
            for i in range(4)
        ]


# ============================================
# Pass 1: Per-Topic Chapter Generation
# ============================================

PASS1_PROMPT_TEMPLATE = """你是專業會議記錄助手。請針對以下「{topic_title}」這個主題段落，生成一個完整的 chapter JSON。

## 輸出格式
{{
  "title": "主題名稱",
  "summary": "100-150 字摘要",
  "bullets": ["重點1 (20-30字)", "重點2", "重點3", "重點4", "重點5"],
  "key_quotes": [
    {{"text": "原音引言 ≤150字", "speaker": "SPEAKER_xx", "time": 秒數}}
  ],
  "sub_chapters": [
    {{
      "time_start": 秒數,
      "time_end": 秒數,
      "summary": "30-50 字",
      "bullets": ["要點1", "要點2", "要點3"],
      "key_quotes": [{{"text": "...", "speaker": "...", "time": 秒數}}]
    }}
  ],
  "decisions": ["此主題中的決議"],
  "action_items": ["此主題中的待辦"],
  "risks": ["此主題中的風險"]
}}

## 規則
- sub_chapters 最多 4 條，按時序排列，30-90 秒一段
- bullets 每處最多 5 條，每條 20-30 字
- key_quotes 每章最多 2 條，sub_chapter 最多 1 條
- 使用繁體中文
- SPEAKER_NN_cM 標籤保持原樣
- decisions/action_items/risks 視內容而定，沒有就空陣列
"""


def _pass1_summarize_topic(client, topic: Dict, transcript_lines: List[str]) -> Dict[str, Any]:
    """Pass 1: Generate a full chapter for a single topic."""
    line_start = topic.get("line_start", 0)
    line_end = topic.get("line_end", len(transcript_lines) - 1)
    topic_title = topic.get("title", "未命名主題")

    # Extract the relevant portion of the transcript
    topic_lines = transcript_lines[line_start:line_end + 1]
    topic_text = "\n".join(topic_lines)

    # If a single topic is too long, sample it
    if len(topic_text) > 15000:
        step = max(1, len(topic_lines) // 750)
        topic_lines = topic_lines[::step]
        topic_text = "\n".join(topic_lines)
        if len(topic_text) > 15000:
            topic_text = topic_text[:15000]

    prompt = PASS1_PROMPT_TEMPLATE.format(topic_title=topic_title)
    full_prompt = f"{prompt}\n\n## 逐字稿片段（主題：{topic_title}）\n\n{topic_text}"

    try:
        response = client.models.generate_content(
            model=_get_model(),
            contents=full_prompt,
            config={
                "response_mime_type": "application/json",
                "temperature": 0.2,
                "max_output_tokens": 16384
            }
        )

        finish_reason = ""
        try:
            finish_reason = str(response.candidates[0].finish_reason)
        except (IndexError, AttributeError):
            pass

        if "MAX_TOKENS" in finish_reason.upper():
            logger.warning(f"[MultiPass] Pass 1 topic '{topic_title}' hit MAX_TOKENS, using partial")

        result = _safe_json_parse(response.text)
        result["title"] = result.get("title", topic_title)
        logger.info(
            f"[MultiPass] Pass 1: topic '{topic_title}' → "
            f"{len(response.text)} chars, "
            f"{len(result.get('sub_chapters', []))} sub_chapters"
        )
        return result
    except Exception as e:
        logger.error(f"[MultiPass] Pass 1 failed for topic '{topic_title}': {e}")
        return {
            "title": topic_title,
            "summary": f"（摘要生成失敗：{str(e)[:50]}）",
            "bullets": [],
            "key_quotes": [],
            "sub_chapters": [],
            "decisions": [],
            "action_items": [],
            "risks": []
        }


# ============================================
# Pass 2: Merge & Generate Meta Fields
# ============================================

PASS2_PROMPT_TEMPLATE = """你是專業會議記錄助手。以下是一場會議各主題的摘要，請整合生成全會議的 meta 欄位。

## 各主題摘要
{chapters_summary}

## 輸出格式 (JSON)
{{
  "tldr": "100-150 字一句話結論（BLUF 原則）",
  "summary": "全會議 200-300 字綜合摘要",
  "speaker_contributions": [
    {{
      "speaker": "SPEAKER_xx",
      "role": "角色",
      "speak_time_pct": 0-100,
      "main_topics": ["主題1", "主題2"],
      "key_contribution": "一句話貢獻"
    }}
  ],
  "next_steps": [
    {{
      "task": "任務描述",
      "assignee": "負責人（可空）",
      "due": "YYYY-MM-DD（可空）",
      "follow_up_meeting": null
    }}
  ],
  "decisions": ["全會議決議彙整"],
  "action_items": ["全會議待辦彙整"],
  "risks": ["全會議風險彙整"]
}}

## 規則
- tldr 用 BLUF 原則：最重要的結論/決策放第一句
- speaker_contributions 最多列 5 位
- next_steps 與 action_items 去重：相同事項只列一次
- decisions/risks 從各主題 merge 後去重
- 使用繁體中文
"""


def _pass2_merge(client, chapters: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Pass 2: Merge all chapters and generate meta fields."""
    # Build a concise summary of all chapters for the merge prompt
    chapters_text_parts = []
    for i, ch in enumerate(chapters):
        part = f"### 主題 {i+1}: {ch.get('title', '未命名')}\n"
        part += f"摘要：{ch.get('summary', '無')}\n"
        bullets = ch.get("bullets", [])
        if bullets:
            part += "重點：" + " / ".join(bullets[:5]) + "\n"
        decisions = ch.get("decisions", [])
        if decisions:
            part += "決議：" + " / ".join(decisions[:3]) + "\n"
        actions = ch.get("action_items", [])
        if actions:
            part += "待辦：" + " / ".join(actions[:3]) + "\n"
        risks = ch.get("risks", [])
        if risks:
            part += "風險：" + " / ".join(risks[:3]) + "\n"
        chapters_text_parts.append(part)

    chapters_summary = "\n".join(chapters_text_parts)
    prompt = PASS2_PROMPT_TEMPLATE.format(chapters_summary=chapters_summary)

    try:
        response = client.models.generate_content(
            model=_get_model(),
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "temperature": 0.2,
                "max_output_tokens": 8192
            }
        )
        result = _safe_json_parse(response.text)
        logger.info(f"[MultiPass] Pass 2: merge complete, {len(response.text)} chars")
        return result
    except Exception as e:
        logger.error(f"[MultiPass] Pass 2 merge failed: {e}")
        # Fallback: construct minimal meta from chapters
        all_decisions = []
        all_actions = []
        all_risks = []
        for ch in chapters:
            all_decisions.extend(ch.get("decisions", []))
            all_actions.extend(ch.get("action_items", []))
            all_risks.extend(ch.get("risks", []))
        return {
            "tldr": chapters[0].get("summary", "") if chapters else "",
            "summary": " ".join(ch.get("summary", "") for ch in chapters[:3]),
            "speaker_contributions": [],
            "next_steps": [],
            "decisions": list(set(all_decisions))[:10],
            "action_items": list(set(all_actions))[:10],
            "risks": list(set(all_risks))[:10],
        }


# ============================================
# Pass 2b: Template-Specific Sections (2026-07-07 策略a)
# ============================================
# 長會議走 multi-pass 時，Pass 2 只產固定 V2 meta 欄位，模板專屬欄位（如教育訓練的
# key_learnings/qa_summary）會遺失，導致換模板毫無效果。這裡在 Pass 2 之後加一步：
# 給定各章節摘要 + 模板專屬 sections 定義，生成對應的 output_key。
# 失敗時回傳 {}，絕不影響主摘要（fail-safe）。

def _pass2b_template_sections(
    client,
    chapters: List[Dict[str, Any]],
    sections: List[Any],
) -> Dict[str, Any]:
    """Generate template-specific output_keys for long (multi-pass) meetings."""
    if not sections:
        return {}

    # Build chapter context (reuse the same concise format as Pass 2)
    parts = []
    for i, ch in enumerate(chapters):
        p = f"### 主題 {i+1}: {ch.get('title', '未命名')}\n摘要：{ch.get('summary', '無')}\n"
        bullets = ch.get("bullets", [])
        if bullets:
            p += "重點：" + " / ".join(bullets[:5]) + "\n"
        parts.append(p)
    chapters_summary = "\n".join(parts)

    # Build the requested-fields spec + a JSON skeleton
    field_lines = []
    skeleton_lines = []
    for s in sections:
        otype = getattr(s, "output_type", "list")
        json_hint = {
            "string": '"..."',
            "list": '["...", "..."]',
            "object": '{"欄位": "值"}',
        }.get(otype, '["...", "..."]')
        field_lines.append(
            f"- `{s.output_key}` ({otype})：{getattr(s, 'instruction', s.title)}"
        )
        skeleton_lines.append(f'  "{s.output_key}": {json_hint}')

    prompt = (
        "你是專業會議記錄助手。根據以下各主題摘要，生成指定欄位的內容。\n\n"
        f"## 各主題摘要\n{chapters_summary}\n\n"
        "## 需要生成的欄位\n" + "\n".join(field_lines) + "\n\n"
        "## 輸出格式（僅輸出 JSON，且只含下列 key）\n{\n"
        + ",\n".join(skeleton_lines) + "\n}\n\n"
        "## 規則\n"
        "- 只根據會議內容生成，沒有對應內容的欄位給空陣列或空字串，嚴禁瞎掰\n"
        "- 使用繁體中文\n"
    )

    try:
        response = client.models.generate_content(
            model=_get_model(),
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "temperature": 0.2,
                "max_output_tokens": 4096,
            },
        )
        result = _safe_json_parse(response.text)
        # Only keep the requested keys (defensive)
        wanted = {s.output_key for s in sections}
        cleaned = {k: v for k, v in (result or {}).items() if k in wanted}
        logger.info(f"[MultiPass] Pass 2b: generated {list(cleaned.keys())}")
        return cleaned
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[MultiPass] Pass 2b (template sections) failed, skipping: {e}")
        return {}


# ============================================
# Main Orchestrator
# ============================================

def generate_multi_pass_summary(
    client,
    transcript_text: str,
    template_name: str = "general",
    extra_instructions: str = "",
    template: Any = None,
) -> Dict[str, Any]:
    """
    Multi-pass summarization pipeline.
    
    Returns the same JSON structure as single-shot generate_summary(),
    compatible with all downstream consumers (frontend, DB, embeddings).
    """
    start_time = time.time()

    lines = transcript_text.split("\n")
    logger.info(
        f"[MultiPass] Starting multi-pass summary: "
        f"{len(lines)} lines, {len(transcript_text)} chars"
    )

    # --- Pass 0: Topic Segmentation ---
    t0 = time.time()
    topics = _pass0_segment_topics(client, lines)
    logger.info(f"[MultiPass] Pass 0 completed in {time.time()-t0:.1f}s")

    if not topics:
        return {"error": "Pass 0 failed to identify topics"}

    # --- Pass 1: Per-Topic Summary (parallel via ThreadPoolExecutor) ---
    t1 = time.time()
    chapters = []

    # Use ThreadPoolExecutor for parallel Gemini calls
    max_workers = min(len(topics), 4)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(_pass1_summarize_topic, client, topic, lines)
            for topic in topics
        ]
        for future in futures:
            try:
                chapter = future.result(timeout=120)
                chapters.append(chapter)
            except Exception as e:
                logger.error(f"[MultiPass] Pass 1 thread failed: {e}")

    logger.info(
        f"[MultiPass] Pass 1 completed in {time.time()-t1:.1f}s "
        f"({len(chapters)}/{len(topics)} chapters)"
    )

    if not chapters:
        return {"error": "Pass 1 failed to generate any chapters"}

    # --- Pass 2: Merge & Meta ---
    t2 = time.time()
    meta = _pass2_merge(client, chapters)
    logger.info(f"[MultiPass] Pass 2 completed in {time.time()-t2:.1f}s")

    # --- Pass 2b: Template-specific sections (2026-07-07 策略a) ---
    # 只針對模板專屬（非 V2 通用）欄位生成；general 模板沒有專屬欄位 → 跳過。
    template_extra: Dict[str, Any] = {}
    try:
        from app.template_engine import get_template_specific_sections
        specific_sections = get_template_specific_sections(template)
        if specific_sections:
            t2b = time.time()
            template_extra = _pass2b_template_sections(client, chapters, specific_sections)
            logger.info(f"[MultiPass] Pass 2b completed in {time.time()-t2b:.1f}s")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[MultiPass] Pass 2b skipped due to error: {e}")

    # --- Assemble final output (same schema as single-shot) ---
    # Strip per-chapter decisions/actions/risks (they're merged into top-level)
    clean_chapters = []
    for ch in chapters:
        clean_ch = {
            "title": ch.get("title", ""),
            "summary": ch.get("summary", ""),
            "bullets": ch.get("bullets", []),
            "key_quotes": ch.get("key_quotes", []),
            "sub_chapters": ch.get("sub_chapters", []),
        }
        clean_chapters.append(clean_ch)

    # Collect all key_quotes for top-level
    all_quotes = []
    for ch in chapters:
        all_quotes.extend(ch.get("key_quotes", []))
        for sc in ch.get("sub_chapters", []):
            all_quotes.extend(sc.get("key_quotes", []))

    result = {
        "tldr": meta.get("tldr", ""),
        "summary": meta.get("summary", ""),
        "chapters": clean_chapters,
        "speaker_contributions": meta.get("speaker_contributions", []),
        "next_steps": meta.get("next_steps", []),
        "key_quotes": all_quotes[:10],
        "decisions": meta.get("decisions", []),
        "action_items": meta.get("action_items", []),
        "risks": meta.get("risks", []),
    }

    # 模板專屬欄位併入頂層（不覆蓋既有 V2 通用欄位）
    for k, v in template_extra.items():
        if k not in result:
            result[k] = v

    total_time = time.time() - start_time
    logger.info(
        f"[MultiPass] Complete: {len(chapters)} chapters, "
        f"{sum(len(ch.get('sub_chapters',[])) for ch in chapters)} sub_chapters, "
        f"total {total_time:.1f}s "
        f"(P0={time.time()-start_time - (time.time()-t0):.0f}s, "
        f"P1={time.time()-t1 - (time.time()-t2):.0f}s, "
        f"P2={time.time()-t2:.0f}s)"
    )

    return result
