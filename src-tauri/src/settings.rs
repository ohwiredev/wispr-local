use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;

// ── Setting types ────────────────────────────────────────────────────

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct HotkeySettings {
    pub hold_key: String,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct AudioSettings {
    #[serde(default = "default_sample_rate")]
    pub sample_rate: u32,
    #[serde(default)]
    pub device: serde_json::Value,
}

fn default_sample_rate() -> u32 {
    16000
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct TranscriptionSettings {
    pub model: String,
    pub device: String,
    pub compute_type: String,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct CorrectionSettings {
    pub enabled: bool,
    pub repo_id: String,
    pub model_filename: String,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct OutputSettings {
    #[serde(default = "default_output_method")]
    pub method: String,
}

fn default_output_method() -> String {
    "paste".into()
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct WisprSettings {
    pub hotkey: HotkeySettings,
    pub audio: AudioSettings,
    pub transcription: TranscriptionSettings,
    #[serde(default = "default_text_processing")]
    pub text_processing: serde_json::Value,
    pub correction: CorrectionSettings,
    pub output: OutputSettings,
}

fn default_text_processing() -> serde_json::Value {
    serde_json::json!({})
}

impl Default for WisprSettings {
    fn default() -> Self {
        Self {
            hotkey: HotkeySettings {
                hold_key: "right_ctrl".into(),
            },
            audio: AudioSettings {
                sample_rate: 16000,
                device: serde_json::Value::Null,
            },
            transcription: TranscriptionSettings {
                model: "distil-medium.en".into(),
                device: "cpu".into(),
                compute_type: "int8".into(),
            },
            text_processing: serde_json::json!({}),
            correction: CorrectionSettings {
                enabled: true,
                repo_id: "Qwen/Qwen2.5-0.5B-Instruct-GGUF".into(),
                model_filename: "qwen2.5-0.5b-instruct-q4_k_m.gguf".into(),
            },
            output: OutputSettings {
                method: "paste".into(),
            },
        }
    }
}

// ── Supported models (sorted) ────────────────────────────────────────

pub const WHISPER_MODEL_IDS: &[&str] = &[
    "base",
    "base.en",
    "distil-large-v2",
    "distil-large-v3",
    "distil-medium.en",
    "distil-small.en",
    "large-v1",
    "large-v2",
    "large-v3",
    "medium",
    "medium.en",
    "small",
    "small.en",
    "tiny",
    "tiny.en",
];

// ── Deep-merge ───────────────────────────────────────────────────────

pub fn merge_json(
    base: &serde_json::Value,
    patch: &serde_json::Value,
) -> serde_json::Value {
    match (base, patch) {
        (serde_json::Value::Object(b), serde_json::Value::Object(p)) => {
            let mut out = b.clone();
            for (k, pv) in p {
                let merged = if let Some(bv) = out.get(k) {
                    merge_json(bv, pv)
                } else {
                    pv.clone()
                };
                out.insert(k.clone(), merged);
            }
            serde_json::Value::Object(out)
        }
        (_, patch) => patch.clone(),
    }
}

// ── Load / save ──────────────────────────────────────────────────────

pub fn load_settings(path: &PathBuf) -> WisprSettings {
    let defaults = WisprSettings::default();
    let defaults_val = serde_json::to_value(&defaults).unwrap();

    if !path.exists() {
        return defaults;
    }

    let content = match fs::read_to_string(path) {
        Ok(c) => c,
        Err(_) => return defaults,
    };

    let saved: serde_json::Value = match serde_json::from_str(&content) {
        Ok(v) => v,
        Err(_) => return defaults,
    };

    let merged = merge_json(&defaults_val, &saved);
    serde_json::from_value(merged).unwrap_or(defaults)
}

pub fn save_settings(path: &PathBuf, settings: &WisprSettings) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    let content =
        serde_json::to_string_pretty(settings).map_err(|e| e.to_string())?;
    fs::write(path, content).map_err(|e| e.to_string())
}

// ── Validation ───────────────────────────────────────────────────────

pub fn validate_model(model: &str) -> Result<(), String> {
    if WHISPER_MODEL_IDS.contains(&model) {
        Ok(())
    } else {
        Err(format!(
            "Unsupported transcription model '{model}'. Choose from: {}",
            WHISPER_MODEL_IDS.join(", ")
        ))
    }
}

pub fn validate_device(device: &str) -> Result<(), String> {
    match device {
        "cpu" | "cuda" => Ok(()),
        _ => Err(format!(
            "Unsupported transcription device '{device}'. Use 'cpu' or 'cuda'."
        )),
    }
}
