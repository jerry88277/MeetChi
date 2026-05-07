"""
Script Aligner — Smith-Waterman based real-time transcript alignment.

Provides:
  - ScriptAligner: single-zone character-level alignment
  - MultiSpeakerScriptAligner: multi-zone (per-speaker) alignment with
    cross-zone detection and auto-advance

Extracted from main.py as part of the refactor; logic unchanged.
"""

import logging
import re

logger = logging.getLogger(__name__)


class ScriptAligner:
    """
    Smith-Waterman Based Script Aligner for real-time alignment.
    
    Features:
    1. Smith-Waterman local alignment algorithm
    2. Character-level flattened script with segment mapping
    3. Multi-segment matching for long ASR outputs
    4. Global resync when consecutive matches fail
    """
    
    # Smith-Waterman scoring parameters
    MATCH_SCORE = 3
    MISMATCH_SCORE = -1
    GAP_SCORE = -2
    
    # Alignment parameters
    NORMAL_WINDOW_BACK = 20       # Characters to search backward
    NORMAL_WINDOW_FORWARD = 600   # Characters to search forward (increased for slow speech)
    MAX_CONSECUTIVE_FAILURES = 3  # Trigger global resync after this many failures (reduced for faster recovery)
    MIN_MATCH_SCORE = 6           # Minimum score to consider a valid match (lowered for short fragments)
    
    def __init__(self):
        self.segments = []            # List of {source, target, start_idx, end_idx}
        self.full_cn_text = ""        # Flattened Chinese text
        self.char_to_segment = []     # Maps char index -> segment index
        self.current_cursor = 0       # Current character position
        self.consecutive_failures = 0 # Track failures for global resync
        self.last_matched_segments = set()  # Avoid duplicate segment sends
    
    def load_script(self, script_text: str):
        """
        Parse script text into segments and create flattened character mapping.
        Format: "[N] Chinese text ||| English text"
        """
        self.segments = []
        self.full_cn_text = ""
        self.char_to_segment = []
        self.current_cursor = 0
        self.consecutive_failures = 0
        self.last_matched_segments = set()
        
        if not script_text:
            return
        
        lines = script_text.split('\n')
        for line in lines:
            line = line.strip()
            if not line or "|||" not in line:
                continue
            
            parts = line.split("|||")
            if len(parts) >= 2:
                source = parts[0].strip()
                target = parts[1].strip()
                
                # Remove numbering: [1], 1., (1), etc.
                clean_source = re.sub(r'^[\[\(]?\d+[\]\)\.]?\s*', '', source)
                
                # Remove punctuation for matching
                normalized = self._normalize(clean_source)
                
                if not normalized:
                    continue
                
                start_idx = len(self.full_cn_text)
                end_idx = start_idx + len(normalized)
                
                self.segments.append({
                    'index': len(self.segments),
                    'source': clean_source,
                    'target': target,
                    'normalized': normalized,
                    'start_idx': start_idx,
                    'end_idx': end_idx
                })
                
                # Build character-to-segment mapping
                for _ in range(len(normalized)):
                    self.char_to_segment.append(len(self.segments) - 1)
                
                self.full_cn_text += normalized
    
    def _normalize(self, text: str) -> str:
        """Remove punctuation and whitespace, keep Chinese/English characters."""
        return re.sub(r'[\s,.\?!，。？！、：；""''「」（）\u3000\-—]+', '', text)
    
    def has_script(self):
        return len(self.segments) > 0 and len(self.full_cn_text) > 0
    
    # Common homophones/similar characters in Chinese for tolerance matching
    HOMOPHONES = {
        '諸': {'祝', '竹', '朱'}, '祝': {'諸', '竹', '朱'},
        '夜': {'一', '億'}, '一': {'夜'},
        '走得': {'走了'}, '走了': {'走得'},
        '的': {'得', '地'}, '得': {'的', '地'}, '地': {'的', '得'},
        '事': {'是', '式'}, '是': {'事', '式'},
        '晚': {'碗', '萬'}, '萬': {'晚'},
    }
    
    def _is_homophone(self, char1: str, char2: str) -> bool:
        """Check if two characters are homophones (similar sounds)"""
        if char1 == char2:
            return True
        homophones1 = self.HOMOPHONES.get(char1, set())
        return char2 in homophones1
    
    def smith_waterman(self, query: str, target: str):
        """
        Smith-Waterman local alignment algorithm.
        Returns: (best_start, best_end, best_score) - position in target where query best matches
        """
        if not query or not target:
            return (0, 0, 0)
        
        m, n = len(query), len(target)
        
        # Initialize scoring matrix
        H = [[0] * (n + 1) for _ in range(m + 1)]
        
        best_score = 0
        best_end = 0
        
        # Fill matrix
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                q_char = query[i-1]
                t_char = target[j-1]
                
                # Match/Mismatch with homophone tolerance
                if q_char == t_char:
                    diag = H[i-1][j-1] + self.MATCH_SCORE
                elif self._is_homophone(q_char, t_char):
                    # Partial match for homophones (75% of match score)
                    diag = H[i-1][j-1] + int(self.MATCH_SCORE * 0.75)
                else:
                    diag = H[i-1][j-1] + self.MISMATCH_SCORE
                
                # Gap scores
                up = H[i-1][j] + self.GAP_SCORE
                left = H[i][j-1] + self.GAP_SCORE
                
                # Smith-Waterman: reset to 0 if negative
                H[i][j] = max(0, diag, up, left)
                
                # Track best score position
                if H[i][j] > best_score:
                    best_score = H[i][j]
                    best_end = j
        
        # Traceback to find start position
        best_start = best_end
        if best_score > 0:
            # Simple traceback: find where the match started
            i, j = m, best_end
            while i > 0 and j > 0 and H[i][j] > 0:
                if query[i-1] == target[j-1]:
                    i -= 1
                    j -= 1
                elif H[i-1][j] >= H[i][j-1]:
                    i -= 1
                else:
                    j -= 1
            best_start = j
        
        return (best_start, best_end, best_score)
    
    def find_match(self, transcript_text: str, threshold: float = 0.5, alignment_mode: bool = False):
        """
        Find best matching segment(s) using Smith-Waterman algorithm.
        
        Args:
            transcript_text: The ASR transcript to match
            threshold: Base matching threshold (default 0.5)
            alignment_mode: If True, use a more relaxed threshold (0.30) for slow speech
        
        Returns: dict with matched segments, or None if no match
        When score is below threshold but above MIN_MATCH_SCORE, returns with low_confidence=True
        """
        if not transcript_text or not self.has_script():
            return None
        
        normalized_input = self._normalize(transcript_text)
        
        # Use lower threshold in alignment mode to handle slow speech fragments
        effective_threshold = 0.30 if alignment_mode else threshold
        
        if len(normalized_input) < 3:
            return None
        
        # Determine search window
        if self.consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
            # Global resync: search entire script
            search_start = 0
            search_end = len(self.full_cn_text)
            search_window = self.full_cn_text
            is_global_search = True
        else:
            # Normal windowed search
            search_start = max(0, self.current_cursor - self.NORMAL_WINDOW_BACK)
            search_end = min(len(self.full_cn_text), self.current_cursor + self.NORMAL_WINDOW_FORWARD)
            search_window = self.full_cn_text[search_start:search_end]
            is_global_search = False
        
        if not search_window:
            return None
        
        # Run Smith-Waterman
        match_start, match_end, score = self.smith_waterman(normalized_input, search_window)
        
        # Convert to global indices
        global_start = search_start + match_start
        global_end = search_start + match_end
        
        # Calculate normalized score (as percentage of query length)
        max_possible_score = len(normalized_input) * self.MATCH_SCORE
        normalized_score = score / max_possible_score if max_possible_score > 0 else 0
        
        # Determine confidence level
        low_confidence = False
        if normalized_score < effective_threshold:
            if score < self.MIN_MATCH_SCORE:
                # Score too low, truly no match
                self.consecutive_failures += 1
                return None
            else:
                # Score below threshold but still reasonable - mark as low confidence
                low_confidence = True
                self.consecutive_failures += 1
                # Don't return None - proceed with best guess
        else:
            # Good match - reset failure counter
            self.consecutive_failures = 0
        
        # Find all segments covered by this match
        matched_segment_indices = set()
        for char_idx in range(global_start, min(global_end, len(self.char_to_segment))):
            seg_idx = self.char_to_segment[char_idx]
            matched_segment_indices.add(seg_idx)
        
        if not matched_segment_indices:
            # Fallback: use the next expected segment
            next_seg_idx = 0
            for seg in self.segments:
                if seg['start_idx'] >= self.current_cursor:
                    next_seg_idx = seg['index']
                    break
            matched_segment_indices = {next_seg_idx}
        
        # Filter out already-matched segments (avoid duplicates)
        # But for low_confidence matches, allow re-showing recent segments
        if low_confidence:
            new_segments = matched_segment_indices
        else:
            new_segments = matched_segment_indices - self.last_matched_segments
        
        if not new_segments:
            # All segments already matched, but still update cursor
            self.current_cursor = global_end
            return None
        
        # Update state
        if not low_confidence:
            self.last_matched_segments = matched_segment_indices
            self.current_cursor = global_end
        # For low_confidence, keep cursor but don't update last_matched
        
        # Get the segment data for new matches
        matched_segments = []
        for seg_idx in sorted(new_segments):
            if 0 <= seg_idx < len(self.segments):
                seg = self.segments[seg_idx]
                matched_segments.append({
                    'index': seg_idx,
                    'source': seg['source'],
                    'target': seg['target'],
                    'score': normalized_score,
                    'low_confidence': low_confidence
                })
        
        if not matched_segments:
            return None
        
        # Return first segment for backward compatibility, but include all
        first_match = matched_segments[0]
        return {
            'source': first_match['source'],
            'target': first_match['target'],
            'score': normalized_score,
            'index': first_match['index'],
            'all_matches': matched_segments,  # All matched segments
            'is_global_resync': is_global_search,
            'cursor_position': self.current_cursor,
            'low_confidence': low_confidence  # NEW: flag for uncertain matches
        }
    
    def reset_position(self):
        """Reset alignment state to beginning."""
        self.current_cursor = 0
        self.consecutive_failures = 0
        self.last_matched_segments = set()


class MultiSpeakerScriptAligner(ScriptAligner):
    """
    Extended Script Aligner for multi-speaker scenarios.
    
    Features:
    1. Speaker zone parsing (===SPEAKER:xxx===)
    2. Zone-restricted search (prevents cross-speaker matching)
    3. Auto-advance to next speaker at zone boundary
    4. Manual speaker switching support
    """
    
    # Auto-advance threshold (percentage of zone traversed)
    AUTO_ADVANCE_THRESHOLD = 0.90
    # Characters of next zone to include in search for cross-zone detection
    NEXT_ZONE_LOOKAHEAD = 100
    
    def __init__(self):
        super().__init__()
        self.speaker_zones = []  # [(start_idx, end_idx, speaker_name, segment_range)]
        self.current_zone_index = 0
        self.lock_to_current_zone = True  # Prevent cross-speaker matching
        self.zone_final_segments_matched = set()  # Track which final segments have been matched
    
    def load_script(self, script_text: str):
        """
        Parse script with optional ===SPEAKER:xxx=== markers.
        Falls back to single-speaker mode if no markers found.
        """
        self.segments = []
        self.full_cn_text = ""
        self.char_to_segment = []
        self.current_cursor = 0
        self.consecutive_failures = 0
        self.last_matched_segments = set()
        self.speaker_zones = []
        self.current_zone_index = 0
        
        if not script_text:
            return
        
        # Check if multi-speaker format
        if "===SPEAKER:" in script_text:
            self._load_multi_speaker_script(script_text)
        else:
            # Fallback to single-speaker mode
            super().load_script(script_text)
            if self.segments:
                self.speaker_zones = [(0, len(self.full_cn_text), "Default", (0, len(self.segments)))]
    
    def _load_multi_speaker_script(self, script_text: str):
        """Parse multi-speaker script with ===SPEAKER:xxx=== markers."""
        # Split by speaker markers
        parts = re.split(r'===SPEAKER:([^=]+)===', script_text)
        
        # parts will be: ['', 'Speaker1', 'content1', 'Speaker2', 'content2', ...]
        current_speaker = "Default"
        
        for i, part in enumerate(parts):
            part = part.strip()
            if not part:
                continue
            
            # Odd indices are speaker names, even indices are content
            if i % 2 == 1:
                current_speaker = part
            else:
                # This is content for current_speaker
                zone_start_idx = len(self.full_cn_text)
                segment_start = len(self.segments)
                
                # Parse lines in this speaker's section
                lines = part.split('\n')
                for line in lines:
                    line = line.strip()
                    if not line or "|||" not in line:
                        continue
                    
                    line_parts = line.split("|||")
                    if len(line_parts) >= 2:
                        source = line_parts[0].strip()
                        target = line_parts[1].strip()
                        
                        # Remove numbering
                        clean_source = re.sub(r'^[\[\(]?\d+[\]\)\.:]?\s*', '', source)
                        normalized = self._normalize(clean_source)
                        
                        if not normalized:
                            continue
                        
                        start_idx = len(self.full_cn_text)
                        end_idx = start_idx + len(normalized)
                        
                        self.segments.append({
                            'index': len(self.segments),
                            'source': clean_source,
                            'target': target,
                            'normalized': normalized,
                            'start_idx': start_idx,
                            'end_idx': end_idx,
                            'speaker': current_speaker  # Track speaker per segment
                        })
                        
                        for _ in range(len(normalized)):
                            self.char_to_segment.append(len(self.segments) - 1)
                        
                        self.full_cn_text += normalized
                
                zone_end_idx = len(self.full_cn_text)
                segment_end = len(self.segments)
                
                if zone_end_idx > zone_start_idx:
                    self.speaker_zones.append((
                        zone_start_idx, 
                        zone_end_idx, 
                        current_speaker,
                        (segment_start, segment_end)
                    ))
        
        logger.info(f"[MultiSpeaker] Loaded {len(self.speaker_zones)} speaker zones, {len(self.segments)} total segments")
        for i, zone in enumerate(self.speaker_zones):
            logger.info(f"  Zone {i}: {zone[2]} (chars {zone[0]}-{zone[1]}, segments {zone[3][0]}-{zone[3][1]})")
    
    def get_current_speaker(self) -> str:
        """Get the name of the current active speaker."""
        if self.speaker_zones and 0 <= self.current_zone_index < len(self.speaker_zones):
            return self.speaker_zones[self.current_zone_index][2]
        return "Unknown"
    
    def get_zone_progress(self) -> float:
        """Get progress within current zone (0.0 to 1.0)."""
        if not self.speaker_zones or self.current_zone_index >= len(self.speaker_zones):
            return 0.0
        
        zone = self.speaker_zones[self.current_zone_index]
        zone_start, zone_end = zone[0], zone[1]
        zone_length = zone_end - zone_start
        
        if zone_length == 0:
            return 1.0
        
        progress = (self.current_cursor - zone_start) / zone_length
        return max(0.0, min(1.0, progress))
    
    def advance_speaker(self) -> bool:
        """Manually advance to next speaker zone. Returns True if successful."""
        if self.current_zone_index < len(self.speaker_zones) - 1:
            self.current_zone_index += 1
            new_zone = self.speaker_zones[self.current_zone_index]
            self.current_cursor = new_zone[0]
            self.consecutive_failures = 0
            self.last_matched_segments = set()
            self.zone_final_segments_matched.clear()  # Reset final segment tracking
            logger.info(f"[MultiSpeaker] Advanced to zone {self.current_zone_index}: {new_zone[2]}")
            return True
        return False
    
    def previous_speaker(self) -> bool:
        """Go back to previous speaker zone. Returns True if successful."""
        if self.current_zone_index > 0:
            self.current_zone_index -= 1
            prev_zone = self.speaker_zones[self.current_zone_index]
            self.current_cursor = prev_zone[0]
            self.consecutive_failures = 0
            self.last_matched_segments = set()
            self.zone_final_segments_matched.clear()  # Reset final segment tracking
            logger.info(f"[MultiSpeaker] Returned to zone {self.current_zone_index}: {prev_zone[2]}")
            return True
        return False
    
    def find_match(self, transcript_text: str, threshold: float = 0.5, alignment_mode: bool = False):
        """
        Find match with zone-restricted search.
        Prevents cross-speaker matching when lock_to_current_zone is True.
        
        Args:
            transcript_text: The ASR transcript to match
            threshold: Base matching threshold (default 0.5)
            alignment_mode: If True, use a more relaxed threshold (0.30) for slow speech
        """
        if not transcript_text or not self.has_script():
            return None
        
        normalized_input = self._normalize(transcript_text)
        
        # Use lower threshold in alignment mode to handle slow speech fragments
        effective_threshold = 0.30 if alignment_mode else threshold
        
        if len(normalized_input) < 3:
            return None
        
        # Determine search range based on zone locking
        if self.lock_to_current_zone and self.speaker_zones:
            if self.current_zone_index >= len(self.speaker_zones):
                # All zones exhausted
                return None
            
            zone = self.speaker_zones[self.current_zone_index]
            zone_start, zone_end, speaker_name, _ = zone
            
            # Restrict search to current zone (+ next zone lookahead for cross-zone detection)
            next_zone_start = None
            if self.current_zone_index < len(self.speaker_zones) - 1:
                next_zone = self.speaker_zones[self.current_zone_index + 1]
                next_zone_start = next_zone[0]
            
            if self.consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
                # Global resync within zone only
                search_start = zone_start
                search_end = zone_end
                is_global_search = True
            else:
                # Normal windowed search within zone + next zone lookahead
                search_start = max(zone_start, self.current_cursor - self.NORMAL_WINDOW_BACK)
                base_search_end = min(zone_end, self.current_cursor + self.NORMAL_WINDOW_FORWARD)
                
                # Extend search to include next zone's first segment area
                if next_zone_start is not None:
                    search_end = min(
                        next_zone_start + self.NEXT_ZONE_LOOKAHEAD,
                        len(self.full_cn_text)
                    )
                else:
                    search_end = base_search_end
                is_global_search = False
        else:
            # No zone locking - use parent class behavior
            return super().find_match(transcript_text, threshold)
        
        search_window = self.full_cn_text[search_start:search_end]
        if not search_window:
            # Check if we should auto-advance
            if self.get_zone_progress() >= self.AUTO_ADVANCE_THRESHOLD:
                if self.advance_speaker():
                    # Retry with new zone
                    return self.find_match(transcript_text, threshold)
            return None
        
        # Run Smith-Waterman on restricted range
        match_start, match_end, score = self.smith_waterman(normalized_input, search_window)
        
        global_start = search_start + match_start
        global_end = search_start + match_end
        
        max_possible_score = len(normalized_input) * self.MATCH_SCORE
        normalized_score = score / max_possible_score if max_possible_score > 0 else 0
        
        # Cross-zone detection: if match falls in next zone's range, auto-advance
        if (next_zone_start is not None and 
            global_start >= next_zone_start and 
            normalized_score >= effective_threshold):
            logger.info(f"[MultiSpeaker] Cross-zone match detected at position {global_start} (next zone starts at {next_zone_start})")
            logger.info(f"[MultiSpeaker] User started reading next speaker's script -> auto-advance")
            self.zone_final_segments_matched.clear()
            self.advance_speaker()
            # Re-run match in new zone context
            return self.find_match(transcript_text, threshold, alignment_mode)
        
        low_confidence = False
        if normalized_score < effective_threshold:
            if score < self.MIN_MATCH_SCORE:
                self.consecutive_failures += 1
                return None
            else:
                low_confidence = True
                self.consecutive_failures += 1
        else:
            self.consecutive_failures = 0
        
        # Find matched segments
        matched_segment_indices = set()
        for char_idx in range(global_start, min(global_end, len(self.char_to_segment))):
            seg_idx = self.char_to_segment[char_idx]
            matched_segment_indices.add(seg_idx)
        
        if not matched_segment_indices:
            return None
        
        if low_confidence:
            new_segments = matched_segment_indices
        else:
            new_segments = matched_segment_indices - self.last_matched_segments
        
        if not new_segments:
            self.current_cursor = global_end
            # Check for auto-advance
            if self.get_zone_progress() >= self.AUTO_ADVANCE_THRESHOLD:
                self.advance_speaker()
            return None
        
        if not low_confidence:
            self.last_matched_segments = matched_segment_indices
            self.current_cursor = global_end
        
        # Get segment data
        matched_segments = []
        for seg_idx in sorted(new_segments):
            if 0 <= seg_idx < len(self.segments):
                seg = self.segments[seg_idx]
                matched_segments.append({
                    'index': seg_idx,
                    'source': seg['source'],
                    'target': seg['target'],
                    'score': normalized_score,
                    'low_confidence': low_confidence,
                    'speaker': seg.get('speaker', 'Unknown')
                })
        
        if not matched_segments:
            return None
        
        first_match = matched_segments[0]
        
        # Fallback auto-advance: if cursor reaches 95% of zone without cross-zone trigger
        # This handles edge cases where user finishes zone but doesn't immediately start next
        if (self.speaker_zones and 
            self.current_zone_index < len(self.speaker_zones) and
            self.get_zone_progress() >= 0.95):
            logger.info(f"[MultiSpeaker] Fallback auto-advance: zone progress >= 95%")
            self.zone_final_segments_matched.clear()
            self.advance_speaker()
        
        return {
            'source': first_match['source'],
            'target': first_match['target'],
            'score': normalized_score,
            'index': first_match['index'],
            'speaker': first_match['speaker'],
            'all_matches': matched_segments,
            'is_global_resync': is_global_search,
            'cursor_position': self.current_cursor,
            'low_confidence': low_confidence,
            'current_speaker': self.get_current_speaker(),
            'zone_progress': self.get_zone_progress()
        }
    
    def reset_position(self):
        """Reset alignment state to beginning of first zone."""
        super().reset_position()
        self.current_zone_index = 0
        if self.speaker_zones:
            self.current_cursor = self.speaker_zones[0][0]
