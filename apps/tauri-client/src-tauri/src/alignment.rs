use serde::{Serialize, Deserialize};
use std::cmp::max;

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Segment {
    pub id: usize,
    pub cn_text: String,
    pub en_text: String,
    pub start_idx: usize, 
    pub end_idx: usize,
}

pub struct ScriptEngine {
    full_cn_text: Vec<char>, 
    segments: Vec<Segment>,
    pub current_cursor: usize,
}

impl ScriptEngine {
    pub fn new(script_original: &str, script_translated: &str) -> Self {
        let orig_lines: Vec<&str> = script_original.lines().filter(|l| !l.trim().is_empty()).collect();
        let trans_lines: Vec<&str> = script_translated.lines().filter(|l| !l.trim().is_empty()).collect();
        
        let mut segments = Vec::new();
        let mut full_cn_text = Vec::new();
        let mut current_idx = 0;

        for (i, line) in orig_lines.iter().enumerate() {
            let cn = line.trim().to_string();
            let en = if i < trans_lines.len() { trans_lines[i].trim().to_string() } else { "".to_string() };
            
            let chars: Vec<char> = cn.chars().collect();
            let len = chars.len();
            full_cn_text.extend(chars);
            
            segments.push(Segment {
                id: i,
                cn_text: cn,
                en_text: en,
                start_idx: current_idx,
                end_idx: current_idx + len,
            });
            
            current_idx += len;
        }

        ScriptEngine {
            full_cn_text,
            segments,
            current_cursor: 0,
        }
    }

    /// Reset cursor to the beginning for a new recording session
    pub fn reset_cursor(&mut self) {
        self.current_cursor = 0;
        eprintln!("[ALIGN] Cursor reset to 0 for new recording session");
    }

    pub fn align(&mut self, hypothesis: &str) -> Option<Segment> {
        let window_size = 200; // Look ahead 200 chars
        let look_back = 30;    // Look back 30 chars
        let start = self.current_cursor.saturating_sub(look_back);
        let end = (self.current_cursor + window_size).min(self.full_cn_text.len());
        
        // Debug: Log window range and cursor position
        eprintln!("[ALIGN] Cursor: {}, Window: [{}, {}], Script length: {}", 
            self.current_cursor, start, end, self.full_cn_text.len());
        
        if start >= end { 
            eprintln!("[ALIGN] FAILED: Window exhausted (start >= end)");
            return None; 
        }
        
        let reference_window = &self.full_cn_text[start..end];
        let reference_preview: String = reference_window.iter().take(50).collect();
        let hypothesis_chars: Vec<char> = hypothesis.chars().collect();
        
        if hypothesis_chars.is_empty() { 
            eprintln!("[ALIGN] FAILED: Empty hypothesis");
            return None; 
        }

        eprintln!("[ALIGN] Hypothesis: '{}'", hypothesis);
        eprintln!("[ALIGN] Reference window preview: '{}...' (len: {})", reference_preview, reference_window.len());

        // Execute Smith-Waterman
        if let Some((local_end_idx, score)) = run_smith_waterman(reference_window, &hypothesis_chars) {
            let threshold = (hypothesis_chars.len() as i32) * 1; 
            let passed = score > threshold;
            eprintln!("[ALIGN] SW Score: {}, Threshold: {}, Passed: {}", score, threshold, passed);
            
            if passed {
                 let global_idx = start + local_end_idx;
                 let old_cursor = self.current_cursor;
                 
                 // Update cursor if we advanced
                 if global_idx > self.current_cursor {
                     self.current_cursor = global_idx;
                 }
                 
                 eprintln!("[ALIGN] Cursor update: {} -> {} (global_idx: {})", old_cursor, self.current_cursor, global_idx);
                 
                 let result = self.find_segment(self.current_cursor);
                 if let Some(ref seg) = result {
                     eprintln!("[ALIGN] SUCCESS: Matched segment ID {} ('{}')", seg.id, &seg.cn_text[..seg.cn_text.len().min(30)]);
                 } else {
                     eprintln!("[ALIGN] WARNING: Score passed but no segment found at cursor {}", self.current_cursor);
                 }
                 return result;
            } else {
                eprintln!("[ALIGN] FAILED: Score {} <= Threshold {}", score, threshold);
            }
        } else {
            eprintln!("[ALIGN] FAILED: Smith-Waterman returned None");
        }
        
        None
    }

    fn find_segment(&self, cursor: usize) -> Option<Segment> {
        self.segments.iter().find(|s| cursor >= s.start_idx && cursor < s.end_idx).cloned()
    }
}

fn run_smith_waterman(reference: &[char], hypothesis: &[char]) -> Option<(usize, i32)> {
    let m = reference.len();
    let n = hypothesis.len();
    
    if m == 0 || n == 0 { return None; }

    // Scoring scheme
    let match_score = 3;
    let mismatch_score = -1;
    let gap_score = -2;

    // DP Matrix: stored as flat vector for performance or just Vec<Vec>
    // Using 2 rows optimization to save memory if we only needed score, 
    // but we need the position, so full matrix or tracking max is needed.
    // Since window is small (200x50), full matrix is fine (10k ints = 40KB).
    let mut dp = vec![vec![0; n + 1]; m + 1];
    
    let mut max_score = 0;
    let mut max_pos_i = 0; // End position in reference

    for i in 1..=m {
        for j in 1..=n {
            let s_match = if reference[i-1] == hypothesis[j-1] { match_score } else { mismatch_score };
            
            let score_diag = dp[i-1][j-1] + s_match;
            let score_up = dp[i-1][j] + gap_score;
            let score_left = dp[i][j-1] + gap_score;
            
            let val = max(0, max(score_diag, max(score_up, score_left)));
            dp[i][j] = val;

            if val > max_score {
                max_score = val;
                max_pos_i = i;
            }
        }
    }

    if max_score == 0 {
        None
    } else {
        // Return 0-based index in reference window
        Some((max_pos_i.saturating_sub(1), max_score))
    }
}
