use std::{collections::HashMap, sync::Mutex};

#[derive(Clone)]
struct PinData { image: Vec<u8>, radius: f64 }

#[derive(Default)]
pub struct Pins {
    next: u64,
    images: HashMap<String, PinData>,
    capture_visible: Option<bool>,
    restore_visible: Option<bool>,
}

impl Pins {
    fn begin(&mut self, visible: bool) -> Result<(), String> {
        if self.capture_visible.is_some() { return Err("capture is already active".into()); }
        self.capture_visible = Some(visible);
        Ok(())
    }
    fn insert(&mut self, data: PinData) -> String {
        self.next += 1;
        let label = format!("pin-{}", self.next);
        self.restore_visible.get_or_insert(self.capture_visible.unwrap_or(false));
        self.images.insert(label.clone(), data);
        label
    }
    fn remove(&mut self, label: &str) -> Option<bool> {
        self.images.remove(label)?;
        if self.images.is_empty() && self.capture_visible.is_none() {
            self.restore_visible.take()
        } else { None }
    }
    fn finish(&mut self, outcome: &str) -> Result<bool, String> {
        if !matches!(outcome, "pin" | "confirm" | "cancel") {
            return Err("invalid capture outcome".into());
        }
        let before = self.capture_visible.take().ok_or("capture is not active")?;
        let pending = if self.images.is_empty() { self.restore_visible.take() } else { None };
        Ok(match outcome {
            "confirm" => true,
            "pin" if !self.images.is_empty() => false,
            "cancel" if !self.images.is_empty() => before,
            _ => pending.unwrap_or(true),
        })
    }
}

pub type PinState = Mutex<Pins>;

#[cfg(test)]
mod tests {
    use super::*;
    fn data() -> PinData { PinData { image: vec![1], radius: 12.0 } }
    #[test]
    fn independent_close_restores_only_last() {
        let mut pins = Pins::default();
        pins.begin(true).unwrap();
        let a = pins.insert(data());
        assert!(!pins.finish("pin").unwrap());
        pins.begin(false).unwrap();
        let b = pins.insert(data());
        assert!(!pins.finish("pin").unwrap());
        assert_ne!(a, b);
        assert_eq!(pins.remove(&a), None);
        assert!(pins.images.contains_key(&b));
        assert_eq!(pins.remove(&b), Some(true));
        assert_eq!(pins.remove(&b), None);
    }
    #[test]
    fn hidden_first_pin_stays_hidden_after_last_close() {
        let mut pins = Pins::default();
        pins.begin(false).unwrap();
        let a = pins.insert(data());
        pins.finish("pin").unwrap();
        assert_eq!(pins.remove(&a), Some(false));
    }
    #[test]
    fn close_during_capture_preserves_first_visibility() {
        let mut pins = Pins::default();
        pins.begin(true).unwrap();
        let a = pins.insert(data());
        pins.finish("pin").unwrap();
        pins.begin(false).unwrap();
        assert_eq!(pins.remove(&a), None);
        let b = pins.insert(data());
        assert!(!pins.finish("pin").unwrap());
        assert_eq!(pins.remove(&b), Some(true));
    }
    #[test]
    fn failed_creation_can_be_rolled_back_before_capture_finishes() {
        let mut pins = Pins::default();
        pins.begin(true).unwrap();
        let a = pins.insert(data());
        pins.remove(&a);
        assert!(pins.finish("cancel").unwrap());
        assert!(pins.restore_visible.is_none());
        assert!(pins.begin(false).is_ok());
        assert!(pins.begin(true).is_err());
    }
    #[test]
    fn invalid_or_duplicate_finish_does_not_consume_a_new_session() {
        let mut pins = Pins::default();
        pins.begin(true).unwrap();
        assert!(pins.finish("invalid").is_err());
        assert!(pins.finish("confirm").unwrap());
        assert!(pins.finish("confirm").is_err());
    }
}
