import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, FlatList,
  ActivityIndicator, Image, Platform, Alert, RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as Location from 'expo-location';
import { useAuth } from '../../contexts/AuthContext';
import COLORS from '../../constants/colors';

const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

const RADIUS_OPTIONS = [
  { label: '10m', value: 10 },
  { label: '50m', value: 50 },
  { label: '100m', value: 100 },
  { label: '500m', value: 500 },
];

interface NearbyUser {
  user_id: string;
  username: string;
  email: string;
  avatar?: string | null;
  is_online: boolean;
  distance_meters: number;
}

export default function NearbyScreen() {
  const { token, socket } = useAuth();
  const router = useRouter();
  const [nearbyUsers, setNearbyUsers] = useState<NearbyUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [selectedRadius, setSelectedRadius] = useState(500);
  const [locationPermission, setLocationPermission] = useState<boolean | null>(null);
  const [currentLocation, setCurrentLocation] = useState<{ latitude: number; longitude: number } | null>(null);
  const [locationError, setLocationError] = useState<string | null>(null);
  const [joiningRoom, setJoiningRoom] = useState(false);
  const locationWatcherRef = useRef<Location.LocationSubscription | null>(null);
  const lastUpdateRef = useRef<number>(0);

  // Request location permissions
  useEffect(() => {
    const requestPermission = async () => {
      try {
        const { status } = await Location.requestForegroundPermissionsAsync();
        setLocationPermission(status === 'granted');
        if (status !== 'granted') {
          setLocationError('Location permission denied');
          setLoading(false);
        }
      } catch (e) {
        setLocationError('Failed to get location permission');
        setLoading(false);
      }
    };
    requestPermission();
  }, []);

  // Start watching location with battery optimization
  useEffect(() => {
    if (locationPermission !== true) return;

    const startWatching = async () => {
      try {
        // Get initial position quickly
        const initialLocation = await Location.getCurrentPositionAsync({
          accuracy: Location.Accuracy.Balanced,
        });
        const coords = {
          latitude: initialLocation.coords.latitude,
          longitude: initialLocation.coords.longitude,
        };
        setCurrentLocation(coords);
        updateServerLocation(coords);
        fetchNearbyUsers(coords);

        // Watch position with battery-optimized settings
        const watcher = await Location.watchPositionAsync(
          {
            accuracy: Location.Accuracy.Balanced,
            distanceInterval: 10, // Only update when moved 10m+
            timeInterval: 30000,  // At most every 30 seconds
          },
          (location) => {
            const now = Date.now();
            // Throttle updates to max once per 15 seconds
            if (now - lastUpdateRef.current < 15000) return;
            lastUpdateRef.current = now;

            const newCoords = {
              latitude: location.coords.latitude,
              longitude: location.coords.longitude,
            };
            setCurrentLocation(newCoords);
            updateServerLocation(newCoords);
          }
        );
        locationWatcherRef.current = watcher;
      } catch (e) {
        console.error('Location watch error:', e);
        setLocationError('Failed to get location');
        setLoading(false);
      }
    };

    startWatching();

    return () => {
      if (locationWatcherRef.current) {
        locationWatcherRef.current.remove();
        locationWatcherRef.current = null;
      }
    };
  }, [locationPermission]);

  // Re-fetch nearby users when radius changes
  useEffect(() => {
    if (currentLocation) {
      fetchNearbyUsers(currentLocation);
    }
  }, [selectedRadius]);

  const updateServerLocation = useCallback(async (coords: { latitude: number; longitude: number }) => {
    try {
      // Use Socket.IO for real-time location update (more efficient than REST)
      if (socket?.connected) {
        socket.emit('update_location', coords);
      } else {
        await fetch(`${BACKEND_URL}/api/users/location`, {
          method: 'PUT',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(coords),
        });
      }
    } catch (e) {
      console.error('Update location error:', e);
    }
  }, [socket, token]);

  const fetchNearbyUsers = useCallback(async (coords: { latitude: number; longitude: number }) => {
    try {
      const res = await fetch(
        `${BACKEND_URL}/api/users/nearby?latitude=${coords.latitude}&longitude=${coords.longitude}&radius=${selectedRadius}`,
        { headers: { 'Authorization': `Bearer ${token}` } }
      );
      if (res.ok) {
        const data = await res.json();
        setNearbyUsers(data.users);
      }
    } catch (e) {
      console.error('Fetch nearby error:', e);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [token, selectedRadius]);

  const handleRefresh = () => {
    if (!currentLocation) return;
    setRefreshing(true);
    updateServerLocation(currentLocation);
    fetchNearbyUsers(currentLocation);
  };

  const joinAreaChat = async () => {
    if (!currentLocation || joiningRoom) return;
    setJoiningRoom(true);
    try {
      const res = await fetch(`${BACKEND_URL}/api/proximity/join`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          latitude: currentLocation.latitude,
          longitude: currentLocation.longitude,
          radius: selectedRadius,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        router.push({
          pathname: '/(app)/proximity-chat',
          params: { roomId: data.room_id, radius: String(data.radius) },
        });
      }
    } catch (e) {
      console.error('Join area chat error:', e);
    } finally {
      setJoiningRoom(false);
    }
  };

  const startConversation = async (participantId: string) => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/conversations`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ participant_id: participantId }),
      });
      if (res.ok) {
        const data = await res.json();
        router.push(`/(app)/chat/${data.conversation.conversation_id}`);
      }
    } catch (e) {
      console.error('Start conversation error:', e);
    }
  };

  const formatDistance = (meters: number) => {
    if (meters < 1) return '<1m';
    if (meters < 1000) return `${Math.round(meters)}m`;
    return `${(meters / 1000).toFixed(1)}km`;
  };

  const getDistanceColor = (meters: number) => {
    if (meters <= 10) return COLORS.status.success;
    if (meters <= 50) return COLORS.accent.primary;
    if (meters <= 100) return COLORS.status.warning;
    return COLORS.text.secondary;
  };

  const renderAvatar = (user: NearbyUser, size: number = 48) => {
    if (user.avatar) {
      const source = user.avatar.startsWith('data:') || user.avatar.startsWith('http')
        ? { uri: user.avatar }
        : { uri: `data:image/jpeg;base64,${user.avatar}` };
      return (
        <View style={[styles.avatarContainer, { width: size, height: size, borderRadius: size * 0.38 }]}>
          <Image source={source} style={{ width: size, height: size, borderRadius: size * 0.38 }} />
          {user.is_online && <View style={styles.onlineDot} />}
        </View>
      );
    }
    const initials = (user.username || '?').charAt(0).toUpperCase();
    return (
      <View style={[styles.avatarContainer, styles.avatarPlaceholder, { width: size, height: size, borderRadius: size * 0.38 }]}>
        <Text style={[styles.avatarInitials, { fontSize: size * 0.4 }]}>{initials}</Text>
        {user.is_online && <View style={styles.onlineDot} />}
      </View>
    );
  };

  const renderNearbyUser = ({ item }: { item: NearbyUser }) => (
    <TouchableOpacity
      testID={`nearby-user-${item.user_id}`}
      style={styles.userItem}
      onPress={() => startConversation(item.user_id)}
      activeOpacity={0.7}
    >
      {renderAvatar(item)}
      <View style={styles.userInfo}>
        <Text style={styles.username} numberOfLines={1}>{item.username}</Text>
        <Text style={styles.userEmail} numberOfLines={1}>{item.email}</Text>
      </View>
      <View style={styles.distanceContainer}>
        <View style={[styles.distanceBadge, { borderColor: getDistanceColor(item.distance_meters) }]}>
          <Ionicons name="navigate" size={12} color={getDistanceColor(item.distance_meters)} />
          <Text style={[styles.distanceText, { color: getDistanceColor(item.distance_meters) }]}>
            {formatDistance(item.distance_meters)}
          </Text>
        </View>
      </View>
    </TouchableOpacity>
  );

  // Permission denied state
  if (locationPermission === false) {
    return (
      <SafeAreaView style={styles.safeArea} edges={['top']}>
        <View style={styles.header}>
          <Text style={styles.headerTitle}>Nearby</Text>
        </View>
        <View style={styles.centerContainer}>
          <View style={styles.permissionIconContainer}>
            <Ionicons name="location-outline" size={48} color={COLORS.status.error} />
          </View>
          <Text style={styles.permissionTitle}>Location Access Required</Text>
          <Text style={styles.permissionSubtitle}>
            Enable location to discover people near you
          </Text>
          <TouchableOpacity
            testID="enable-location-btn"
            style={styles.enableBtn}
            onPress={async () => {
              const { status } = await Location.requestForegroundPermissionsAsync();
              setLocationPermission(status === 'granted');
            }}
          >
            <Ionicons name="location" size={18} color={COLORS.text.inverse} />
            <Text style={styles.enableBtnText}>Enable Location</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safeArea} edges={['top']}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Nearby</Text>
        {currentLocation && (
          <View style={styles.locationIndicator}>
            <View style={styles.locationDot} />
            <Text style={styles.locationText}>Live</Text>
          </View>
        )}
      </View>

      {/* Radius Selector */}
      <View style={styles.radiusSection}>
        <Text style={styles.radiusLabel}>RADIUS</Text>
        <View style={styles.radiusRow}>
          {RADIUS_OPTIONS.map((option) => (
            <TouchableOpacity
              key={option.value}
              testID={`radius-${option.value}`}
              style={[
                styles.radiusChip,
                selectedRadius === option.value && styles.radiusChipActive,
              ]}
              onPress={() => setSelectedRadius(option.value)}
              activeOpacity={0.7}
            >
              <Text
                style={[
                  styles.radiusChipText,
                  selectedRadius === option.value && styles.radiusChipTextActive,
                ]}
              >
                {option.label}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>

      {/* Users List */}
      {loading ? (
        <View style={styles.centerContainer}>
          <ActivityIndicator size="large" color={COLORS.accent.primary} />
          <Text style={styles.loadingText}>Scanning nearby...</Text>
        </View>
      ) : nearbyUsers.length === 0 ? (
        <View style={styles.centerContainer}>
          <Ionicons name="radio-outline" size={64} color={COLORS.text.tertiary} />
          <Text style={styles.emptyTitle}>No One Nearby</Text>
          <Text style={styles.emptySubtitle}>
            No users found within {formatDistance(selectedRadius)}. Try expanding the radius.
          </Text>
          <TouchableOpacity
            testID="refresh-nearby-btn"
            style={styles.refreshBtn}
            onPress={handleRefresh}
          >
            <Ionicons name="refresh" size={18} color={COLORS.text.inverse} />
            <Text style={styles.refreshBtnText}>Refresh</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <FlatList
          data={nearbyUsers}
          keyExtractor={(item) => item.user_id}
          renderItem={renderNearbyUser}
          contentContainerStyle={styles.listContent}
          showsVerticalScrollIndicator={false}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={handleRefresh}
              tintColor={COLORS.accent.primary}
              colors={[COLORS.accent.primary]}
            />
          }
          ListHeaderComponent={
            <Text style={styles.listHeaderText}>
              {nearbyUsers.length} {nearbyUsers.length === 1 ? 'person' : 'people'} within {formatDistance(selectedRadius)}
            </Text>
          }
        />
      )}

      {/* Floating Join Area Chat Button */}
      {currentLocation && (
        <TouchableOpacity
          testID="join-area-chat-btn"
          style={styles.floatingBtn}
          onPress={joinAreaChat}
          disabled={joiningRoom}
          activeOpacity={0.8}
        >
          {joiningRoom ? (
            <ActivityIndicator size="small" color={COLORS.text.inverse} />
          ) : (
            <>
              <Ionicons name="radio" size={20} color={COLORS.text.inverse} />
              <Text style={styles.floatingBtnText}>Join Area Chat</Text>
            </>
          )}
        </TouchableOpacity>
      )}
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
    justifyContent: 'space-between',
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
  locationIndicator: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: 'rgba(0, 255, 148, 0.1)',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: 'rgba(0, 255, 148, 0.2)',
  },
  locationDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: COLORS.status.online,
  },
  locationText: {
    fontSize: 12,
    fontWeight: '600',
    color: COLORS.status.online,
  },
  radiusSection: {
    paddingHorizontal: 20,
    paddingVertical: 14,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255,255,255,0.06)',
  },
  radiusLabel: {
    fontSize: 10,
    fontWeight: '700',
    color: COLORS.text.tertiary,
    letterSpacing: 1.5,
    marginBottom: 10,
  },
  radiusRow: {
    flexDirection: 'row',
    gap: 10,
  },
  radiusChip: {
    flex: 1,
    height: 40,
    borderRadius: 20,
    backgroundColor: COLORS.bg.secondary,
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: COLORS.border.subtle,
  },
  radiusChipActive: {
    backgroundColor: 'rgba(0, 240, 255, 0.12)',
    borderColor: COLORS.accent.primary,
  },
  radiusChipText: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.text.secondary,
  },
  radiusChipTextActive: {
    color: COLORS.accent.primary,
  },
  centerContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 40,
  },
  loadingText: {
    fontSize: 14,
    color: COLORS.text.secondary,
    marginTop: 12,
  },
  emptyTitle: {
    fontSize: 20,
    fontWeight: '700',
    color: COLORS.text.primary,
    marginTop: 16,
  },
  emptySubtitle: {
    fontSize: 14,
    color: COLORS.text.secondary,
    marginTop: 8,
    textAlign: 'center',
    lineHeight: 20,
  },
  refreshBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: 24,
    height: 48,
    paddingHorizontal: 24,
    borderRadius: 24,
    backgroundColor: COLORS.accent.primary,
  },
  refreshBtnText: {
    fontSize: 14,
    fontWeight: '700',
    color: COLORS.text.inverse,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  listContent: {
    paddingVertical: 8,
  },
  listHeaderText: {
    fontSize: 12,
    fontWeight: '600',
    color: COLORS.text.tertiary,
    paddingHorizontal: 20,
    paddingVertical: 8,
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  userItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 14,
    gap: 14,
  },
  avatarContainer: {
    position: 'relative',
    overflow: 'visible',
  },
  avatarPlaceholder: {
    backgroundColor: COLORS.bg.tertiary,
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: COLORS.border.subtle,
  },
  avatarInitials: {
    color: COLORS.accent.primary,
    fontWeight: '700',
  },
  onlineDot: {
    position: 'absolute',
    bottom: 0,
    right: 0,
    width: 14,
    height: 14,
    borderRadius: 7,
    backgroundColor: COLORS.status.online,
    borderWidth: 2,
    borderColor: COLORS.bg.primary,
  },
  userInfo: {
    flex: 1,
  },
  username: {
    fontSize: 16,
    fontWeight: '600',
    color: COLORS.text.primary,
  },
  userEmail: {
    fontSize: 12,
    color: COLORS.text.secondary,
    marginTop: 2,
  },
  distanceContainer: {
    alignItems: 'flex-end',
  },
  distanceBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 12,
    borderWidth: 1,
    backgroundColor: COLORS.bg.secondary,
  },
  distanceText: {
    fontSize: 13,
    fontWeight: '700',
  },
  permissionIconContainer: {
    width: 88,
    height: 88,
    borderRadius: 32,
    backgroundColor: 'rgba(255, 0, 85, 0.1)',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 16,
    borderWidth: 1,
    borderColor: 'rgba(255, 0, 85, 0.2)',
  },
  permissionTitle: {
    fontSize: 20,
    fontWeight: '700',
    color: COLORS.text.primary,
    marginTop: 8,
  },
  permissionSubtitle: {
    fontSize: 14,
    color: COLORS.text.secondary,
    marginTop: 8,
    textAlign: 'center',
    lineHeight: 20,
  },
  enableBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: 24,
    height: 48,
    paddingHorizontal: 24,
    borderRadius: 24,
    backgroundColor: COLORS.accent.primary,
  },
  enableBtnText: {
    fontSize: 14,
    fontWeight: '700',
    color: COLORS.text.inverse,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  floatingBtn: {
    position: 'absolute',
    bottom: 24,
    left: 20,
    right: 20,
    height: 56,
    borderRadius: 28,
    backgroundColor: COLORS.accent.secondary,
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    gap: 10,
    elevation: 8,
  },
  floatingBtnText: {
    fontSize: 16,
    fontWeight: '700',
    color: COLORS.text.primary,
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
});
