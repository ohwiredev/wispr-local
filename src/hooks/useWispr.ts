import { useState, useEffect, useCallback } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';

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
    downloaded_models: string[];
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
    downloaded_models: [],
};

export const useWispr = () => {
    const [status, setStatus] = useState<Status>(DEFAULT_STATUS);
    const [settings, setSettings] = useState<WisprSettings | null>(null);
    const [transcriptionModels, setTranscriptionModels] = useState<string[]>([]);
    const [settingsSaving, setSettingsSaving] = useState(false);
    const [settingsError, setSettingsError] = useState<string | null>(null);
    const [capabilities, setCapabilities] = useState<WisprCapabilities | null>(null);
    const [gpuPackInstalling, setGpuPackInstalling] = useState(false);
    const [gpuPackMessage, setGpuPackMessage] = useState<string | null>(null);
    const [gpuPackError, setGpuPackError] = useState<string | null>(null);

    const refreshConfiguration = useCallback(async () => {
        setSettingsError(null);
        try {
            const [sRes, mRes, cRes, stRes] = await Promise.all([
                invoke('get_settings').catch(() => null),
                invoke('get_transcription_models').catch(() => []),
                invoke('get_capabilities').catch(() => null),
                invoke('get_status').catch(() => null),
            ]);
            
            if (sRes) {
                setSettings(sRes as WisprSettings);
            }
            if (mRes) {
                setTranscriptionModels(mRes as string[]);
            }
            if (cRes) {
                setCapabilities(cRes as WisprCapabilities);
            }
            if (stRes) {
                setStatus(prev => ({ ...prev, ...(stRes as Status) }));
            }
        } catch (e) {
            console.error("Failed to load settings", e);
            setSettingsError("Could not load settings");
        }
    }, []);

    useEffect(() => {
        void refreshConfiguration();
    }, [refreshConfiguration]);

    useEffect(() => {
        const unlisten = listen('wispr-status-update', (event) => {
            const raw = event.payload as Partial<Status>;
            setStatus(prev => ({
                ...prev,
                ...raw,
                cuda_available: raw.cuda_available ?? false,
            }));
        });
        
        return () => { void unlisten.then((fn) => fn()); };
    }, []);

    useEffect(() => {
        const unlisten = listen('tray-model-changed', () => {
            void refreshConfiguration();
        });
        return () => { void unlisten.then((fn) => fn()); };
    }, [refreshConfiguration]);

    const saveSettingsPatch = async (patch: Partial<WisprSettings>): Promise<boolean> => {
        setSettingsSaving(true);
        setSettingsError(null);
        try {
            await invoke('save_settings', { patch });
            await refreshConfiguration();
            return true;
        } catch (e) {
            console.error(e);
            setSettingsError(typeof e === "string" ? e : "Failed to save settings");
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

    const startRecording = () => invoke('start_recording').catch(console.error);
    const stopRecording = () => invoke('stop_recording').catch(console.error);

    const installGpuPack = useCallback(async (): Promise<boolean> => {
        setGpuPackInstalling(true);
        setGpuPackError(null);
        setGpuPackMessage(null);
        try {
            const body = (await invoke('install_gpu_pack').catch((e) => ({error: String(e)}))) as {
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
        apiOk: true, // Legacy compat, always true now
        gaveUp: false,
        retryConnection: () => {},
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
