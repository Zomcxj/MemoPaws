use pinyin::ToPinyin;
use serde::Serialize;

use crate::model::Memo;

/// Minimum Levenshtein similarity for a fuzzy word match.
const FUZZY_THRESHOLD: f64 = 0.8;

/// Keywords shorter than this skip fuzzy matching, where a single edit would
/// otherwise match almost anything.
const FUZZY_MIN_CHARS: usize = 4;

#[derive(Clone, Debug, Serialize)]
pub struct MemoSearchResult {
    pub memo: Memo,
    pub line_number: usize,
}

pub fn search_memos(memos: &[Memo], query: &str) -> Vec<MemoSearchResult> {
    let keyword = query.trim().to_lowercase();
    memos.iter().filter_map(|memo| match_memo(memo, &keyword)).collect()
}

fn match_memo(memo: &Memo, keyword: &str) -> Option<MemoSearchResult> {
    if keyword.is_empty() {
        return Some(MemoSearchResult { memo: memo.clone(), line_number: 1 });
    }
    let fields = std::iter::once(memo.title.as_str()).chain(std::iter::once(memo.content.as_str())).chain(memo.tags.iter().map(String::as_str));
    for field in fields.clone() {
        if field.to_lowercase().contains(keyword) || pinyin_initials(field).contains(keyword) {
            return Some(MemoSearchResult { memo: memo.clone(), line_number: matching_line(memo, keyword) });
        }
    }
    if keyword.chars().count() >= FUZZY_MIN_CHARS && fields.flat_map(words).any(|word| strsim::normalized_levenshtein(keyword, &word) >= FUZZY_THRESHOLD) {
        return Some(MemoSearchResult { memo: memo.clone(), line_number: matching_line(memo, keyword) });
    }
    None
}

fn pinyin_initials(text: &str) -> String {
    text.chars().map(|character| character.to_pinyin().and_then(|pinyin| pinyin.plain().chars().next()).unwrap_or(character)).collect::<String>().to_lowercase()
}

fn words(text: &str) -> impl Iterator<Item = String> + '_ {
    text.split(|character: char| character.is_whitespace() || character == '_' || character == '-')
        .filter(|word| !word.is_empty())
        .map(str::to_lowercase)
}

fn matching_line(memo: &Memo, keyword: &str) -> usize {
    if field_matches(&memo.title, keyword) || memo.tags.iter().any(|tag| field_matches(tag, keyword)) {
        return 1;
    }
    memo.content.lines().position(|line| field_matches(line, keyword)).map(|index| index + 1).unwrap_or(1)
}

fn field_matches(field: &str, keyword: &str) -> bool {
    let lowered = field.to_lowercase();
    lowered.contains(keyword)
        || pinyin_initials(field).contains(keyword)
        || (keyword.chars().count() >= FUZZY_MIN_CHARS
            && words(&lowered).any(|word| strsim::normalized_levenshtein(keyword, &word) >= FUZZY_THRESHOLD))
}
