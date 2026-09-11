#[cfg(not(windows))]
pub fn init(_: std::sync::Arc<crate::commands::TextReplacerState>) -> Result<(), String> {
    Ok(())
}

#[cfg(windows)]
mod platform {
    use std::sync::{Arc, OnceLock};

    use windows_sys::Win32::Foundation::{LPARAM, LRESULT, WPARAM};
    use windows_sys::Win32::UI::Input::KeyboardAndMouse::{
        GetKeyboardState, SendInput, ToUnicode, INPUT, INPUT_0, INPUT_KEYBOARD,
        KEYBDINPUT, KEYEVENTF_KEYUP, KEYEVENTF_UNICODE, VK_BACK, VK_RETURN, VK_SPACE, VK_TAB,
    };
    use windows_sys::Win32::UI::WindowsAndMessaging::{
        CallNextHookEx, SetWindowsHookExW, HC_ACTION, KBDLLHOOKSTRUCT, WH_KEYBOARD_LL, WM_KEYDOWN,
        WM_SYSKEYDOWN,
    };
    use windows_sys::Win32::System::LibraryLoader::GetModuleHandleW;

    use crate::commands::TextReplacerState;
    use crate::text_replacer::KeyAction;

    const SYNTHETIC_INPUT_MARKER: usize = 0x4D50_5452;
    static STATE: OnceLock<Arc<TextReplacerState>> = OnceLock::new();
    static HOOK: OnceLock<isize> = OnceLock::new();

    pub fn init(state: Arc<TextReplacerState>) -> Result<(), String> {
        let _ = STATE.set(state);
        let module = unsafe { GetModuleHandleW(std::ptr::null()) };
        if module.is_null() {
            return Err("failed to get the application module handle".to_string());
        }
        let hook = unsafe { SetWindowsHookExW(WH_KEYBOARD_LL, Some(keyboard_hook), module, 0) };
        if hook.is_null() {
            return Err("failed to install text replacement keyboard hook".to_string());
        }
        let _ = HOOK.set(hook as isize);
        Ok(())
    }

    unsafe extern "system" fn keyboard_hook(code: i32, wparam: WPARAM, lparam: LPARAM) -> LRESULT {
        if code != HC_ACTION as i32 || (wparam != WM_KEYDOWN as usize && wparam != WM_SYSKEYDOWN as usize) {
            return CallNextHookEx(std::ptr::null_mut(), code, wparam, lparam);
        }
        let key = *(lparam as *const KBDLLHOOKSTRUCT);
        if key.dwExtraInfo == SYNTHETIC_INPUT_MARKER {
            return CallNextHookEx(std::ptr::null_mut(), code, wparam, lparam);
        }
        let Some(state) = STATE.get() else { return CallNextHookEx(std::ptr::null_mut(), code, wparam, lparam); };
        let mut machine = match state.machine.lock() { Ok(machine) => machine, Err(_) => return CallNextHookEx(std::ptr::null_mut(), code, wparam, lparam) };
        if key.vkCode == VK_TAB as u32 {
            let action = {
                let rules = match state.rules.lock() { Ok(rules) => rules, Err(_) => return CallNextHookEx(std::ptr::null_mut(), code, wparam, lparam) };
                machine.process_tab(&rules)
            };
            drop(machine);
            if let KeyAction::Replace { backspaces, replacement } = action {
                send_replacement(backspaces, &replacement);
                return 1;
            }
            return CallNextHookEx(std::ptr::null_mut(), code, wparam, lparam);
        }
        match key.vkCode {
            value if value == VK_BACK as u32 => machine.process_backspace(),
            value if value == VK_SPACE as u32 || value == VK_RETURN as u32 => machine.clear(),
            _ => {
                if let Some(characters) = key_characters(key.vkCode, key.scanCode) {
                    for character in characters.chars() {
                        machine.process_character(character);
                    }
                }
            }
        }
        CallNextHookEx(std::ptr::null_mut(), code, wparam, lparam)
    }

    unsafe fn key_characters(vk_code: u32, scan_code: u32) -> Option<String> {
        let mut keyboard_state = [0u8; 256];
        if GetKeyboardState(keyboard_state.as_mut_ptr()) == 0 { return None; }
        let mut utf16 = [0u16; 8];
        let count = ToUnicode(vk_code, scan_code, keyboard_state.as_ptr(), utf16.as_mut_ptr(), utf16.len() as i32, 0);
        if count <= 0 { return None; }
        String::from_utf16(&utf16[..count as usize]).ok().map(|characters| characters.chars().filter(|character| !character.is_control()).collect()).filter(|characters: &String| !characters.is_empty())
    }

    unsafe fn send_replacement(backspaces: usize, replacement: &str) {
        let mut inputs = Vec::with_capacity(backspaces * 2 + replacement.encode_utf16().count() * 2);
        for _ in 0..backspaces {
            inputs.push(key_input(VK_BACK as u16, 0));
            inputs.push(key_input(VK_BACK as u16, KEYEVENTF_KEYUP));
        }
        for unit in replacement.encode_utf16() {
            inputs.push(key_input(unit, KEYEVENTF_UNICODE));
            inputs.push(key_input(unit, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP));
        }
        SendInput(inputs.len() as u32, inputs.as_ptr(), std::mem::size_of::<INPUT>() as i32);
    }

    fn key_input(code: u16, flags: u32) -> INPUT {
        INPUT { r#type: INPUT_KEYBOARD, Anonymous: INPUT_0 { ki: KEYBDINPUT { wVk: if flags & KEYEVENTF_UNICODE != 0 { 0 } else { code }, wScan: if flags & KEYEVENTF_UNICODE != 0 { code } else { 0 }, dwFlags: flags, time: 0, dwExtraInfo: SYNTHETIC_INPUT_MARKER } } }
    }
}

#[cfg(windows)]
pub use platform::init;
