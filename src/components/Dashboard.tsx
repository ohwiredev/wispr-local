import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useWispr, type WisprCapabilities, type WisprSettings } from "../hooks/useWispr";
import { useWeeklyWords } from "../hooks/useWeeklyWords";

type Page = "home" | "history" | "settings";

const MODEL_SPEED_LABELS: Record<string, string> = {
    "tiny": "Fastest",
    "tiny.en": "Fastest",
    "base": "Fast",
    "base.en": "Fast",
    "small": "Moderate",
    "small.en": "Moderate",
    "medium": "Slower",
    "medium.en": "Slower",
    "large-v1": "Slowest",
    "large-v2": "Slowest",
    "large-v3": "Slowest",
    "distil-large-v2": "Fast (GPU)",
    "distil-large-v3": "Fast (GPU)",
    "distil-medium.en": "Moderate",
    "distil-small.en": "Fast",
};

const MODEL_SIZE_LABELS: Record<string, string> = {
    "tiny": "75 MB",
    "tiny.en": "75 MB",
    "base": "145 MB",
    "base.en": "145 MB",
    "small": "485 MB",
    "small.en": "485 MB",
    "medium": "1.5 GB",
    "medium.en": "1.5 GB",
    "large-v1": "3.1 GB",
    "large-v2": "3.1 GB",
    "large-v3": "3.1 GB",
    "distil-large-v2": "1.5 GB",
    "distil-large-v3": "1.5 GB",
    "distil-medium.en": "760 MB",
    "distil-small.en": "330 MB",
};

const HOTKEY_OPTIONS: { value: string; label: string }[] = [
    { value: "right_ctrl", label: "Right Ctrl" },
    { value: "left_ctrl", label: "Left Ctrl" },
    { value: "right_alt", label: "Right Alt" },
    { value: "left_alt", label: "Left Alt" },
    { value: "right_shift", label: "Right Shift" },
    { value: "left_shift", label: "Left Shift" },
];

const HOTKEY_LABEL_MAP = Object.fromEntries(HOTKEY_OPTIONS.map((o) => [o.value, o.label]));

function formatHotkeyLabel(holdKey: string | undefined): string {
    if (!holdKey) return "Right Ctrl";
    return HOTKEY_LABEL_MAP[holdKey] ?? holdKey.replace(/_/g, " ");
}

const COMPUTE_DEVICE_LABELS = ["CPU", "GPU (CUDA)"] as const;

function computeLabelFromDevice(device: string | undefined): string {
    return device === "cuda" ? "GPU (CUDA)" : "CPU";
}

function deviceFromComputeLabel(label: string): "cpu" | "cuda" {
    return label === "GPU (CUDA)" ? "cuda" : "cpu";
}

/* ── SVG icons (inline, small) ── */

function IconHome() {
    return (
        <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
            <path d="M3 10.5 10 4l7 6.5" />
            <path d="M5 9.5V16a1 1 0 0 0 1 1h3v-4h2v4h3a1 1 0 0 0 1-1V9.5" />
        </svg>
    );
}

function IconHistory() {
    return (
        <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="10" cy="10" r="7" />
            <path d="M10 6.5V10l2.5 2.5" />
        </svg>
    );
}

function IconSettings() {
    return (
        <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="10" cy="10" r="2.5" />
            <path d="M10 2.5v2M10 15.5v2M2.5 10h2M15.5 10h2M4.4 4.4l1.4 1.4M14.2 14.2l1.4 1.4M4.4 15.6l1.4-1.4M14.2 5.8l1.4-1.4" />
        </svg>
    );
}

/* ── Model loading banner ── */

function formatBytes(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function ModelLoadingBanner({
    name,
    step,
    downloadCurrent,
    downloadTotal,
}: {
    name: string;
    step: string;
    downloadCurrent: number;
    downloadTotal: number;
}) {
    const [speed, setSpeed] = useState<string>("0 B/s");
    const lastUpdate = useRef<{ bytes: number; time: number } | null>(null);

    useEffect(() => {
        if (step !== "downloading" || downloadCurrent === 0) {
            lastUpdate.current = null;
            setSpeed("0 B/s");
            return;
        }

        const now = Date.now();
        if (lastUpdate.current) {
            const dt = (now - lastUpdate.current.time) / 1000;
            if (dt >= 0.5) { // Update speed every 500ms
                const db = downloadCurrent - lastUpdate.current.bytes;
                const bps = db / dt;
                setSpeed(`${formatBytes(Math.round(bps))}/s`);
                lastUpdate.current = { bytes: downloadCurrent, time: now };
            }
        } else {
            lastUpdate.current = { bytes: downloadCurrent, time: now };
        }
    }, [downloadCurrent, step]);

    const pct = downloadTotal > 0 ? Math.min(100, Math.round((downloadCurrent / downloadTotal) * 100)) : 0;
    const isDownloading = step === "downloading" && downloadTotal > 0 && pct < 100;

    let message: React.ReactNode;
    if (step === "checking" || step === "verifying") {
        message = <>Verifying local files for <strong>{name}</strong>...</>;
    } else if (isDownloading) {
        message = (
            <div className="model-loading-banner__message-grid">
                <div className="model-loading-banner__main-text">
                    Downloading <strong>{name}</strong> — {pct}%
                </div>
                <div className="model-loading-banner__meta-text">
                    {formatBytes(downloadCurrent)} / {formatBytes(downloadTotal)} • {speed}
                </div>
            </div>
        );
    } else if (step === "downloading") {
        message = <>Downloading <strong>{name}</strong>...</>;
    } else if (step === "loading") {
        message = <>Loading <strong>{name}</strong> into memory...</>;
    } else {
        message = <>Preparing model <strong>{name}</strong>...</>;
    }

    return (
        <div className="model-loading-banner" role="status">
            <span className="model-loading-banner__spinner" />
            <div className="model-loading-banner__body">
                <span>{message}</span>
                {isDownloading && (
                    <div className="model-loading-banner__bar">
                        <div className="model-loading-banner__fill" style={{ width: `${pct}%` }} />
                    </div>
                )}
            </div>
        </div>
    );
}

/* ── Sidebar ── */

function Sidebar({ page, setPage }: { page: Page; setPage: (p: Page) => void }) {
    const links: { id: Page; label: string; icon: React.ReactNode }[] = [
        { id: "home", label: "Home", icon: <IconHome /> },
        { id: "history", label: "History", icon: <IconHistory /> },
        { id: "settings", label: "Settings", icon: <IconSettings /> },
    ];

    return (
        <aside className="sidebar">
            <div className="sidebar__brand">
                <div className="sidebar__logo">W</div>
                <span className="sidebar__title">Wispr Local</span>
            </div>
            <nav className="sidebar__nav">
                {links.map((l) => (
                    <button
                        key={l.id}
                        type="button"
                        className={`sidebar__link ${page === l.id ? "sidebar__link--active" : ""}`}
                        onClick={() => setPage(l.id)}
                    >
                        {l.icon}
                        {l.label}
                    </button>
                ))}
            </nav>
            <div className="sidebar__footer">
                <span className="sidebar__version">v1.0.0-alpha</span>
            </div>
        </aside>
    );
}

/* ── Transcription types & helpers ── */

const TXN_STORAGE_KEY = "wispr_transcriptions";

interface TranscriptionEntry {
    id: number;
    text: string;
    time: Date;
}

interface StoredEntry {
    id: number;
    text: string;
    time: string;
}

function loadEntries(): { entries: TranscriptionEntry[]; nextId: number } {
    try {
        const raw = localStorage.getItem(TXN_STORAGE_KEY);
        if (!raw) return { entries: [], nextId: 1 };
        const stored = JSON.parse(raw) as StoredEntry[];
        const entries = stored.map((e) => ({ ...e, time: new Date(e.time) }));
        const maxId = entries.reduce((max, e) => Math.max(max, e.id), 0);
        return { entries, nextId: maxId + 1 };
    } catch {
        return { entries: [], nextId: 1 };
    }
}

function saveEntries(entries: TranscriptionEntry[]) {
    const stored: StoredEntry[] = entries.map((e) => ({
        id: e.id,
        text: e.text,
        time: e.time.toISOString(),
    }));
    localStorage.setItem(TXN_STORAGE_KEY, JSON.stringify(stored));
}

function formatTime(d: Date): string {
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function formatTimeAgo(d: Date): string {
    const secs = Math.floor((Date.now() - d.getTime()) / 1000);
    if (secs < 60) return "just now";
    const mins = Math.floor(secs / 60);
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    return `${hrs}h ago`;
}

/* ── Home view ── */

function WaveformPlaceholder() {
    return (
        <svg className="waveform-placeholder" viewBox="0 0 320 48" fill="none">
            <path d="M0 24h8M16 18v12M24 12v24M32 16v16M40 20v8M48 10v28M56 14v20M64 22v4M72 8v32M80 16v16M88 20v8M96 12v24M104 18v12M112 24h8M120 14v20M128 20v8M136 10v28M144 16v16M152 22v4M160 12v24M168 18v12M176 24h8M184 14v20M192 8v32M200 16v16M208 20v8M216 12v24M224 18v12M232 24h8M240 16v16M248 10v28M256 14v20M264 22v4M272 12v24M280 18v12M288 24h8M296 16v16M304 20v8M312 14v20"
                stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
        </svg>
    );
}

function HomeView({
    status,
    currentModel,
    computeDevice,
    hotkeyLabel,
    entries,
    wordCount,
    goToSettings,
    modelLoading,
}: {
    status: { is_recording: boolean; is_processing: boolean };
    currentModel: string;
    computeDevice: string;
    hotkeyLabel: string;
    entries: TranscriptionEntry[];
    wordCount: number;
    goToSettings: () => void;
    modelLoading?: boolean;
}) {
    const statusLabel = modelLoading
        ? "Initializing..."
        : status.is_recording
            ? "Recording..."
            : status.is_processing
                ? "Transcribing..."
                : "Ready";
    const statusVariant = modelLoading
        ? "initializing"
        : status.is_recording
            ? "recording"
            : status.is_processing
                ? "processing"
                : "idle";

    return (
        <>
            {/* Hero */}
            <div className="hero">
                <div className="hero__text">
                    <h2 className="hero__title">{modelLoading ? "Setting things up" : "Welcome back"}</h2>
                    <p className="hero__subtitle">
                        {modelLoading 
                            ? "Please wait while we prepare the transcription model..." 
                            : <>Press <kbd className="kbd">{hotkeyLabel}</kbd> to start recording</>}
                    </p>
                </div>
                <span className={`hero__badge hero__badge--${statusVariant}`}>
                    <span className={`live-dot live-dot--${statusVariant}`} />
                    {statusLabel}
                </span>
            </div>

            {/* Stat cards */}
            <div className="card-grid">
                <div className="card">
                    <div className="card__icon card__icon--model">
                        <svg viewBox="0 0 20 20" fill="none" stroke="#4da6ff" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                            <rect x="6" y="2" width="8" height="12" rx="4" />
                            <path d="M4 10a6 6 0 0 0 12 0" />
                            <path d="M10 16v2M7 18h6" />
                        </svg>
                    </div>
                    <h3 className="card__title">Model</h3>
                    <p className="card__value">{currentModel}</p>
                    <p className="card__meta">{computeDevice}</p>
                    <button type="button" className="card__action" onClick={goToSettings}>Change model</button>
                </div>

                <div className="card">
                    <div className="card__icon card__icon--hotkey">
                        <svg viewBox="0 0 20 20" fill="none" stroke="#4da6ff" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                            <rect x="2" y="5" width="16" height="10" rx="2" />
                            <path d="M6 10h8" />
                        </svg>
                    </div>
                    <h3 className="card__title">Hotkey</h3>
                    <p className="card__value"><kbd className="kbd kbd--lg">{hotkeyLabel}</kbd></p>
                    <p className="card__meta">Hold to record</p>
                </div>

                <div className="card">
                    <div className="card__icon card__icon--words">
                        <svg viewBox="0 0 20 20" fill="none" stroke="#4da6ff" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M4 4h12a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1z" />
                            <path d="M6 8h8M6 11h5" />
                        </svg>
                    </div>
                    <h3 className="card__title">Words This Week</h3>
                    <p className="card__value">{wordCount.toLocaleString()}</p>
                    <p className="card__meta">Resets every Monday</p>
                </div>
            </div>

            {/* Transcription panel */}
            <div className="transcription-panel">
                <div className="transcription-panel__header">
                    <svg width="18" height="18" viewBox="0 0 20 20" fill="none" stroke="#a855f7" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M4 5h12M4 8.5h9M4 12h11M4 15.5h7" />
                    </svg>
                    <h3 className="transcription-panel__title">Transcription</h3>
                </div>
                <TranscriptionTable entries={entries} limit={5} />
            </div>
        </>
    );
}

/* ── Transcription table (shared by Home & History) ── */

function TranscriptionTable({ entries, limit }: { entries: TranscriptionEntry[]; limit?: number }) {
    const rows = limit ? entries.slice(0, limit) : entries;
    const newestId = useRef<number | null>(null);
    const [animatingId, setAnimatingId] = useState<number | null>(null);

    useEffect(() => {
        if (rows.length === 0) return;
        const top = rows[0];
        if (newestId.current !== null && top.id !== newestId.current) {
            setAnimatingId(top.id);
            const timer = window.setTimeout(() => setAnimatingId(null), 400);
            newestId.current = top.id;
            return () => window.clearTimeout(timer);
        }
        newestId.current = top.id;
    }, [rows]);

    if (rows.length === 0) {
        return (
            <div className="transcription-panel__empty">
                <WaveformPlaceholder />
                <p>Transcriptions will appear here</p>
            </div>
        );
    }

    return (
        <div className="txn-table-wrap">
            <table className="txn-table">
                <tbody>
                    {rows.map((entry) => (
                        <tr key={entry.id} className={`txn-table__row ${entry.id === animatingId ? "txn-table__row--new" : ""}`}>
                            <td className="txn-table__cell txn-table__cell--text">{entry.text}</td>
                            <td className="txn-table__cell txn-table__cell--time" title={formatTime(entry.time)}>
                                {formatTimeAgo(entry.time)}
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

/* ── History view ── */

function HistoryView({ entries }: { entries: TranscriptionEntry[] }) {
    return (
        <>
            <div className="content__header">
                <h2 className="content__title">History</h2>
                <p className="content__subtitle">All transcriptions from this session</p>
            </div>
            <div className="transcription-panel">
                <TranscriptionTable entries={entries} />
            </div>
        </>
    );
}

/* ── Custom dropdown ── */

function Dropdown({
    value,
    options,
    disabled,
    onChange,
    isOptionDisabled,
    isOptionDownloaded,
}: {
    value: string;
    options: string[];
    disabled?: boolean;
    onChange: (v: string) => void;
    isOptionDisabled?: (option: string) => boolean;
    isOptionDownloaded?: (option: string) => boolean;
}) {
    const [open, setOpen] = useState(false);
    const ref = useRef<HTMLDivElement>(null);

    const close = useCallback(() => setOpen(false), []);

    useEffect(() => {
        if (!open) return;
        const onClickOutside = (e: MouseEvent) => {
            if (ref.current && !ref.current.contains(e.target as Node)) close();
        };
        const onEsc = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
        document.addEventListener("mousedown", onClickOutside);
        document.addEventListener("keydown", onEsc);
        return () => {
            document.removeEventListener("mousedown", onClickOutside);
            document.removeEventListener("keydown", onEsc);
        };
    }, [open, close]);

    return (
        <div className={`dropdown ${disabled ? "dropdown--disabled" : ""}`} ref={ref}>
            <button
                type="button"
                className="dropdown__trigger"
                onClick={() => !disabled && setOpen((o) => !o)}
                aria-expanded={open}
                disabled={disabled}
            >
                <span className="dropdown__value">{value}</span>
                <svg className={`dropdown__chevron ${open ? "dropdown__chevron--open" : ""}`} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M4 6l4 4 4-4" />
                </svg>
            </button>
            {open && (
                <ul className="dropdown__menu" role="listbox">
                    {options.map((opt) => (
                        <li
                            key={opt}
                            role="option"
                            aria-selected={opt === value}
                            aria-disabled={isOptionDisabled?.(opt) ?? false}
                            className={`dropdown__item ${opt === value ? "dropdown__item--selected" : ""} ${isOptionDisabled?.(opt) ? "dropdown__item--disabled" : ""}`}
                            onClick={() => {
                                if (isOptionDisabled?.(opt)) return;
                                onChange(opt);
                                close();
                            }}
                        >
                            <div className="dropdown__item-content">
                                <div className="dropdown__item-header">
                                    <span className="dropdown__item-label">{opt}</span>
                                    {isOptionDownloaded?.(opt) && (
                                        <span className="dropdown__item-badge">Downloaded</span>
                                    )}
                                </div>
                                {MODEL_SIZE_LABELS[opt] && (
                                    <span className="dropdown__item-size">{MODEL_SIZE_LABELS[opt]}</span>
                                )}
                            </div>
                            {opt === value && (
                                <svg className="dropdown__check" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                    <path d="M3 8.5l3.5 3.5 6.5-7" />
                                </svg>
                            )}
                        </li>
                    ))}
                </ul>
            )}
        </div>
    );
}

/* ── Settings view ── */

function SettingsView({
    settings,
    apiOk,
    settingsSaving,
    settingsError,
    currentModel,
    modelOptionsList,
    currentHotkey,
    modelLoading,
    cudaAvailable,
    capabilities,
    currentDevice,
    saveSettingsPatch,
    gpuPackInstalling,
    gpuPackMessage,
    gpuPackError,
    installGpuPack,
    downloadedModels,
}: {
    settings: ReturnType<typeof useWispr>["settings"];
    apiOk: boolean;
    settingsSaving: boolean;
    settingsError: string | null;
    currentModel: string;
    modelOptionsList: string[];
    currentHotkey: string;
    modelLoading: boolean;
    cudaAvailable: boolean;
    capabilities: WisprCapabilities | null;
    currentDevice: "cpu" | "cuda";
    saveSettingsPatch: (patch: Partial<WisprSettings>) => Promise<boolean>;
    gpuPackInstalling: boolean;
    gpuPackMessage: string | null;
    gpuPackError: string | null;
    installGpuPack: () => Promise<boolean>;
    downloadedModels: string[];
}) {
    const [draftHotkey, setDraftHotkey] = useState(currentHotkey);
    const [draftModel, setDraftModel] = useState(currentModel);
    const [draftDevice, setDraftDevice] = useState<"cpu" | "cuda">(currentDevice);
    const [saved, setSaved] = useState(false);

    useEffect(() => { setDraftHotkey(currentHotkey); }, [currentHotkey]);
    useEffect(() => { setDraftModel(currentModel); }, [currentModel]);
    useEffect(() => { setDraftDevice(currentDevice); }, [currentDevice]);

    const isDirty =
        draftHotkey !== currentHotkey || draftModel !== currentModel || draftDevice !== currentDevice;
    const busy = settingsSaving || modelLoading || gpuPackInstalling;

    const hotkeyLabels = HOTKEY_OPTIONS.map((o) => o.label);
    const draftHotkeyLabel = formatHotkeyLabel(draftHotkey);

    const onHotkeyChange = (label: string) => {
        const opt = HOTKEY_OPTIONS.find((o) => o.label === label);
        if (opt) setDraftHotkey(opt.value);
    };

    const handleSave = async () => {
        if (!settings) return;
        const patch: Partial<WisprSettings> = {};
        if (draftHotkey !== currentHotkey) {
            patch.hotkey = { hold_key: draftHotkey };
        }
        if (draftModel !== currentModel || draftDevice !== currentDevice) {
            patch.transcription = {
                ...settings.transcription,
                ...(draftModel !== currentModel ? { model: draftModel } : {}),
                ...(draftDevice !== currentDevice ? { device: draftDevice } : {}),
            };
        }
        if (Object.keys(patch).length > 0) {
            const ok = await saveSettingsPatch(patch);
            if (!ok) return;
        }
        setSaved(true);
        setTimeout(() => setSaved(false), 2000);
    };

    return (
        <>
            <div className="content__header">
                <h2 className="content__title">Settings</h2>
                <p className="content__subtitle">Configure hotkey and transcription model</p>
            </div>
            <div className="settings-view">
                <div className="settings-card">
                    <div className="setting-row">
                        <label>Hotkey</label>
                        <Dropdown
                            value={draftHotkeyLabel}
                            options={hotkeyLabels}
                            disabled={!apiOk || !settings || busy}
                            onChange={onHotkeyChange}
                        />
                    </div>
                    <div className="setting-row">
                        <div className="setting-row__label-group">
                            <label>Transcription model</label>
                            {MODEL_SPEED_LABELS[draftModel] && (
                                <span className="setting-row__speed-badge">{MODEL_SPEED_LABELS[draftModel]}</span>
                            )}
                        </div>
                        <Dropdown
                            value={draftModel}
                            options={modelOptionsList}
                            disabled={!apiOk || !settings || busy}
                            isOptionDownloaded={(opt) => downloadedModels.includes(opt)}
                            onChange={setDraftModel}
                        />
                    </div>
                    <div className="setting-row">
                        <div className="setting-row__label-group">
                            <label>Compute</label>
                            {!cudaAvailable && capabilities?.gpu_pack_install_configured && (
                                <span className="setting-row__speed-badge">GPU libraries optional</span>
                            )}
                            {!cudaAvailable && !capabilities?.gpu_pack_install_configured && (
                                <span className="setting-row__speed-badge">No GPU detected</span>
                            )}
                        </div>
                        <Dropdown
                            value={computeLabelFromDevice(draftDevice)}
                            options={[...COMPUTE_DEVICE_LABELS]}
                            disabled={!apiOk || !settings || busy}
                            isOptionDisabled={(opt) => opt === "GPU (CUDA)" && !cudaAvailable}
                            onChange={(label) => setDraftDevice(deviceFromComputeLabel(label))}
                        />
                    </div>
                    {capabilities?.gpu_pack_install_configured && !capabilities.cuda_available && (
                        <div className="settings-gpu-pack">
                            <p className="settings-gpu-pack__lead">
                                This build can download GPU acceleration for faster-whisper
                                (CUDA). An NVIDIA GPU and driver are required.
                            </p>
                            {capabilities.gpu_pack_user_hint && (
                                <p className="settings-gpu-pack__hint">{capabilities.gpu_pack_user_hint}</p>
                            )}
                            {!capabilities.nvidia_smi_found && (
                                <p className="settings-gpu-pack__warn" role="status">
                                    <code>nvidia-smi</code> was not found on your PATH. If you do not
                                    have an NVIDIA GPU, GPU acceleration will not work.
                                </p>
                            )}
                            <button
                                type="button"
                                className="settings-gpu-pack__btn"
                                disabled={!apiOk || gpuPackInstalling}
                                onClick={() => void installGpuPack()}
                            >
                                {gpuPackInstalling ? "Installing…" : "Install GPU support"}
                            </button>
                            {gpuPackMessage && (
                                <p className="settings-gpu-pack__success" role="status">{gpuPackMessage}</p>
                            )}
                            {gpuPackError && (
                                <p className="settings-inline-error" role="alert">{gpuPackError}</p>
                            )}
                        </div>
                    )}
                    {settingsError && (
                        <p className="settings-inline-error" role="alert">{settingsError}</p>
                    )}
                </div>
                <button
                    type="button"
                    className={`settings-save-btn ${saved ? "settings-save-btn--saved" : ""}`}
                    disabled={!isDirty || busy}
                    onClick={() => void handleSave()}
                >
                    {busy ? "Saving..." : saved ? "Saved" : "Save Settings"}
                </button>
            </div>
        </>
    );
}

/* ── Main Dashboard ── */

const Dashboard = () => {
    const [page, setPage] = useState<Page>("home");

    const {
        status,
        apiOk,
        settings,
        transcriptionModels,
        settingsSaving,
        settingsError,
        capabilities,
        gpuPackInstalling,
        gpuPackMessage,
        gpuPackError,
        saveSettingsPatch,
        installGpuPack,
    } = useWispr();

    const [initialData] = useState(() => loadEntries());
    const [entries, setEntries] = useState<TranscriptionEntry[]>(initialData.entries);
    const nextIdRef = useRef(initialData.nextId);
    const prevTextRef = useRef(initialData.entries[0]?.text ?? "");
    const { wordCount, addWords } = useWeeklyWords();

    useEffect(() => {
        const text = status.last_text;
        if (text && text !== prevTextRef.current) {
            prevTextRef.current = text;
            setEntries((prev) => {
                const entry: TranscriptionEntry = { id: nextIdRef.current++, text, time: new Date() };
                const next = [entry, ...prev];
                saveEntries(next);
                return next;
            });
            addWords(text);
        }
    }, [status.last_text, addWords]);

    const modelOptionsList = useMemo(() => {
        const fallback = ["tiny", "base", "small", "medium", "large-v2"];
        const base = transcriptionModels.length > 0 ? transcriptionModels : fallback;
        const m = settings?.transcription?.model;
        if (!m) return base;
        return base.includes(m) ? base : [m, ...base];
    }, [transcriptionModels, settings?.transcription?.model]);

    const currentModel = settings?.transcription?.model ?? "base";
    const currentDevice: "cpu" | "cuda" =
        settings?.transcription?.device === "cuda" ? "cuda" : "cpu";
    const cudaForSettings = capabilities?.cuda_available ?? status.cuda_available;

    return (
        <>
            <Sidebar page={page} setPage={setPage} />
            <div className="content">


                {status.model_loading && (
                    <ModelLoadingBanner
                        name={status.model_loading_name}
                        step={status.model_loading_step}
                        downloadCurrent={status.model_download_current}
                        downloadTotal={status.model_download_total}
                    />
                )}
                {status.model_loading_error && !status.model_loading && (
                    <div className="model-error-banner" role="alert">
                        <span>Failed to load model: {status.model_loading_error}</span>
                    </div>
                )}

                {page === "home" && (
                    <HomeView
                        status={status}
                        currentModel={currentModel}
                        computeDevice={computeLabelFromDevice(settings?.transcription?.device)}
                        hotkeyLabel={formatHotkeyLabel(settings?.hotkey?.hold_key)}
                        entries={entries}
                        wordCount={wordCount}
                        goToSettings={() => setPage("settings")}
                        modelLoading={status.model_loading}
                    />
                )}
                {page === "history" && <HistoryView entries={entries} />}
                {page === "settings" && (
                    <SettingsView
                        settings={settings}
                        apiOk={apiOk}
                        settingsSaving={settingsSaving}
                        settingsError={settingsError}
                        currentModel={currentModel}
                        modelOptionsList={modelOptionsList}
                        currentHotkey={settings?.hotkey?.hold_key ?? "right_ctrl"}
                        modelLoading={status.model_loading}
                        cudaAvailable={cudaForSettings}
                        capabilities={capabilities}
                        currentDevice={currentDevice}
                        saveSettingsPatch={saveSettingsPatch}
                        gpuPackInstalling={gpuPackInstalling}
                        gpuPackMessage={gpuPackMessage}
                        gpuPackError={gpuPackError}
                        installGpuPack={installGpuPack}
                        downloadedModels={status.downloaded_models}
                    />
                )}
            </div>
        </>
    );
};

export default Dashboard;
