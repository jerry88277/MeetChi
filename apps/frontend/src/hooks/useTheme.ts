"use client";

import { useState, useEffect, useCallback } from 'react';

export type Theme = 'light' | 'dark';

export function useTheme() {
    const [theme, setThemeState] = useState<Theme>('light');

    useEffect(() => {
        const saved = localStorage.getItem('meetchi-theme') as Theme | null;
        const initial = saved || 'light';
        setThemeState(initial);
        document.documentElement.setAttribute('data-theme', initial);
    }, []);

    const setTheme = useCallback((t: Theme) => {
        setThemeState(t);
        localStorage.setItem('meetchi-theme', t);
        document.documentElement.setAttribute('data-theme', t);
    }, []);

    const toggleTheme = useCallback(() => {
        setTheme(theme === 'light' ? 'dark' : 'light');
    }, [theme, setTheme]);

    return { theme, setTheme, toggleTheme };
}
