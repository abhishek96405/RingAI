import { useEffect, useRef, useState, useCallback } from "react";
import { getAuthToken } from "../lib/api";

export interface WebSocketNotification {
  type: string;
  event: string;
  title: string;
  message: string;
  data: Record<string, unknown>;
  priority: string;
  timestamp: string;
}

interface UseWebSocketNotificationsOptions {
  restaurantId?: string | null;
  onNotification?: (notification: WebSocketNotification) => void;
  autoReconnect?: boolean;
  reconnectDelay?: number;
}

interface UseWebSocketNotificationsReturn {
  connected: boolean;
  notifications: WebSocketNotification[];
  clearNotifications: () => void;
  sendMessage: (message: string) => void;
}

export function useWebSocketNotifications(
  options: UseWebSocketNotificationsOptions = {}
): UseWebSocketNotificationsReturn {
  const {
    restaurantId,
    onNotification,
    autoReconnect = true,
    reconnectDelay = 5000,
  } = options;

  const [connected, setConnected] = useState(false);
  const [notifications, setNotifications] = useState<WebSocketNotification[]>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const mountedRef = useRef(true);

  const clearNotifications = useCallback(() => {
    setNotifications([]);
  }, []);

  const sendMessage = useCallback((message: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(message);
    }
  }, []);

  const connect = useCallback(async () => {
    if (!mountedRef.current) return;

    // Build WebSocket URL
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const backendUrl = import.meta.env.VITE_BACKEND_WS_URL ||
      `${protocol}//${window.location.host}`;

    // Auth: fetch a fresh Clerk token for THIS connection attempt.
    const token = await getAuthToken();

    // Don't open an unauthenticated socket. If we have no restaurant or no
    // token yet (e.g. Clerk still loading), retry shortly instead.
    if (!restaurantId || !token) {
      if (autoReconnect && mountedRef.current) {
        reconnectTimeoutRef.current = setTimeout(() => {
          if (mountedRef.current) connect();
        }, reconnectDelay);
      }
      return;
    }

    const wsUrl =
      `${backendUrl}/ws/notifications` +
      `?restaurant_id=${encodeURIComponent(restaurantId)}` +
      `&token=${encodeURIComponent(token)}`;

    console.log("[WS] Connecting to:", `${backendUrl}/ws/notifications`);

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      if (!mountedRef.current) return;
      console.log("[WS] Connected");
      setConnected(true);
    };

    ws.onmessage = (event) => {
      if (!mountedRef.current) return;
      
      try {
        // Handle ping/pong
        if (event.data === "ping") {
          ws.send("pong");
          return;
        }
        if (event.data === "pong") {
          return;
        }

        const data = JSON.parse(event.data);
        
        // Handle connection confirmation
        if (data.type === "connected") {
          console.log("[WS] Connection confirmed:", data.message);
          return;
        }

        // Handle notifications
        if (data.type === "notification") {
          const notification: WebSocketNotification = {
            type: data.type,
            event: data.event,
            title: data.title,
            message: data.message,
            data: data.data || {},
            priority: data.priority || "normal",
            timestamp: data.timestamp || new Date().toISOString(),
          };

          setNotifications((prev) => [notification, ...prev].slice(0, 50)); // Keep last 50
          
          if (onNotification) {
            onNotification(notification);
          }
        }
      } catch (e) {
        console.warn("[WS] Failed to parse message:", e);
      }
    };

    ws.onerror = (error) => {
      console.error("[WS] Error:", error);
    };

    ws.onclose = (event) => {
      if (!mountedRef.current) return;
      
      console.log("[WS] Disconnected:", event.code, event.reason);
      setConnected(false);
      wsRef.current = null;

      // Auto-reconnect
      if (autoReconnect && mountedRef.current) {
        console.log(`[WS] Reconnecting in ${reconnectDelay / 1000}s...`);
        reconnectTimeoutRef.current = setTimeout(() => {
          if (mountedRef.current) {
            connect();
          }
        }, reconnectDelay);
      }
    };
  }, [restaurantId, onNotification, autoReconnect, reconnectDelay]);

  useEffect(() => {
    mountedRef.current = true;
    connect();

    // Set up ping interval
    const pingInterval = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send("ping");
      }
    }, 25000);

    return () => {
      mountedRef.current = false;
      
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      
      clearInterval(pingInterval);
      
      if (wsRef.current) {
        wsRef.current.close(1000, "Component unmounted");
        wsRef.current = null;
      }
    };
  }, [connect]);

  return {
    connected,
    notifications,
    clearNotifications,
    sendMessage,
  };
}

export default useWebSocketNotifications;
