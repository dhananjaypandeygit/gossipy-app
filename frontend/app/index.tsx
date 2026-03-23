import React, { useState, useEffect } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  KeyboardAvoidingView, Platform, ActivityIndicator, Alert, ScrollView,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../contexts/AuthContext';
import COLORS from '../constants/colors';
import * as WebBrowser from 'expo-web-browser';
import * as Linking from 'expo-linking';

export default function AuthScreen() {
  const { user, loading, login, signup, handleGoogleAuth } = useAuth();
  const router = useRouter();
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!loading && user) {
      router.replace('/(app)/chats');
    }
  }, [user, loading]);

  // Listen for OAuth callback
  useEffect(() => {
    const handleUrl = async (event: { url: string }) => {
      const url = event.url;
      if (url && url.includes('session_id=')) {
        const sessionId = url.split('session_id=')[1]?.split('&')[0]?.split('#')[0];
        if (sessionId) {
          try {
            setSubmitting(true);
            await handleGoogleAuth(sessionId);
            router.replace('/(app)/chats');
          } catch (e: any) {
            Alert.alert('Error', e.message || 'Google auth failed');
          } finally {
            setSubmitting(false);
          }
        }
      }
    };

    const subscription = Linking.addEventListener('url', handleUrl);
    return () => subscription.remove();
  }, []);

  const handleSubmit = async () => {
    if (submitting) return;
    if (!email || !password) {
      Alert.alert('Error', 'Please fill in all fields');
      return;
    }
    if (!isLogin && !username) {
      Alert.alert('Error', 'Please enter a username');
      return;
    }
    setSubmitting(true);
    try {
      if (isLogin) {
        await login(email.trim(), password);
      } else {
        await signup(email.trim(), username.trim(), password);
      }
      router.replace('/(app)/chats');
    } catch (e: any) {
      Alert.alert('Error', e.message || 'Authentication failed');
    } finally {
      setSubmitting(false);
    }
  };

  // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
  const handleGoogleLogin = async () => {
    try {
      const callbackUrl = Linking.createURL('oauth-callback');
      const authUrl = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(callbackUrl)}`;
      await WebBrowser.openBrowserAsync(authUrl);
    } catch (e) {
      console.error('Google auth error:', e);
    }
  };

  if (loading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color={COLORS.accent.primary} />
      </View>
    );
  }

  return (
    <SafeAreaView style={styles.safeArea}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={styles.container}
      >
        <ScrollView contentContainerStyle={styles.scrollContent} keyboardShouldPersistTaps="handled">
          {/* Header */}
          <View style={styles.headerSection}>
            <View style={styles.logoContainer}>
              <Ionicons name="chatbubble-ellipses" size={48} color={COLORS.accent.primary} />
            </View>
            <Text style={styles.appTitle}>NeonVoid</Text>
            <Text style={styles.appSubtitle}>ENCRYPTED MESSAGING</Text>
          </View>

          {/* Form */}
          <View style={styles.formSection}>
            <Text style={styles.formTitle}>{isLogin ? 'Welcome Back' : 'Create Account'}</Text>

            {!isLogin && (
              <View style={styles.inputContainer} testID="username-input-container">
                <Ionicons name="person-outline" size={20} color={COLORS.text.tertiary} />
                <TextInput
                  testID="username-input"
                  style={styles.input}
                  placeholder="Username"
                  placeholderTextColor={COLORS.text.tertiary}
                  value={username}
                  onChangeText={setUsername}
                  autoCapitalize="none"
                />
              </View>
            )}

            <View style={styles.inputContainer} testID="email-input-container">
              <Ionicons name="mail-outline" size={20} color={COLORS.text.tertiary} />
              <TextInput
                testID="email-input"
                style={styles.input}
                placeholder="Email"
                placeholderTextColor={COLORS.text.tertiary}
                value={email}
                onChangeText={setEmail}
                keyboardType="email-address"
                autoCapitalize="none"
              />
            </View>

            <View style={styles.inputContainer} testID="password-input-container">
              <Ionicons name="lock-closed-outline" size={20} color={COLORS.text.tertiary} />
              <TextInput
                testID="password-input"
                style={styles.input}
                placeholder="Password"
                placeholderTextColor={COLORS.text.tertiary}
                value={password}
                onChangeText={setPassword}
                secureTextEntry={!showPassword}
              />
              <TouchableOpacity testID="toggle-password-btn" onPress={() => setShowPassword(!showPassword)}>
                <Ionicons name={showPassword ? 'eye-off-outline' : 'eye-outline'} size={20} color={COLORS.text.tertiary} />
              </TouchableOpacity>
            </View>

            <TouchableOpacity
              testID="auth-submit-btn"
              style={[styles.primaryBtn, submitting && styles.disabledBtn]}
              onPress={handleSubmit}
              disabled={submitting}
              activeOpacity={0.8}
            >
              {submitting ? (
                <ActivityIndicator color={COLORS.text.inverse} />
              ) : (
                <Text style={styles.primaryBtnText}>
                  {isLogin ? 'Sign In' : 'Create Account'}
                </Text>
              )}
            </TouchableOpacity>

            {/* Divider */}
            <View style={styles.dividerRow}>
              <View style={styles.dividerLine} />
              <Text style={styles.dividerText}>OR</Text>
              <View style={styles.dividerLine} />
            </View>

            {/* Google */}
            <TouchableOpacity
              testID="google-auth-btn"
              style={styles.googleBtn}
              onPress={handleGoogleLogin}
              activeOpacity={0.8}
            >
              <Ionicons name="logo-google" size={20} color={COLORS.text.primary} />
              <Text style={styles.googleBtnText}>Continue with Google</Text>
            </TouchableOpacity>

            {/* Toggle */}
            <TouchableOpacity
              testID="toggle-auth-mode-btn"
              style={styles.toggleRow}
              onPress={() => setIsLogin(!isLogin)}
            >
              <Text style={styles.toggleText}>
                {isLogin ? "Don't have an account? " : 'Already have an account? '}
              </Text>
              <Text style={styles.toggleLink}>{isLogin ? 'Sign Up' : 'Sign In'}</Text>
            </TouchableOpacity>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  loadingContainer: {
    flex: 1,
    backgroundColor: COLORS.bg.primary,
    justifyContent: 'center',
    alignItems: 'center',
  },
  safeArea: {
    flex: 1,
    backgroundColor: COLORS.bg.primary,
  },
  container: {
    flex: 1,
  },
  scrollContent: {
    flexGrow: 1,
    paddingHorizontal: 24,
    justifyContent: 'center',
  },
  headerSection: {
    alignItems: 'center',
    marginBottom: 48,
  },
  logoContainer: {
    width: 88,
    height: 88,
    borderRadius: 32,
    backgroundColor: COLORS.bg.secondary,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 16,
    borderWidth: 1,
    borderColor: COLORS.accent.primary,
    shadowColor: COLORS.accent.primary,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 12,
    elevation: 8,
  },
  appTitle: {
    fontSize: 36,
    fontWeight: '900',
    color: COLORS.text.primary,
    letterSpacing: 2,
  },
  appSubtitle: {
    fontSize: 12,
    fontWeight: '600',
    color: COLORS.accent.primary,
    letterSpacing: 4,
    marginTop: 4,
  },
  formSection: {
    width: '100%',
  },
  formTitle: {
    fontSize: 24,
    fontWeight: '700',
    color: COLORS.text.primary,
    marginBottom: 24,
  },
  inputContainer: {
    height: 50,
    borderRadius: 25,
    backgroundColor: COLORS.bg.secondary,
    borderWidth: 1,
    borderColor: COLORS.border.subtle,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    marginBottom: 12,
    gap: 12,
  },
  input: {
    flex: 1,
    color: COLORS.text.primary,
    fontSize: 16,
  },
  primaryBtn: {
    height: 56,
    borderRadius: 28,
    backgroundColor: COLORS.accent.primary,
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: 8,
    shadowColor: COLORS.accent.primary,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 8,
  },
  disabledBtn: {
    opacity: 0.6,
  },
  primaryBtnText: {
    fontSize: 16,
    fontWeight: '700',
    color: COLORS.text.inverse,
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  dividerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginVertical: 24,
  },
  dividerLine: {
    flex: 1,
    height: 1,
    backgroundColor: COLORS.border.subtle,
  },
  dividerText: {
    color: COLORS.text.tertiary,
    fontSize: 12,
    fontWeight: '600',
    marginHorizontal: 16,
    letterSpacing: 2,
  },
  googleBtn: {
    height: 56,
    borderRadius: 28,
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: COLORS.border.subtle,
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    gap: 12,
  },
  googleBtnText: {
    fontSize: 16,
    fontWeight: '600',
    color: COLORS.text.primary,
  },
  toggleRow: {
    flexDirection: 'row',
    justifyContent: 'center',
    marginTop: 24,
    paddingVertical: 8,
  },
  toggleText: {
    color: COLORS.text.secondary,
    fontSize: 14,
  },
  toggleLink: {
    color: COLORS.accent.primary,
    fontSize: 14,
    fontWeight: '700',
  },
});
