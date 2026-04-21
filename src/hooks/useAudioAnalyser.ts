import { useCallback, useEffect, useRef, useState } from "react";

const FFT_SIZE = 64;
const BIN_COUNT = FFT_SIZE / 2;

/**
 * Captures microphone input via the Web Audio API and returns a
 * normalised frequency-domain amplitude array (0–1) that updates
 * every animation frame while `active` is true.
 */
export function useAudioAnalyser(active: boolean) {
    const [levels, setLevels] = useState<Float32Array | null>(null);

    const ctxRef = useRef<AudioContext | null>(null);
    const analyserRef = useRef<AnalyserNode | null>(null);
    const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
    const streamRef = useRef<MediaStream | null>(null);
    const rafRef = useRef<number>(0);

    const tick = useCallback(() => {
        const analyser = analyserRef.current;
        if (!analyser) return;

        const buf = new Uint8Array(analyser.frequencyBinCount);
        analyser.getByteFrequencyData(buf);

        const normalised = new Float32Array(buf.length);
        for (let i = 0; i < buf.length; i++) {
            normalised[i] = buf[i] / 255;
        }
        setLevels(normalised);
        rafRef.current = requestAnimationFrame(tick);
    }, []);

    useEffect(() => {
        if (!active) {
            setLevels(null);
            return;
        }

        let cancelled = false;

        (async () => {
            try {
                const stream = await navigator.mediaDevices.getUserMedia({
                    audio: true,
                });
                if (cancelled) {
                    stream.getTracks().forEach((t) => t.stop());
                    return;
                }
                streamRef.current = stream;

                const ctx = new AudioContext();
                ctxRef.current = ctx;

                const source = ctx.createMediaStreamSource(stream);
                sourceRef.current = source;

                const analyser = ctx.createAnalyser();
                analyser.fftSize = FFT_SIZE;
                analyser.smoothingTimeConstant = 0.6;
                analyserRef.current = analyser;

                source.connect(analyser);

                rafRef.current = requestAnimationFrame(tick);
            } catch (err) {
                console.warn("Microphone access denied for waveform:", err);
            }
        })();

        return () => {
            cancelled = true;
            cancelAnimationFrame(rafRef.current);
            sourceRef.current?.disconnect();
            sourceRef.current = null;
            analyserRef.current = null;
            void ctxRef.current?.close();
            ctxRef.current = null;
            streamRef.current?.getTracks().forEach((t) => t.stop());
            streamRef.current = null;
        };
    }, [active, tick]);

    return { levels, binCount: BIN_COUNT };
}
