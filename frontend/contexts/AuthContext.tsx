import React, { createContext, useContext, useState, useEffect, useRef, useCallback } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { io, Socket } from 'socket.io-client';

const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

interface User {
  user_id: string;
  email: string;
  username: string;
  avatar?: string | null;
  is_online?: boolean;
  last_seen?: string;
}

interface PresenceInfo {
  is_online: boolean;
  last_seen: string | null;
}

interface AuthContextType {
  user: User | null;
  token: string | null;
  loading: boolean;
  socket: Socket | null;
  presence: Record<string, PresenceInfo>;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, username: string, password: string) => Promise<void>;
  handleGoogleAuth: (sessionId: string) => Promise<void>;
  logout: () => Promise<void>;
  updateUser: (user: User) => void;
  getPresence: (userId: string) => PresenceInfo;
}

const defaultPresence: PresenceInfo = { is_online: false, last_seen: null };

const AuthContext = createContext<AuthContextType>({
  user: null,
  token: null,
  loading: true,
  socket: null,
  presence: {},
  login: async () => {},
  signup: async () => {},
  handleGoogleAuth: async () => {},
  logout: async () => {},
  updateUser: () => {},
  getPresence: () => defaultPresence,
});

export const useAuth = () => useContext(AuthContext);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [presence, setPresence] = useState<Record<string, PresenceInfo>>({});
  const socketRef = useRef<Socket | null>(null);

  // Efficient presence updater — only touches the changed user
  const handleUserOnline = useCallback((data: { user_id: string }) => {
    setPresence(prev => ({
      ...prev,
      [data.user_id]: { is_online: true, last_seen: null },
    }));
  }, []);

  const handleUserOffline = useCallback((data: { user_id: string; last_seen?: string }) => {
    setPresence(prev => ({
      ...prev,
      [data.user_id]: { is_online: false, last_seen: data.last_seen || new Date().toISOString() },
    }));
  }, []);

  const getPresence = useCallback((userId: string): PresenceInfo => {
    return presence[userId] || defaultPresence;
  }, [presence]);

  const connectSocket = useCallback((authToken: string) => {
    if (socketRef.current?.connected) return;
    
    const newSocket = io(BACKEND_URL, {
      path: '/api/socket.io',
      transports: ['websocket', 'polling'],
      autoConnect: true,
    });

    newSocket.on('connect', () => {
      console.log('Socket connected');
      newSocket.emit('authenticate', { token: authToken });
    });

    newSocket.on('authenticated', (data: any) => {
      console.log('Socket authenticated:', data.user_id);
    });

    // Global presence listeners — fire on every screen
    newSocket.on('user_online', handleUserOnline);
    newSocket.on('user_offline', handleUserOffline);

    newSocket.on('disconnect', () => {
      console.log('Socket disconnected');
    });

    socketRef.current = newSocket;
  }, [handleUserOnline, handleUserOffline]);

  const disconnectSocket = useCallback(() => {
    if (socketRef.current) {
      socketRef.current.off('user_online', handleUserOnline);
      socketRef.current.off('user_offline', handleUserOffline);
      socketRef.current.disconnect();
      socketRef.current = null;
    }
  }, [handleUserOnline, handleUserOffline]);

  useEffect(() => {
    const loadAuth = async () => {
      try {
        const savedToken = await AsyncStorage.getItem('auth_token');
        if (savedToken) {
          const res = await fetch(`${BACKEND_URL}/api/auth/me`, {
            headers: { 'Authorization': `Bearer ${savedToken}` },
          });
          if (res.ok) {
            const data = await res.json();
            setUser(data.user);
            setToken(savedToken);
            connectSocket(savedToken);
          } else {
            await AsyncStorage.removeItem('auth_token');
          }
        }
      } catch (e) {
        console.error('Auth load error:', e);
      } finally {
        setLoading(false);
      }
    };
    loadAuth();
    return () => disconnectSocket();
  }, []);

  const login = async (email: string, password: string) => {
    const res = await fetch(`${BACKEND_URL}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Login failed');
    }
    const data = await res.json();
    await AsyncStorage.setItem('auth_token', data.token);
    setToken(data.token);
    setUser(data.user);
    connectSocket(data.token);
  };

  const signup = async (email: string, username: string, password: string) => {
    const res = await fetch(`${BACKEND_URL}/api/auth/signup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, username, password }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Signup failed');
    }
    const data = await res.json();
    await AsyncStorage.setItem('auth_token', data.token);
    setToken(data.token);
    setUser(data.user);
    connectSocket(data.token);
  };

  const handleGoogleAuth = async (sessionId: string) => {
    const res = await fetch(`${BACKEND_URL}/api/auth/session?session_id=${sessionId}`);
    if (!res.ok) {
      throw new Error('Google auth failed');
    }
    const data = await res.json();
    await AsyncStorage.setItem('auth_token', data.token);
    setToken(data.token);
    setUser(data.user);
    connectSocket(data.token);
  };

  const logout = async () => {
    try {
      await fetch(`${BACKEND_URL}/api/auth/logout`, {
        method: 'POST',
        headers: token ? { 'Authorization': `Bearer ${token}` } : {},
      });
    } catch (e) {}
    disconnectSocket();
    await AsyncStorage.removeItem('auth_token');
    setUser(null);
    setToken(null);
    setPresence({});
  };

  const updateUser = (updatedUser: User) => {
    setUser(updatedUser);
  };

  return (
    <AuthContext.Provider value={{
      user, token, loading, socket: socketRef.current, presence,
      login, signup, handleGoogleAuth, logout, updateUser, getPresence,
    }}>
      {children}
    </AuthContext.Provider>
  );
};
