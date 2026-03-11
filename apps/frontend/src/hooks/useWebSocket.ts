"use client";

import { useRef, useCallback, useState } from 'react';

export type WSStatus = 'disconnected' | 'connecting' | 'connected' | 'error';

export interface UseWebSocketOptions {
    /** Max reconnection attempts (default: 3) */
    maxRetries?: number;
    /** Base delay between retries in ms (default: 2000). Actual delay uses exponential backoff. */
    retryDelay?: number;
    /** Called when the WS receives a message (parsed JSON or raw string) */
    onMessage: (data: any) => void;
    /** Called when a reconnection attempt starts */
    onReconnect?: (attempt: number) => void;
    /** Called when all reconnection attempts are exhausted */
    onFinalDisconnect?: () => void;
    /** Called on successful connection or reconnection */
    onOpen?: () => void;
    /** Called on connection close (before any retry) */
    onClose?: (code: number, reason: string) => void;
    /** Config message to send on (re)connect */
    configMessage?: Record<string, any>;
}

export interface UseWebSocketReturn {
    /** Current connection status */
    status: WSStatus;
    /** Connect to the given WebSocket URL */
    connect: (url: string) => void;
    /** Disconnect (intentional — no reconnect) */
    disconnect: () => void;
    /** Send raw binary data (ArrayBuffer) */
    sendBinary: (data: ArrayBuffer) => boolean;
    /** Send JSON message */
    sendJSON: (data: Record<string, any>) => boolean;
    /** Buffer binary data if WS is connecting */
    sendOrBuffer: (data: ArrayBuffer) => void;
    /** Reference to the underlying WebSocket */
    wsRef: React.MutableRefObject<WebSocket | null>;
}

/**
 * useWebSocket — a custom hook for WebSocket connections with:
 * - Exponential backoff reconnection
 * - Config message auto-resend on reconnect
 * - Pre-connection buffering
 * - session_end-aware (no reconnect after session end)
 */
export function useWebSocket(options: UseWebSocketOptions): UseWebSocketReturn {
    const {
        maxRetries = 3,
        retryDelay = 2000,
        onMessage,
        onReconnect,
        onFinalDisconnect,
        onOpen,
        onClose,
        configMessage,
    } = options;

    const [status, setStatus] = useState<WSStatus>('disconnected');
    const wsRef = useRef<WebSocket | null>(null);
    const urlRef = useRef<string>('');
    const retryCountRef = useRef(0);
    const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const intentionalCloseRef = useRef(false);
    const sessionEndedRef = useRef(false);
    const pendingChunksRef = useRef<ArrayBuffer[]>([]);

    const cleanup = useCallback(() => {
        if (retryTimerRef.current) {
            clearTimeout(retryTimerRef.current);
            retryTimerRef.current = null;
        }
    }, []);

    const createConnection = useCallback((url: string) => {
        // Clean up existing connection
        if (wsRef.current) {
            intentionalCloseRef.current = true;
            wsRef.current.close();
            wsRef.current = null;
        }

        setStatus('connecting');
        const ws = new WebSocket(url);
        wsRef.current = ws;

        ws.onopen = () => {
            setStatus('connected');
            retryCountRef.current = 0; // Reset retry counter on success

            // Flush buffered chunks
            const pending = pendingChunksRef.current;
            if (pending.length > 0) {
                console.log(`[useWebSocket] Flushing ${pending.length} buffered chunks`);
                for (const chunk of pending) {
                    ws.send(chunk);
                }
                pendingChunksRef.current = [];
            }

            // Send config message
            if (configMessage) {
                ws.send(JSON.stringify(configMessage));
            }

            onOpen?.();
        };

        ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);

                // Handle heartbeat internally
                if (msg.type === 'ping') {
                    ws.send(JSON.stringify({ type: 'pong' }));
                    return;
                }
                if (msg.type === 'pong') {
                    return;
                }

                // Mark session as ended — no reconnect after this
                if (msg.type === 'session_end') {
                    sessionEndedRef.current = true;
                }

                onMessage(msg);
            } catch {
                // Non-JSON message, pass through
                onMessage(event.data);
            }
        };

        ws.onerror = () => {
            setStatus('error');
        };

        ws.onclose = (ev) => {
            setStatus('disconnected');
            onClose?.(ev.code, ev.reason || '');

            // Don't reconnect if:
            // 1. Intentional close (user stopped recording)
            // 2. Session ended (backend sent session_end)
            // 3. Normal close (code 1000)
            if (intentionalCloseRef.current || sessionEndedRef.current || ev.code === 1000) {
                intentionalCloseRef.current = false;
                return;
            }

            // Attempt reconnection with exponential backoff
            if (retryCountRef.current < maxRetries) {
                retryCountRef.current++;
                const delay = retryDelay * Math.pow(2, retryCountRef.current - 1);
                console.log(
                    `[useWebSocket] Reconnecting in ${delay}ms (attempt ${retryCountRef.current}/${maxRetries})`
                );
                onReconnect?.(retryCountRef.current);

                retryTimerRef.current = setTimeout(() => {
                    createConnection(url);
                }, delay);
            } else {
                console.log('[useWebSocket] All reconnection attempts exhausted');
                onFinalDisconnect?.();
            }
        };
    }, [maxRetries, retryDelay, onMessage, onReconnect, onFinalDisconnect, onOpen, onClose, configMessage]);

    const connect = useCallback((url: string) => {
        urlRef.current = url;
        intentionalCloseRef.current = false;
        sessionEndedRef.current = false;
        retryCountRef.current = 0;
        pendingChunksRef.current = [];
        createConnection(url);
    }, [createConnection]);

    const disconnect = useCallback(() => {
        cleanup();
        intentionalCloseRef.current = true;
        if (wsRef.current) {
            wsRef.current.close();
            wsRef.current = null;
        }
        setStatus('disconnected');
    }, [cleanup]);

    const sendBinary = useCallback((data: ArrayBuffer): boolean => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
            wsRef.current.send(data);
            return true;
        }
        return false;
    }, []);

    const sendJSON = useCallback((data: Record<string, any>): boolean => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify(data));
            return true;
        }
        return false;
    }, []);

    const sendOrBuffer = useCallback((data: ArrayBuffer) => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
            wsRef.current.send(data);
        } else if (wsRef.current?.readyState === WebSocket.CONNECTING) {
            // Clone to prevent buffer reuse
            pendingChunksRef.current.push(data.slice(0));
        }
        // If CLOSING or CLOSED, drop silently
    }, []);

    return {
        status,
        connect,
        disconnect,
        sendBinary,
        sendJSON,
        sendOrBuffer,
        wsRef,
    };
}
