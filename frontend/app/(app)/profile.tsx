import React, { useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, Image,
  TextInput, ActivityIndicator, Alert, ScrollView, Switch,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import * as ImagePicker from 'expo-image-picker';
import { useAuth } from '../../contexts/AuthContext';
import COLORS from '../../constants/colors';

const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

export default function ProfileScreen() {
  const { user, token, logout, updateUser } = useAuth();
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const [newUsername, setNewUsername] = useState(user?.username || '');
  const [saving, setSaving] = useState(false);
  const [uploadingAvatar, setUploadingAvatar] = useState(false);
  const [togglingAnon, setTogglingAnon] = useState(false);

  const isAnonymous = (user as any)?.is_anonymous || false;
  const anonymousUsername = (user as any)?.anonymous_username || '';

  const handleToggleAnonymous = async (value: boolean) => {
    setTogglingAnon(true);
    try {
      const res = await fetch(`${BACKEND_URL}/api/users/anonymous`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ is_anonymous: value }),
      });
      if (res.ok) {
        const data = await res.json();
        updateUser(data.user);
      } else {
        Alert.alert('Error', 'Failed to toggle anonymous mode');
      }
    } catch (e) {
      Alert.alert('Error', 'Failed to toggle anonymous mode');
    } finally {
      setTogglingAnon(false);
    }
  };

  const handleSaveProfile = async () => {
    if (!newUsername.trim()) {
      Alert.alert('Error', 'Username cannot be empty');
      return;
    }
    setSaving(true);
    try {
      const res = await fetch(`${BACKEND_URL}/api/users/profile`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ username: newUsername.trim() }),
      });
      if (res.ok) {
        const data = await res.json();
        updateUser(data.user);
        setEditing(false);
      } else {
        const err = await res.json();
        Alert.alert('Error', err.detail || 'Failed to update');
      }
    } catch (e) {
      Alert.alert('Error', 'Failed to update profile');
    } finally {
      setSaving(false);
    }
  };

  const handlePickAvatar = async () => {
    const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert('Permission needed', 'Please grant photo library access');
      return;
    }

    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      allowsEditing: true,
      aspect: [1, 1],
      quality: 0.5,
      base64: true,
    });

    if (!result.canceled && result.assets[0]?.base64) {
      setUploadingAvatar(true);
      try {
        const base64Data = `data:image/jpeg;base64,${result.assets[0].base64}`;
        const res = await fetch(`${BACKEND_URL}/api/users/avatar`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ avatar: base64Data }),
        });
        if (res.ok) {
          const data = await res.json();
          updateUser({ ...user!, avatar: data.avatar });
        }
      } catch (e) {
        Alert.alert('Error', 'Failed to upload avatar');
      } finally {
        setUploadingAvatar(false);
      }
    }
  };

  const handleLogout = () => {
    Alert.alert('Logout', 'Are you sure you want to logout?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Logout',
        style: 'destructive',
        onPress: async () => {
          await logout();
          router.replace('/');
        },
      },
    ]);
  };

  const getAvatarSource = () => {
    if (user?.avatar) {
      if (user.avatar.startsWith('data:') || user.avatar.startsWith('http')) {
        return { uri: user.avatar };
      }
      return { uri: `data:image/jpeg;base64,${user.avatar}` };
    }
    return null;
  };

  return (
    <SafeAreaView style={styles.safeArea} edges={['top']}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Profile</Text>
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        {/* Avatar Section */}
        <View style={styles.avatarSection}>
          <TouchableOpacity
            testID="change-avatar-btn"
            onPress={handlePickAvatar}
            style={styles.avatarWrapper}
            activeOpacity={0.8}
          >
            {uploadingAvatar ? (
              <View style={styles.avatarLarge}>
                <ActivityIndicator color={COLORS.accent.primary} />
              </View>
            ) : getAvatarSource() ? (
              <Image source={getAvatarSource()!} style={styles.avatarLarge} />
            ) : (
              <View style={[styles.avatarLarge, styles.avatarPlaceholder]}>
                <Text style={styles.avatarInitialsLarge}>
                  {(user?.username || '?').charAt(0).toUpperCase()}
                </Text>
              </View>
            )}
            <View style={styles.cameraIconBadge}>
              <Ionicons name="camera" size={16} color={COLORS.text.inverse} />
            </View>
          </TouchableOpacity>

          {editing ? (
            <View style={styles.editUsernameRow}>
              <TextInput
                testID="edit-username-input"
                style={styles.editUsernameInput}
                value={newUsername}
                onChangeText={setNewUsername}
                autoFocus
                placeholderTextColor={COLORS.text.tertiary}
              />
              <TouchableOpacity
                testID="save-username-btn"
                onPress={handleSaveProfile}
                disabled={saving}
                style={styles.saveBtn}
              >
                {saving ? (
                  <ActivityIndicator size="small" color={COLORS.accent.primary} />
                ) : (
                  <Ionicons name="checkmark" size={24} color={COLORS.accent.primary} />
                )}
              </TouchableOpacity>
              <TouchableOpacity
                testID="cancel-edit-btn"
                onPress={() => { setEditing(false); setNewUsername(user?.username || ''); }}
                style={styles.cancelBtn}
              >
                <Ionicons name="close" size={24} color={COLORS.status.error} />
              </TouchableOpacity>
            </View>
          ) : (
            <TouchableOpacity
              testID="edit-username-btn"
              onPress={() => setEditing(true)}
              style={styles.usernameRow}
            >
              <Text style={styles.username}>{user?.username}</Text>
              <Ionicons name="pencil" size={16} color={COLORS.accent.primary} />
            </TouchableOpacity>
          )}
          <Text style={styles.email}>{user?.email}</Text>
        </View>

        {/* Info Section */}
        <View style={styles.infoSection}>
          <View style={styles.infoItem}>
            <View style={styles.infoIconContainer}>
              <Ionicons name="mail-outline" size={20} color={COLORS.accent.primary} />
            </View>
            <View style={styles.infoTextContainer}>
              <Text style={styles.infoLabel}>EMAIL</Text>
              <Text style={styles.infoValue}>{user?.email}</Text>
            </View>
          </View>

          <View style={styles.infoItem}>
            <View style={styles.infoIconContainer}>
              <Ionicons name="time-outline" size={20} color={COLORS.accent.primary} />
            </View>
            <View style={styles.infoTextContainer}>
              <Text style={styles.infoLabel}>MEMBER SINCE</Text>
              <Text style={styles.infoValue}>
                {user?.last_seen ? new Date(user.last_seen).toLocaleDateString() : 'N/A'}
              </Text>
            </View>
          </View>
        </View>

        {/* Anonymous Mode Section */}
        <View style={styles.anonSection}>
          <View style={styles.anonHeader}>
            <View style={styles.anonIconContainer}>
              <Ionicons name="eye-off" size={22} color={isAnonymous ? COLORS.accent.secondary : COLORS.text.tertiary} />
            </View>
            <View style={styles.anonTextContainer}>
              <Text style={styles.anonTitle}>Ghost Mode</Text>
              <Text style={styles.anonDescription}>
                {isAnonymous
                  ? `You appear as "${anonymousUsername}"`
                  : 'Hide your identity from others'}
              </Text>
            </View>
            <Switch
              testID="anonymous-toggle"
              value={isAnonymous}
              onValueChange={handleToggleAnonymous}
              disabled={togglingAnon}
              trackColor={{ false: COLORS.bg.tertiary, true: COLORS.accent.secondary }}
              thumbColor={isAnonymous ? COLORS.text.primary : COLORS.text.tertiary}
            />
          </View>
          {isAnonymous && (
            <View style={styles.anonActiveCard}>
              <View style={styles.anonActiveBadge}>
                <Ionicons name="shield-checkmark" size={16} color={COLORS.accent.secondary} />
                <Text style={styles.anonActiveText}>GHOST MODE ACTIVE</Text>
              </View>
              <View style={styles.anonIdentityRow}>
                <View style={styles.anonAvatarPlaceholder}>
                  <Ionicons name="skull-outline" size={24} color={COLORS.accent.secondary} />
                </View>
                <View style={styles.anonIdentityInfo}>
                  <Text style={styles.anonIdentityName}>{anonymousUsername}</Text>
                  <Text style={styles.anonIdentityHint}>Others see this identity</Text>
                </View>
              </View>
              <View style={styles.anonProtections}>
                <View style={styles.anonProtectionItem}>
                  <Ionicons name="checkmark-circle" size={14} color={COLORS.status.success} />
                  <Text style={styles.anonProtectionText}>Real name hidden</Text>
                </View>
                <View style={styles.anonProtectionItem}>
                  <Ionicons name="checkmark-circle" size={14} color={COLORS.status.success} />
                  <Text style={styles.anonProtectionText}>Avatar hidden</Text>
                </View>
                <View style={styles.anonProtectionItem}>
                  <Ionicons name="checkmark-circle" size={14} color={COLORS.status.success} />
                  <Text style={styles.anonProtectionText}>Email hidden</Text>
                </View>
              </View>
            </View>
          )}
        </View>

        {/* Logout */}
        <TouchableOpacity
          testID="logout-btn"
          style={styles.logoutBtn}
          onPress={handleLogout}
          activeOpacity={0.7}
        >
          <Ionicons name="log-out-outline" size={22} color={COLORS.status.error} />
          <Text style={styles.logoutText}>Logout</Text>
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: COLORS.bg.primary,
  },
  header: {
    height: 60,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 20,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255,255,255,0.06)',
  },
  headerTitle: {
    fontSize: 28,
    fontWeight: '800',
    color: COLORS.text.primary,
    letterSpacing: 0.5,
  },
  content: {
    paddingVertical: 32,
    alignItems: 'center',
  },
  avatarSection: {
    alignItems: 'center',
    marginBottom: 40,
  },
  avatarWrapper: {
    position: 'relative',
    marginBottom: 16,
  },
  avatarLarge: {
    width: 100,
    height: 100,
    borderRadius: 38,
    backgroundColor: COLORS.bg.tertiary,
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 2,
    borderColor: COLORS.accent.primary,
  },
  avatarPlaceholder: {
    backgroundColor: COLORS.bg.tertiary,
    borderWidth: 2,
    borderColor: COLORS.accent.primary,
  },
  avatarInitialsLarge: {
    fontSize: 40,
    fontWeight: '700',
    color: COLORS.accent.primary,
  },
  cameraIconBadge: {
    position: 'absolute',
    bottom: 0,
    right: 0,
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: COLORS.accent.primary,
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 2,
    borderColor: COLORS.bg.primary,
  },
  usernameRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  username: {
    fontSize: 24,
    fontWeight: '700',
    color: COLORS.text.primary,
  },
  editUsernameRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  editUsernameInput: {
    fontSize: 20,
    fontWeight: '600',
    color: COLORS.text.primary,
    borderBottomWidth: 2,
    borderBottomColor: COLORS.accent.primary,
    paddingVertical: 4,
    minWidth: 150,
    textAlign: 'center',
  },
  saveBtn: {
    width: 40,
    height: 40,
    justifyContent: 'center',
    alignItems: 'center',
  },
  cancelBtn: {
    width: 40,
    height: 40,
    justifyContent: 'center',
    alignItems: 'center',
  },
  email: {
    fontSize: 14,
    color: COLORS.text.secondary,
    marginTop: 4,
  },
  infoSection: {
    width: '100%',
    paddingHorizontal: 20,
    gap: 2,
  },
  infoItem: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: COLORS.bg.secondary,
    paddingHorizontal: 16,
    paddingVertical: 16,
    borderRadius: 16,
    marginBottom: 8,
    gap: 14,
  },
  infoIconContainer: {
    width: 40,
    height: 40,
    borderRadius: 12,
    backgroundColor: COLORS.bg.tertiary,
    justifyContent: 'center',
    alignItems: 'center',
  },
  infoTextContainer: {
    flex: 1,
  },
  infoLabel: {
    fontSize: 10,
    fontWeight: '600',
    color: COLORS.text.tertiary,
    letterSpacing: 1,
    marginBottom: 2,
  },
  infoValue: {
    fontSize: 15,
    color: COLORS.text.primary,
    fontWeight: '500',
  },
  logoutBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    marginTop: 40,
    paddingHorizontal: 32,
    paddingVertical: 14,
    borderRadius: 28,
    borderWidth: 1,
    borderColor: COLORS.status.error,
  },
  logoutText: {
    fontSize: 16,
    fontWeight: '600',
    color: COLORS.status.error,
  },
  anonSection: {
    width: '100%',
    paddingHorizontal: 20,
    marginTop: 24,
  },
  anonHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: COLORS.bg.secondary,
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderRadius: 16,
    gap: 12,
  },
  anonIconContainer: {
    width: 40,
    height: 40,
    borderRadius: 12,
    backgroundColor: COLORS.bg.tertiary,
    justifyContent: 'center',
    alignItems: 'center',
  },
  anonTextContainer: {
    flex: 1,
  },
  anonTitle: {
    fontSize: 15,
    fontWeight: '700',
    color: COLORS.text.primary,
  },
  anonDescription: {
    fontSize: 12,
    color: COLORS.text.secondary,
    marginTop: 2,
  },
  anonActiveCard: {
    marginTop: 10,
    backgroundColor: 'rgba(112, 0, 255, 0.08)',
    borderRadius: 16,
    padding: 16,
    borderWidth: 1,
    borderColor: 'rgba(112, 0, 255, 0.2)',
  },
  anonActiveBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginBottom: 12,
  },
  anonActiveText: {
    fontSize: 10,
    fontWeight: '800',
    color: COLORS.accent.secondary,
    letterSpacing: 1.5,
  },
  anonIdentityRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    marginBottom: 12,
  },
  anonAvatarPlaceholder: {
    width: 44,
    height: 44,
    borderRadius: 16,
    backgroundColor: 'rgba(112, 0, 255, 0.15)',
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: 'rgba(112, 0, 255, 0.3)',
  },
  anonIdentityInfo: {
    flex: 1,
  },
  anonIdentityName: {
    fontSize: 17,
    fontWeight: '700',
    color: COLORS.text.primary,
  },
  anonIdentityHint: {
    fontSize: 12,
    color: COLORS.text.tertiary,
    marginTop: 2,
  },
  anonProtections: {
    gap: 6,
  },
  anonProtectionItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  anonProtectionText: {
    fontSize: 13,
    color: COLORS.text.secondary,
  },
});
