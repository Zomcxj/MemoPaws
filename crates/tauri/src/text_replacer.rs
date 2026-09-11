use memopaws_config::config::TextReplacement;

const MAX_BUFFER_CHARS: usize = 64;

#[derive(Debug, Default)]
pub struct TextReplacer {
    buffer: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum KeyAction {
    PassThrough,
    Replace { backspaces: usize, replacement: String },
}

impl TextReplacer {
    pub fn process_character(&mut self, character: char) {
        self.buffer.push(character);
        let overflow = self.buffer.chars().count().saturating_sub(MAX_BUFFER_CHARS);
        if overflow > 0 {
            self.buffer = self.buffer.chars().skip(overflow).collect();
        }
    }

    pub fn process_backspace(&mut self) {
        self.buffer.pop();
    }

    pub fn clear(&mut self) {
        self.buffer.clear();
    }

    pub fn process_tab(&mut self, replacements: &[TextReplacement]) -> KeyAction {
        let matched = replacements
            .iter()
            .filter(|replacement| self.buffer.ends_with(&replacement.abbr))
            .max_by_key(|replacement| replacement.abbr.chars().count());

        match matched {
            Some(replacement) => {
                let backspaces = replacement.abbr.chars().count();
                self.buffer.clear();
                KeyAction::Replace {
                    backspaces,
                    replacement: replacement.replacement.clone(),
                }
            }
            None => {
                self.buffer.clear();
                KeyAction::PassThrough
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{KeyAction, TextReplacer};
    use memopaws_config::config::TextReplacement;

    fn rule(abbr: &str, replacement: &str) -> TextReplacement {
        TextReplacement { abbr: abbr.into(), replacement: replacement.into() }
    }

    #[test]
    fn tab_replaces_the_longest_matching_suffix() {
        let mut replacer = TextReplacer::default();
        for character in "say:brb".chars() {
            replacer.process_character(character);
        }

        assert_eq!(
            replacer.process_tab(&[rule("brb", "be right back"), rule(":brb", "BRB")]),
            KeyAction::Replace { backspaces: 4, replacement: "BRB".into() }
        );
    }

    #[test]
    fn unmatched_tab_passes_through() {
        let mut replacer = TextReplacer::default();
        replacer.process_character('x');

        assert_eq!(replacer.process_tab(&[rule("brb", "be right back")]), KeyAction::PassThrough);
        replacer.process_character('b');
        assert_eq!(replacer.process_tab(&[rule("xb", "must not match")]), KeyAction::PassThrough);
    }

    #[test]
    fn backspace_and_boundaries_clear_the_buffer() {
        let mut replacer = TextReplacer::default();
        replacer.process_character('a');
        replacer.process_character('b');
        replacer.process_backspace();
        assert_eq!(replacer.process_tab(&[rule("ab", "matched")]), KeyAction::PassThrough);

        replacer.process_character('b');
        replacer.clear();
        assert_eq!(replacer.process_tab(&[rule("ab", "matched")]), KeyAction::PassThrough);
    }

    #[test]
    fn replacement_clears_the_buffer_to_prevent_recursive_expansion() {
        let mut replacer = TextReplacer::default();
        for character in "aa".chars() {
            replacer.process_character(character);
        }
        assert!(matches!(replacer.process_tab(&[rule("aa", "bb")]), KeyAction::Replace { .. }));
        assert_eq!(replacer.process_tab(&[rule("bb", "expanded again")]), KeyAction::PassThrough);
    }

    #[test]
    fn buffer_keeps_only_the_latest_64_unicode_characters() {
        let mut replacer = TextReplacer::default();
        for character in "é".repeat(65).chars() {
            replacer.process_character(character);
        }

        assert_eq!(
            replacer.process_tab(&[rule(&"é".repeat(64), "matched")]),
            KeyAction::Replace { backspaces: 64, replacement: "matched".into() }
        );
    }
}
