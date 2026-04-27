import React, { useState, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, FlatList,
  ActivityIndicator, TextInput, Image,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter, useFocusEffect } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../../contexts/AuthContext';
import COLORS from '../../constants/colors';

const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

interface Conversation {
  conversation_id: string;
  participants: string[];
  last_message: string | null;
  last_message_at: string | null;
  other_user: {
    user_id: string;
    username: string;
    avatar?: string | null;
    is_online?: boolean;
    last_seen?: string | null;
  } | null;
  unread_count: number;
}

export default function ChatsScreen() {
  const { token, socket, getPresence } = useAuth();
  const router = useRouter();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchVisible, setSearchVisible] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [searching, setSearching] = useState(false);

  const fetchConversations = useCallback(async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/conversations`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setConversations(data.conversations);
      }
    } catch (e) {
      console.error('Fetch conversations error:', e);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useFocusEffect(
    useCallback(() => {
      fetchConversations();
    }, [fetchConversations])
  );

  // Listen for new messages to update conversation list
  React.useEffect(() => {
    if (!socket) return;
    const onNewMessage = () => {
      fetchConversations();
    };
    socket.on('new_message', onNewMessage);
    return () => {
      socket.off('new_message', onNewMessage);
    };
  }, [socket, fetchConversations]);

  const searchUsers = async (query: string) => {
    setSearchQuery(query);
    if (query.length < 1) {
      setSearchResults([]);
      return;
    }
    setSearching(true);
    try {
      const res = await fetch(`${BACKEND_URL}/api/users/search?q=${encodeURIComponent(query)}`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setSearchResults(data.users);
      }
    } catch (e) {
      console.error('Search error:', e);
    } finally {
      setSearching(false);
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
        setSearchVisible(false);
        setSearchQuery('');
        setSearchResults([]);
        router.push(`/(app)/chat/${data.conversation.conversation_id}`);
      }
    } catch (e) {
      console.error('Start conversation error:', e);
    }
  };

  const formatTime = (dateStr: string | null) => {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
    if (diffDays === 0) {
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } else if (diffDays === 1) {
      return 'Yesterday';
    } else if (diffDays < 7) {
      return date.toLocaleDateString([], { weekday: 'short' });
    }
    return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
  };

  const formatLastSeen = (userId: string, fallbackLastSeen?: string | null) => {
    const pres = getPresence(userId);
    if (pres.is_online) return 'Online';
    const lastSeen = pres.last_seen || fallbackLastSeen;
    if (!lastSeen) return 'Offline';
    const diff = Date.now() - new Date(lastSeen).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'Just now';
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    if (days === 1) return 'Yesterday';
    return `${days}d ago`;
  };

  const isUserOnline = (userId: string, fallback?: boolean) => {
    const pres = getPresence(userId);
    // If we have real-time presence data, use it; otherwise fall back to API data
    if (pres.is_online) return true;
    if (pres.last_seen) return false; // We got an offline event
    return fallback || false;
  };

  const renderAvatar = (user: any, size: number = 48) => {
    const online = user?.user_id ? isUserOnline(user.user_id, user?.is_online) : false;
    if (user?.avatar) {
      const source = user.avatar.startsWith('data:') || user.avatar.startsWith('http')
        ? { uri: user.avatar }
        : { uri: `data:image/jpeg;base64,${user.avatar}` };
      return (
        <View style={[styles.avatarContainer, { width: size, height: size, borderRadius: size * 0.38 }]}>
          <Image source={source} style={{ width: size, height: size, borderRadius: size * 0.38 }} />
          {online && <View style={styles.onlineDot} />}
        </View>
      );
    }
    const initials = (user?.username || '?').charAt(0).toUpperCase();
    return (
      <View style={[styles.avatarContainer, styles.avatarPlaceholder, { width: size, height: size, borderRadius: size * 0.38 }]}>
        <Text style={[styles.avatarInitials, { fontSize: size * 0.4 }]}>{initials}</Text>
        {online && <View style={styles.onlineDot} />}
      </View>
    );
  };

  const renderConversation = ({ item }: { item: Conversation }) => {
    const otherUserId = item.other_user?.user_id || '';
    const online = otherUserId ? isUserOnline(otherUserId, item.other_user?.is_online) : false;
    const lastSeenText = otherUserId ? formatLastSeen(otherUserId, item.other_user?.last_seen) : '';

    return (
      <TouchableOpacity
        testID={`conversation-${item.conversation_id}`}
        style={styles.conversationItem}
        onPress={() => router.push(`/(app)/chat/${item.conversation_id}`)}
        activeOpacity={0.7}
      >
        {renderAvatar(item.other_user)}
        <View style={styles.conversationInfo}>
          <View style={styles.conversationTop}>
            <Text style={styles.conversationName} numberOfLines={1}>
              {item.other_user?.username || 'Unknown'}
            </Text>
            <Text style={styles.conversationTime}>
              {formatTime(item.last_message_at)}
            </Text>
          </View>
          <View style={styles.conversationBottom}>
            <View style={styles.lastMsgRow}>
              {online ? (
                <View style={styles.presenceIndicator}>
                  <View style={styles.presenceDotSmall} />
                  <Text style={styles.presenceOnlineText}>Online</Text>
                </View>
              ) : lastSeenText ? (
                <Text style={styles.presenceOfflineText}>{lastSeenText}</Text>
              ) : null}
              <Text style={styles.conversationLastMsg} numberOfLines={1}>
                {item.last_message ? `· ${item.last_message}` : 'No messages yet'}
              </Text>
            </View>
            {item.unread_count > 0 && (
              <View style={styles.unreadBadge}>
                <Text style={styles.unreadText}>{item.unread_count}</Text>
              </View>
            )}
          </View>
        </View>
      </TouchableOpacity>
    );
  };

  const renderSearchResult = ({ item }: { item: any }) => (
    <TouchableOpacity
      testID={`search-result-${item.user_id}`}
      style={styles.searchResultItem}
      onPress={() => startConversation(item.user_id)}
      activeOpacity={0.7}
    >
      {renderAvatar(item, 40)}
      <View style={styles.searchResultInfo}>
        <Text style={styles.searchResultName}>{item.username}</Text>
        <Text style={styles.searchResultEmail}>{item.email}</Text>
      </View>
      <Ionicons name="chatbubble-outline" size={20} color={COLORS.accent.primary} />
    </TouchableOpacity>
  );

  return (
    <SafeAreaView style={styles.safeArea} edges={['top']}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Chats</Text>
        <TouchableOpacity
          testID="search-users-btn"
          onPress={() => setSearchVisible(!searchVisible)}
          style={styles.headerBtn}
        >
          <Ionicons name={searchVisible ? 'close' : 'search'} size={24} color={COLORS.accent.primary} />
        </TouchableOpacity>
      </View>

      {/* Search Bar */}
      {searchVisible && (
        <View style={styles.searchSection}>
          <View style={styles.searchInputContainer}>
            <Ionicons name="search" size={18} color={COLORS.text.tertiary} />
            <TextInput
              testID="search-users-input"
              style={styles.searchInput}
              placeholder="Search users..."
              placeholderTextColor={COLORS.text.tertiary}
              value={searchQuery}
              onChangeText={searchUsers}
              autoFocus
              autoCapitalize="none"
            />
          </View>
          {searching && <ActivityIndicator size="small" color={COLORS.accent.primary} style={{ marginTop: 8 }} />}
          {searchResults.length > 0 && (
            <FlatList
              data={searchResults}
              keyExtractor={(item) => item.user_id}
              renderItem={renderSearchResult}
              style={styles.searchResultsList}
            />
          )}
        </View>
      )}

      {/* Conversations List */}
      {loading ? (
        <View style={styles.centerContainer}>
          <ActivityIndicator size="large" color={COLORS.accent.primary} />
        </View>
      ) : conversations.length === 0 ? (
        <View style={styles.centerContainer}>
          <Ionicons name="chatbubble-ellipses-outline" size={64} color={COLORS.text.tertiary} />
          <Text style={styles.emptyTitle}>No Conversations</Text>
          <Text style={styles.emptySubtitle}>Search for users to start chatting</Text>
          <TouchableOpacity
            testID="start-search-btn"
            style={styles.startChatBtn}
            onPress={() => setSearchVisible(true)}
          >
            <Ionicons name="add" size={20} color={COLORS.text.inverse} />
            <Text style={styles.startChatBtnText}>New Chat</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <FlatList
          data={conversations}
          keyExtractor={(item) => item.conversation_id}
          renderItem={renderConversation}
          contentContainerStyle={styles.listContent}
          showsVerticalScrollIndicator={false}
        />
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
  headerBtn: {
    width: 44,
    height: 44,
    justifyContent: 'center',
    alignItems: 'center',
  },
  searchSection: {
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255,255,255,0.06)',
  },
  searchInputContainer: {
    height: 44,
    borderRadius: 22,
    backgroundColor: COLORS.bg.secondary,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 14,
    gap: 10,
    borderWidth: 1,
    borderColor: COLORS.border.subtle,
  },
  searchInput: {
    flex: 1,
    color: COLORS.text.primary,
    fontSize: 15,
  },
  searchResultsList: {
    maxHeight: 200,
    marginTop: 8,
  },
  searchResultItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 10,
    paddingHorizontal: 4,
    gap: 12,
  },
  searchResultInfo: {
    flex: 1,
  },
  searchResultName: {
    fontSize: 15,
    fontWeight: '600',
    color: COLORS.text.primary,
  },
  searchResultEmail: {
    fontSize: 12,
    color: COLORS.text.secondary,
    marginTop: 2,
  },
  centerContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 32,
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
  },
  startChatBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: 24,
    height: 48,
    paddingHorizontal: 24,
    borderRadius: 24,
    backgroundColor: COLORS.accent.primary,
  },
  startChatBtnText: {
    fontSize: 14,
    fontWeight: '700',
    color: COLORS.text.inverse,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  listContent: {
    paddingVertical: 8,
  },
  conversationItem: {
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
  conversationInfo: {
    flex: 1,
  },
  conversationTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  conversationName: {
    fontSize: 16,
    fontWeight: '600',
    color: COLORS.text.primary,
    flex: 1,
    marginRight: 8,
  },
  conversationTime: {
    fontSize: 12,
    color: COLORS.text.tertiary,
  },
  conversationBottom: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: 4,
  },
  lastMsgRow: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
    marginRight: 8,
    gap: 4,
  },
  presenceIndicator: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  presenceDotSmall: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: COLORS.status.online,
  },
  presenceOnlineText: {
    fontSize: 12,
    color: COLORS.status.online,
    fontWeight: '600',
  },
  presenceOfflineText: {
    fontSize: 12,
    color: COLORS.text.tertiary,
  },
  conversationLastMsg: {
    fontSize: 14,
    color: COLORS.text.secondary,
    flex: 1,
  },
  unreadBadge: {
    minWidth: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: COLORS.accent.primary,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 6,
  },
  unreadText: {
    fontSize: 11,
    fontWeight: '700',
    color: COLORS.text.inverse,
  },
});
