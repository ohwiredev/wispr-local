use std::path::PathBuf;
use std::process::Stdio;
use std::sync::Arc;
use tauri::{AppHandle, Emitter};
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::process::{Child, Command};
use tokio::sync::{mpsc, oneshot, Mutex};

use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct IpcRequest {
    pub id: u64,
    pub method: String,
    pub params: serde_json::Value,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct IpcResponse {
    pub id: Option<u64>,
    pub result: Option<serde_json::Value>,
    pub error: Option<String>,
    pub event: Option<String>,
    pub data: Option<serde_json::Value>,
}

pub struct PythonWorker {
    request_tx: mpsc::Sender<(
        IpcRequest,
        oneshot::Sender<Result<serde_json::Value, String>>,
    )>,
    next_id: Arc<Mutex<u64>>,
    process: Arc<Mutex<Child>>,
}

impl PythonWorker {
    pub async fn spawn(app: &AppHandle, exe_path: PathBuf, args: Vec<String>, cwd: Option<PathBuf>) -> Result<Self, String> {
        #[cfg(target_os = "windows")]
        const CREATE_NO_WINDOW: u32 = 0x08000000;

        let mut cmd = Command::new(&exe_path);
        cmd.args(args);

        if let Some(dir) = cwd {
            cmd.current_dir(dir);
        } else if let Some(parent) = exe_path.parent() {
            cmd.current_dir(parent);
        }

        cmd.stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());

        #[cfg(target_os = "windows")]
        cmd.creation_flags(CREATE_NO_WINDOW);

        let mut child = cmd
            .spawn()
            .map_err(|e| format!("Failed to spawn python worker: {}", e))?;

        let stdin = child.stdin.take().ok_or("Failed to open stdin")?;
        let stdout = child.stdout.take().ok_or("Failed to open stdout")?;
        let stderr = child.stderr.take().ok_or("Failed to open stderr")?;

        let (req_tx, mut req_rx) = mpsc::channel::<(
            IpcRequest,
            oneshot::Sender<Result<serde_json::Value, String>>,
        )>(32);

        let pending_requests: Arc<
            Mutex<
                std::collections::HashMap<u64, oneshot::Sender<Result<serde_json::Value, String>>>,
            >,
        > = Arc::new(Mutex::new(std::collections::HashMap::new()));

        let pending_requests_writer = pending_requests.clone();

        // Writer task
        tokio::spawn(async move {
            let mut stdin = stdin;
            while let Some((req, tx)) = req_rx.recv().await {
                let req_id = req.id;
                pending_requests_writer.lock().await.insert(req_id, tx);

                let mut json = match serde_json::to_string(&req) {
                    Ok(s) => s,
                    Err(_) => continue,
                };
                json.push('\n');

                if let Err(_) = stdin.write_all(json.as_bytes()).await {
                    break;
                }
            }
        });

        // Reader task (stdout)
        let app_handle = app.clone();
        let pending_requests_reader = pending_requests.clone();
        tokio::spawn(async move {
            let mut reader = BufReader::new(stdout).lines();
            while let Ok(Some(line)) = reader.next_line().await {
                if let Ok(res) = serde_json::from_str::<IpcResponse>(&line) {
                    if let Some(event) = res.event {
                        let _ = app_handle.emit(&event, res.data.unwrap_or(serde_json::json!({})));
                    } else if let Some(id) = res.id {
                        if let Some(tx) = pending_requests_reader.lock().await.remove(&id) {
                            if let Some(err) = res.error {
                                let _ = tx.send(Err(err));
                            } else {
                                let _ = tx.send(Ok(res.result.unwrap_or(serde_json::json!({}))));
                            }
                        }
                    }
                }
            }
        });

        // Stderr reader
        tokio::spawn(async move {
            let mut reader = BufReader::new(stderr).lines();
            while let Ok(Some(line)) = reader.next_line().await {
                eprintln!("[python worker] {}", line);
            }
        });

        Ok(Self {
            request_tx: req_tx,
            next_id: Arc::new(Mutex::new(0)),
            process: Arc::new(Mutex::new(child)),
        })
    }

    pub async fn request(
        &self,
        method: &str,
        params: serde_json::Value,
    ) -> Result<serde_json::Value, String> {
        let id = {
            let mut id_lock = self.next_id.lock().await;
            *id_lock += 1;
            *id_lock
        };

        let req = IpcRequest {
            id,
            method: method.into(),
            params,
        };

        let (tx, rx) = oneshot::channel();
        self.request_tx
            .send((req, tx))
            .await
            .map_err(|_| "Failed to send request to worker loop")?;

        rx.await
            .map_err(|_| "Response channel closed".to_string())?
    }

    pub async fn shutdown(&self) {
        let mut child = self.process.lock().await;
        let _ = child.kill().await;
        let _ = child.wait().await;
    }
}
