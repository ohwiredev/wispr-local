import { useEffect } from "react";
import { useAudioAnalyser } from "../hooks/useAudioAnalyser";
import { useWispr } from "../hooks/useWispr";
import { syncIndicatorWindow } from "../utils/indicatorWindow";

const BAR_COUNT = 16;
const MIN_SCALE = 0.08;

function WaveformBars({ levels }: { levels: Float32Array | null }) {
    return (
        <span className="waveform-bars" aria-hidden>
            {Array.from({ length: BAR_COUNT }, (_, i) => {
                const raw = levels ? (levels[i % levels.length] ?? 0) : 0;
                const scale = MIN_SCALE + raw * (1 - MIN_SCALE);
                return (
                    <span
                        key={i}
                        className="waveform-bars__bar"
                        style={{ transform: `scaleY(${scale})` }}
                    />
                );
            })}
        </span>
    );
}

function RecordingIcon() {
    return (
        <svg
            className="indicator-pill__svg"
            width="18"
            height="18"
            viewBox="0 0 20 20"
            aria-hidden
        >
            <circle cx="10" cy="10" r="6" fill="currentColor" />
        </svg>
    );
}

function ProcessingIcon() {
    return (
        <svg
            className="indicator-pill__svg indicator-pill__svg--spin"
            width="18"
            height="18"
            viewBox="0 0 20 20"
            aria-hidden
        >
            <circle
                cx="10"
                cy="10"
                r="7"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeDasharray="28 44"
            />
        </svg>
    );
}

const Indicator = () => {
    const { status } = useWispr();
    const recording = status.is_recording;
    const processing = !recording && status.is_processing;
    const active = recording || processing;
    const { levels } = useAudioAnalyser(recording);

    useEffect(() => {
        let cancelled = false;
        const isCancelled = () => cancelled;
        let intervalId: number | null = null;

        const runSync = async () => {
            try {
                await syncIndicatorWindow(active, isCancelled);
            } catch (e) {
                console.error("Indicator window sync failed", e);
            }
        };

        void runSync();

        if (active) {
            intervalId = window.setInterval(() => {
                void runSync();
            }, 400);
        }

        return () => {
            cancelled = true;
            if (intervalId !== null) {
                window.clearInterval(intervalId);
            }
        };
    }, [active]);

    if (!active) return null;

    const variantClass = recording ? "indicator-pill--recording" : "indicator-pill--processing";
    const label = recording ? "Recording..." : "Processing...";

    return (
        <div
            className={`indicator-pill ${variantClass}`}
            role="status"
        >
            <span className="indicator-pill__icon" aria-hidden>
                {recording ? <RecordingIcon /> : <ProcessingIcon />}
            </span>
            {recording && <WaveformBars levels={levels} />}
            <span className="indicator-pill__label">{label}</span>
        </div>
    );
};

export default Indicator;
