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

interface AuthContextType {
  user: User | null;
  token: string | null;
  loading: boolean;
  socket: Socket | null;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, username: string, password: string) => Promise<void>;
  handleGoogleAuth: (sessionId: string) => Promise<void>;
  logout: () => Promise<void>;
  updateUser: (user: User) => void;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  token: null,
  loading: true,
  socket: null,
  login: async () => {},
  signup: async () => {},
  handleGoogleAuth: async () => {},
  logout: async () => {},
  updateUser: () => {},
});

export const useAuth = () => useContext(AuthContext);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const socketRef = useRef<Socket | null>(null);

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

    newSocket.on('disconnect', () => {
      console.log('Socket disconnected');
    });

    socketRef.current = newSocket;
  }, []);

  const disconnectSocket = useCallback(() => {
    if (socketRef.current) {
      socketRef.current.disconnect();
      socketRef.current = null;
    }
  }, []);

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
  };

  const updateUser = (updatedUser: User) => {
    setUser(updatedUser);
  };

  return (
    <AuthContext.Provider value={{
      user, token, loading, socket: socketRef.current,
      login, signup, handleGoogleAuth, logout, updateUser
    }}>
      {children}
    </AuthContext.Provider>
  );
};
