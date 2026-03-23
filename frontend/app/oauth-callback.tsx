import React, { useEffect } from 'react';
import { View, ActivityIndicator, StyleSheet } from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { useAuth } from '../contexts/AuthContext';
import COLORS from '../constants/colors';
import * as Linking from 'expo-linking';

export default function OAuthCallback() {
  const router = useRouter();
  const { handleGoogleAuth } = useAuth();

  useEffect(() => {
    const processAuth = async () => {
      try {
        const url = await Linking.getInitialURL();
        if (url && url.includes('session_id=')) {
          const sessionId = url.split('session_id=')[1]?.split('&')[0]?.split('#')[0];
          if (sessionId) {
            await handleGoogleAuth(sessionId);
            router.replace('/(app)/chats');
            return;
          }
        }
        router.replace('/');
      } catch (e) {
        console.error('OAuth callback error:', e);
        router.replace('/');
      }
    };
    processAuth();
  }, []);

  return (
    <View style={styles.container}>
      <ActivityIndicator size="large" color={COLORS.accent.primary} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.bg.primary,
    justifyContent: 'center',
    alignItems: 'center',
  },
});
