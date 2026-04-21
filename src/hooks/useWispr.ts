import { useState, useEffect, useCallback, useRef } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';
import { WISPR_API_URL } from '../apiConfig';

export interface WisprSettings {
    hotkey: { hold_key: string };
    audio: { sample_rate?: number; device?: number | null };
    transcription: { model: string; device: string; compute_type: string };
    text_processing: Record<string, unknown>;
    output: { method?: string };
}

export interface WisprCapabilities {
    cuda_available: boolean;
    nvidia_smi_found: boolean;
    gpu_pack_install_configured: boolean;
    gpu_pack_user_hint: string | null;
}

const ERROR_GIVE_UP_MS = 2 * 60 * 1000;

interface Status {
    is_recording: boolean;
    is_processing: boolean;
    partial_text: string;
    last_text: string;
    model_loading: boolean;
    model_loading_name: string;
    model_loading_error: string | null;
    model_loading_step: string;
    model_download_current: number;
    model_download_total: number;
    cuda_available: boolean;
}

const DEFAULT_STATUS: Status = {
    is_recording: false,
    is_processing: false,
    partial_text: "",
    last_text: "",
    model_loading: false,
    model_loading_name: "",
    model_loading_error: null,
    model_loading_step: "idle",
    model_download_current: 0,
    model_download_total: 0,
    cuda_available: false,
};

export const useWispr = () => {
    const [status, setStatus] = useState<Status>(DEFAULT_STATUS);
    const [apiOk, setApiOk] = useState(true);
    const [gaveUp, setGaveUp] = useState(false);
    const [settings, setSettings] = useState<WisprSettings | null>(null);
    const [transcriptionModels, setTranscriptionModels] = useState<string[]>([]);
    const [settingsSaving, setSettingsSaving] = useState(false);
    const [settingsError, setSettingsError] = useState<string | null>(null);
    const [capabilities, setCapabilities] = useState<WisprCapabilities | null>(null);
    const [gpuPackInstalling, setGpuPackInstalling] = useState(false);
    const [gpuPackMessage, setGpuPackMessage] = useState<string | null>(null);
    const [gpuPackError, setGpuPackError] = useState<string | null>(null);

    const esRef = useRef<EventSource | null>(null);
    const firstFailureAtRef = useRef<number | null>(null);
    const retryTimerRef = useRef<number | null>(null);

    const apiOkRef = useRef(apiOk);
    apiOkRef.current = apiOk;
    const gaveUpRef = useRef(gaveUp);
    gaveUpRef.current = gaveUp;

    const connectSSE = useCallback(() => {
        if (esRef.current) {
            esRef.current.close();
            esRef.current = null;
        }
        if (retryTimerRef.current !== null) {
            window.clearTimeout(retryTimerRef.current);
            retryTimerRef.current = null;
        }

        const es = new EventSource(`${WISPR_API_URL}/events`);
        esRef.current = es;

        es.onmessage = (e) => {
            try {
                const raw = JSON.parse(e.data) as Partial<Status> & { type?: string };
                const data: Status = {
                    ...DEFAULT_STATUS,
                    ...raw,
                    cuda_available: raw.cuda_available ?? false,
                };
                setStatus(data);
                if (!apiOkRef.current) setApiOk(true);
                if (gaveUpRef.current) setGaveUp(false);
                firstFailureAtRef.current = null;
            } catch {
                // ignore malformed messages
            }
        };

        es.onopen = () => {
            if (!apiOkRef.current) setApiOk(true);
            if (gaveUpRef.current) setGaveUp(false);
            firstFailureAtRef.current = null;
        };

        es.onerror = () => {
            es.close();
            esRef.current = null;
            if (apiOkRef.current) setApiOk(false);

            const now = Date.now();
            if (firstFailureAtRef.current === null) {
                firstFailureAtRef.current = now;
            }
            if (now - firstFailureAtRef.current >= ERROR_GIVE_UP_MS) {
                setGaveUp(true);
                return;
            }
            retryTimerRef.current = window.setTimeout(() => {
                connectSSE();
            }, 2000);
        };
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    useEffect(() => {
        connectSSE();
        return () => {
            if (esRef.current) {
                esRef.current.close();
                esRef.current = null;
            }
            if (retryTimerRef.current !== null) {
                window.clearTimeout(retryTimerRef.current);
            }
        };
    }, [connectSSE]);

    const refreshConfiguration = useCallback(async () => {
        setSettingsError(null);
        try {
            const [sRes, mRes, cRes] = await Promise.all([
                fetch(`${WISPR_API_URL}/settings`),
                fetch(`${WISPR_API_URL}/transcription/models`),
                fetch(`${WISPR_API_URL}/system/capabilities`),
            ]);
            if (sRes.ok) {
                setSettings((await sRes.json()) as WisprSettings);
            }
            if (mRes.ok) {
                const body = (await mRes.json()) as { models?: string[] };
                setTranscriptionModels(body.models ?? []);
            }
            if (cRes.ok) {
                setCapabilities((await cRes.json()) as WisprCapabilities);
            }
        } catch (e) {
            console.error("Failed to load settings", e);
            setSettingsError("Could not load settings");
        }
    }, []);

    useEffect(() => {
        if (apiOk && !gaveUp) {
            void refreshConfiguration();
        }
    }, [apiOk, gaveUp, refreshConfiguration]);

    useEffect(() => {
        if (!settings || transcriptionModels.length === 0) return;
        invoke('update_tray_models', {
            models: transcriptionModels,
            currentModel: settings.transcription.model,
        }).catch((e) => console.warn('Failed to update tray models', e));
    }, [settings, transcriptionModels]);

    useEffect(() => {
        const unlisten = listen('tray-model-changed', () => {
            void refreshConfiguration();
        });
        return () => { void unlisten.then((fn) => fn()); };
    }, [refreshConfiguration]);

    const retryConnection = useCallback(() => {
        firstFailureAtRef.current = null;
        setGaveUp(false);
        connectSSE();
    }, [connectSSE]);

    const saveSettingsPatch = async (patch: Partial<WisprSettings>): Promise<boolean> => {
        setSettingsSaving(true);
        setSettingsError(null);
        try {
            const res = await fetch(`${WISPR_API_URL}/settings`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(patch),
            });
            const detail = !res.ok
                ? ((await res.json().catch(() => ({}))) as { detail?: string }).detail ?? res.statusText
                : null;
            if (!res.ok) {
                setSettingsError(typeof detail === "string" ? detail : "Failed to save settings");
                return false;
            }
            await refreshConfiguration();
            return true;
        } catch (e) {
            console.error(e);
            setSettingsError("Failed to save settings");
            return false;
        } finally {
            setSettingsSaving(false);
        }
    };

    const setTranscriptionModel = async (model: string) => {
        if (!settings) return;
        await saveSettingsPatch({
            transcription: { ...settings.transcription, model },
        });
    };

    const setHotkey = async (holdKey: string) => {
        if (!settings) return;
        await saveSettingsPatch({
            hotkey: { hold_key: holdKey },
        });
    };

    const setTranscriptionDevice = async (device: "cpu" | "cuda") => {
        if (!settings) return;
        await saveSettingsPatch({
            transcription: { ...settings.transcription, device },
        });
    };

    const startRecording = () => fetch(`${WISPR_API_URL}/start`, { method: 'POST' });
    const stopRecording = () => fetch(`${WISPR_API_URL}/stop`, { method: 'POST' });

    const installGpuPack = useCallback(async (): Promise<boolean> => {
        setGpuPackInstalling(true);
        setGpuPackError(null);
        setGpuPackMessage(null);
        try {
            const res = await fetch(`${WISPR_API_URL}/system/gpu-pack/install`, {
                method: "POST",
            });
            const body = (await res.json().catch(() => ({}))) as {
                ok?: boolean;
                error?: string;
                message?: string;
            };
            if (!body.ok) {
                setGpuPackError(typeof body.error === "string" ? body.error : "GPU install failed");
                return false;
            }
            setGpuPackMessage(
                typeof body.message === "string" ? body.message : "Installation finished.",
            );
            await refreshConfiguration();
            return true;
        } catch (e) {
            console.error(e);
            setGpuPackError("Could not reach the backend for GPU install");
            return false;
        } finally {
            setGpuPackInstalling(false);
        }
    }, [refreshConfiguration]);

    return {
        status,
        apiOk,
        gaveUp,
        retryConnection,
        settings,
        transcriptionModels,
        settingsSaving,
        settingsError,
        capabilities,
        gpuPackInstalling,
        gpuPackMessage,
        gpuPackError,
        refreshConfiguration,
        saveSettingsPatch,
        installGpuPack,
        setTranscriptionModel,
        setTranscriptionDevice,
        setHotkey,
        startRecording,
        stopRecording,
    };
};
