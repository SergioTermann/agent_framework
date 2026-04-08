use pyo3::prelude::*;
use rayon::prelude::*;
use rustc_hash::{FxHashMap, FxHashSet};
use std::collections::HashMap;

// ─── Stopwords ───────────────────────────────────────────────────────────────

static STOPWORDS: &[&str] = &[
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how",
    "in", "is", "it", "of", "on", "or", "that", "the", "this", "to", "with",
    "what", "when", "where", "who", "why",
];

fn build_stopwords() -> FxHashSet<&'static str> {
    STOPWORDS.iter().copied().collect()
}

// ─── Tokenizer ───────────────────────────────────────────────────────────────

/// Check if a char is CJK (Chinese/Japanese/Korean unified ideograph).
#[inline]
fn is_cjk(c: char) -> bool {
    ('\u{4e00}'..='\u{9fff}').contains(&c)
}

/// Single-pass tokenizer.
///
/// Scans the input once, collecting:
///   - English words (lowercased, len > 1, not in stopwords)
///   - Numbers (if include_numbers is true)
///   - CJK unigrams + bigrams
///
/// Returns a Vec<String> of tokens (may contain duplicates, like the Python version).
#[pyfunction]
#[pyo3(signature = (text, include_numbers=false))]
fn tokenize(text: &str, include_numbers: bool) -> Vec<String> {
    let text = text.trim();
    if text.is_empty() {
        return Vec::new();
    }

    let stopwords = build_stopwords();
    let mut tokens: Vec<String> = Vec::with_capacity(text.len() / 3);

    // Collect english/number tokens from lowercased text
    let lower = text.to_lowercase();
    let mut chars_iter = lower.chars().peekable();
    let mut word_buf = String::with_capacity(32);

    while let Some(c) = chars_iter.next() {
        if c.is_ascii_alphabetic() || c == '_' {
            word_buf.push(c);
        } else if c.is_ascii_digit() {
            if include_numbers {
                // accumulate digit run
                let mut num_buf = String::with_capacity(8);
                num_buf.push(c);
                while let Some(&next_c) = chars_iter.peek() {
                    if next_c.is_ascii_digit() {
                        num_buf.push(next_c);
                        chars_iter.next();
                    } else {
                        break;
                    }
                }
                // flush pending word first
                if word_buf.len() > 1 && !stopwords.contains(word_buf.as_str()) {
                    tokens.push(std::mem::take(&mut word_buf));
                } else {
                    word_buf.clear();
                }
                tokens.push(num_buf);
            } else {
                // flush pending word
                if word_buf.len() > 1 && !stopwords.contains(word_buf.as_str()) {
                    tokens.push(std::mem::take(&mut word_buf));
                } else {
                    word_buf.clear();
                }
            }
        } else {
            // non-alpha, non-digit: flush word
            if word_buf.len() > 1 && !stopwords.contains(word_buf.as_str()) {
                tokens.push(std::mem::take(&mut word_buf));
            } else {
                word_buf.clear();
            }
        }
    }
    // flush trailing word
    if word_buf.len() > 1 && !stopwords.contains(word_buf.as_str()) {
        tokens.push(word_buf);
    }

    // CJK pass: collect unigrams and bigrams from original text
    let mut prev_cjk: Option<char> = None;
    for c in text.chars() {
        if is_cjk(c) {
            // unigram
            let mut buf = [0u8; 4];
            tokens.push(c.encode_utf8(&mut buf).to_owned());

            // bigram with previous CJK char
            if let Some(prev) = prev_cjk {
                let mut bigram = String::with_capacity(6);
                bigram.push(prev);
                bigram.push(c);
                tokens.push(bigram);
            }
            prev_cjk = Some(c);
        } else {
            prev_cjk = None;
        }
    }

    // Dedup numbers if include_numbers (to match Python behavior)
    if include_numbers {
        let mut seen = FxHashSet::default();
        let existing: FxHashSet<String> = tokens.iter().cloned().collect();
        // numbers already added, no extra dedup needed since we push inline
        let _ = (seen, existing);
    }

    tokens
}

// ─── BM25 Batch Scoring ─────────────────────────────────────────────────────

/// Compute BM25 scores for a batch of candidate documents.
///
/// Arguments:
///   - doc_term_freqs: list of dicts (token -> term_frequency) for each document in corpus
///   - doc_lengths: list of document lengths (number of tokens)
///   - idf: dict (token -> IDF value)
///   - query_tokens: list of unique query tokens
///   - candidate_indices: list of document indices to score
///   - k1, b, avgdl: BM25 parameters
///
/// Returns: list of (doc_index, bm25_score) sorted by score descending.
#[pyfunction]
#[pyo3(signature = (doc_term_freqs, doc_lengths, idf, query_tokens, candidate_indices, k1=1.2, b=0.75, avgdl=1.0))]
fn bm25_score_batch(
    doc_term_freqs: Vec<HashMap<String, u32>>,
    doc_lengths: Vec<u32>,
    idf: HashMap<String, f32>,
    query_tokens: Vec<String>,
    candidate_indices: Vec<u32>,
    k1: f32,
    b: f32,
    avgdl: f32,
) -> Vec<(u32, f32)> {
    let safe_avgdl = if avgdl > 0.0 { avgdl } else { 1.0 };

    // Precompute query token IDF values
    let query_idf: Vec<(&str, f32)> = query_tokens
        .iter()
        .filter_map(|t| idf.get(t.as_str()).map(|&v| (t.as_str(), v)))
        .collect();

    let mut results: Vec<(u32, f32)> = candidate_indices
        .par_iter()
        .filter_map(|&idx| {
            let i = idx as usize;
            if i >= doc_term_freqs.len() {
                return None;
            }
            let tf_map = &doc_term_freqs[i];
            let dl = doc_lengths[i] as f32;

            let mut score: f32 = 0.0;
            for &(token, token_idf) in &query_idf {
                let tf = match tf_map.get(token) {
                    Some(&v) => v as f32,
                    None => continue,
                };
                let numerator = tf * (k1 + 1.0);
                let denominator = tf + k1 * (1.0 - b + b * dl / safe_avgdl);
                score += token_idf * numerator / denominator;
            }

            if score > 0.0 {
                Some((idx, score))
            } else {
                None
            }
        })
        .collect();

    results.sort_unstable_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
    results
}

// ─── Lexical Score Batch ─────────────────────────────────────────────────────

/// Compute lexical overlap scores for a batch of candidate documents.
///
/// Arguments:
///   - doc_term_freqs: list of dicts (token -> term_frequency)
///   - doc_lengths: list of document lengths
///   - query_token_freqs: dict (query_token -> frequency)
///   - query_total: sum of query token frequencies
///   - candidate_indices: list of document indices to score
///
/// Returns: list of (doc_index, lexical_score).
#[pyfunction]
#[pyo3(signature = (doc_term_freqs, doc_lengths, query_token_freqs, query_total, candidate_indices))]
fn lexical_score_batch(
    doc_term_freqs: Vec<HashMap<String, u32>>,
    doc_lengths: Vec<u32>,
    query_token_freqs: HashMap<String, u32>,
    query_total: u32,
    candidate_indices: Vec<u32>,
) -> Vec<(u32, f32)> {
    let qt = query_total.max(1) as f32;
    let query_items: Vec<(&str, u32)> = query_token_freqs
        .iter()
        .map(|(k, &v)| (k.as_str(), v))
        .collect();

    candidate_indices
        .par_iter()
        .filter_map(|&idx| {
            let i = idx as usize;
            if i >= doc_term_freqs.len() {
                return None;
            }
            let content_freq = &doc_term_freqs[i];
            let doc_len = doc_lengths[i].max(1) as f32;

            let mut overlap: u32 = 0;
            for &(token, freq) in &query_items {
                let cf = match content_freq.get(token) {
                    Some(&v) => v,
                    None => continue,
                };
                overlap += freq.min(cf);
            }

            if overlap == 0 {
                return None;
            }

            let coverage = overlap as f32 / qt;
            let density = overlap as f32 / doc_len;
            let score = 0.72 * coverage + 0.28 * (density * 8.0).min(1.0);
            let score = score.clamp(0.0, 1.0);

            if score > 0.0 {
                Some((idx, score))
            } else {
                None
            }
        })
        .collect()
}

// ─── Combined BM25 + Lexical (fused single-pass) ────────────────────────────

/// Compute both BM25 and lexical scores in a single pass over candidates.
///
/// Returns: list of (doc_index, fused_score, bm25_raw, lexical_score).
#[pyfunction]
#[pyo3(signature = (doc_term_freqs, doc_lengths, idf, query_tokens, query_token_freqs, query_total, candidate_indices, k1=1.2, b=0.75, avgdl=1.0))]
fn fused_score_batch(
    doc_term_freqs: Vec<HashMap<String, u32>>,
    doc_lengths: Vec<u32>,
    idf: HashMap<String, f32>,
    query_tokens: Vec<String>,
    query_token_freqs: HashMap<String, u32>,
    query_total: u32,
    candidate_indices: Vec<u32>,
    k1: f32,
    b: f32,
    avgdl: f32,
) -> Vec<(u32, f32, f32, f32)> {
    let safe_avgdl = if avgdl > 0.0 { avgdl } else { 1.0 };
    let qt = query_total.max(1) as f32;

    let query_idf: Vec<(&str, f32)> = query_tokens
        .iter()
        .filter_map(|t| idf.get(t.as_str()).map(|&v| (t.as_str(), v)))
        .collect();

    let query_items: Vec<(&str, u32)> = query_token_freqs
        .iter()
        .map(|(k, &v)| (k.as_str(), v))
        .collect();

    candidate_indices
        .par_iter()
        .filter_map(|&idx| {
            let i = idx as usize;
            if i >= doc_term_freqs.len() {
                return None;
            }
            let tf_map = &doc_term_freqs[i];
            let dl = doc_lengths[i] as f32;
            let safe_dl = dl.max(1.0);

            // BM25
            let mut bm25: f32 = 0.0;
            for &(token, token_idf) in &query_idf {
                let tf = match tf_map.get(token) {
                    Some(&v) => v as f32,
                    None => continue,
                };
                let numerator = tf * (k1 + 1.0);
                let denominator = tf + k1 * (1.0 - b + b * dl / safe_avgdl);
                bm25 += token_idf * numerator / denominator;
            }

            // Lexical
            let mut overlap: u32 = 0;
            for &(token, freq) in &query_items {
                let cf = match tf_map.get(token) {
                    Some(&v) => v,
                    None => continue,
                };
                overlap += freq.min(cf);
            }

            let lexical = if overlap > 0 {
                let coverage = overlap as f32 / qt;
                let density = overlap as f32 / safe_dl;
                (0.72 * coverage + 0.28 * (density * 8.0).min(1.0)).clamp(0.0, 1.0)
            } else {
                0.0
            };

            if bm25 <= 0.0 && lexical <= 0.0 {
                return None;
            }

            Some((idx, bm25, lexical))
        })
        .collect::<Vec<_>>()
        .into_iter()
        .map(|(idx, bm25, lexical)| {
            // Caller will normalize BM25 later; return raw values
            (idx, 0.0_f32, bm25, lexical)
        })
        .collect()
}

// ─── Python Module ───────────────────────────────────────────────────────────

#[pymodule]
fn retrieval_core(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(tokenize, m)?)?;
    m.add_function(wrap_pyfunction!(bm25_score_batch, m)?)?;
    m.add_function(wrap_pyfunction!(lexical_score_batch, m)?)?;
    m.add_function(wrap_pyfunction!(fused_score_batch, m)?)?;
    Ok(())
}
