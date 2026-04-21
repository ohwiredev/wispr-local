import { useCallback, useState } from "react";

const STORAGE_KEY = "wispr_weekly_words";

interface StoredData {
  weekStart: string;
  count: number;
}

function getWeekStart(): string {
  const now = new Date();
  const day = now.getDay();
  const diff = day === 0 ? 6 : day - 1; // Monday = 0 offset
  const monday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - diff);
  return monday.toISOString().slice(0, 10);
}

function load(): StoredData {
  const currentWeek = getWeekStart();
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as StoredData;
      if (parsed.weekStart === currentWeek) return parsed;
    }
  } catch { /* corrupted data — reset */ }
  return { weekStart: currentWeek, count: 0 };
}

function save(data: StoredData) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
}

export function useWeeklyWords() {
  const [wordCount, setWordCount] = useState(() => load().count);

  const addWords = useCallback((text: string) => {
    const words = text.trim().split(/\s+/).filter(Boolean).length;
    if (words === 0) return;
    const data = load();
    data.count += words;
    save(data);
    setWordCount(data.count);
  }, []);

  return { wordCount, addWords };
}
