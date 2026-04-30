use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct WisprStatus {
    pub is_recording: bool,
    pub is_processing: bool,
    pub partial_text: String,
    pub last_text: String,
    pub model_loading: bool,
    pub model_loading_name: String,
    pub model_loading_error: Option<String>,
    pub model_loading_step: String,
    pub model_download_current: u64,
    pub model_download_total: u64,
    pub cuda_available: bool,
    pub downloaded_models: Vec<String>,
}

impl Default for WisprStatus {
    fn default() -> Self {
        Self {
            is_recording: false,
            is_processing: false,
            partial_text: String::new(),
            last_text: String::new(),
            model_loading: false,
            model_loading_name: String::new(),
            model_loading_error: None,
            model_loading_step: "idle".into(),
            model_download_current: 0,
            model_download_total: 0,
            cuda_available: false,
            downloaded_models: Vec::new(),
        }
    }
}
