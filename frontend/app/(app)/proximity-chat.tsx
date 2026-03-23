import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, FlatList,
  TextInput, ActivityIndicator, Image, KeyboardAvoidingView,
  Platform, Keyboard,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';
import { useAuth } from '../../contexts/AuthContext';
import COLORS from '../../constants/colors';

const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

interface ProximityMessage {
  message_id: string;
  room_id: string;
  sender_id: string;
  sender_username: string;
  sender_avatar?: string | null;
  content: string | null;
  image: string | null;
  msg_type: string;
  created_at: string;
  expires_at: string;
}

interface RoomParticipant {
  user_id: string;
  username: string;
  avatar?: string | null;
  is_online: boolean;
}

export default function ProximityChatScreen() {
  const { roomId, radius } = useLocalSearchParams<{ roomId: string; radius: string }>();
  const { user, token, socket } = useAuth();
  const router = useRouter();
  const [messages, setMessages] = useState<ProximityMessage[]>([]);
  const [participants, setParticipants] = useState<RoomParticipant[]>([]);
  const [participantCount, setParticipantCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [inputText, setInputText] = useState('');
  const [sending, setSending] = useState(false);
  const [showParticipants, setShowParticipants] = useState(false);
  const flatListRef = useRef<FlatList>(null);

  // Fetch room info and messages
  useEffect(() => {
    const fetchData = async () => {
      if (!roomId) return;
      try {
        const [roomRes, msgRes] = await Promise.all([
          fetch(`${BACKEND_URL}/api/proximity/room/${roomId}`, {
            headers: { 'Authorization': `Bearer ${token}` },
          }),
          fetch(`${BACKEND_URL}/api/proximity/messages/${roomId}`, {
            headers: { 'Authorization': `Bearer ${token}` },
          }),
        ]);
        if (roomRes.ok) {
          const roomData = await roomRes.json();
          setParticipants(roomData.participants);
          setParticipantCount(roomData.room.participant_count);
        }
        if (msgRes.ok) {
          const msgData = await msgRes.json();
          setMessages(msgData.messages);
        }
      } catch (e) {
        console.error('Fetch proximity data error:', e);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [roomId, token]);

  // Socket.IO: join room and listen
  useEffect(() => {
    if (!socket || !roomId) return;

    socket.emit('join_proximity', { room_id: roomId });

    const onProximityMessage = (msg: ProximityMessage) => {
      if (msg.room_id === roomId) {
        setMessages(prev => {
          if (prev.some(m => m.message_id === msg.message_id)) return prev;
          return [...prev, msg];
        });
      }
    };

    const onUserJoined = (data: any) => {
      if (data.room_id === roomId) {
        setParticipantCount(data.participant_count);
        if (data.user && data.user.user_id !== user?.user_id) {
          setMessages(prev => [...prev, {
            message_id: `sys_join_${Date.now()}`,
            room_id: roomId,
            sender_id: 'system',
            sender_username: 'System',
            sender_avatar: null,
            content: `${data.user.username} joined the area`,
            image: null,
            msg_type: 'system',
            created_at: new Date().toISOString(),
            expires_at: new Date(Date.now() + 86400000).toISOString(),
          }]);
        }
      }
    };

    const onUserLeft = (data: any) => {
      if (data.room_id === roomId) {
        setParticipantCount(data.participant_count);
        if (data.user_id !== user?.user_id) {
          setMessages(prev => [...prev, {
            message_id: `sys_leave_${Date.now()}`,
            room_id: roomId,
            sender_id: 'system',
            sender_username: 'System',
            sender_avatar: null,
            content: `${data.username || 'Someone'} left the area`,
            image: null,
            msg_type: 'system',
            created_at: new Date().toISOString(),
            expires_at: new Date(Date.now() + 86400000).toISOString(),
          }]);
        }
      }
    };

    socket.on('proximity_message', onProximityMessage);
    socket.on('proximity_user_joined', onUserJoined);
    socket.on('proximity_user_left', onUserLeft);

    return () => {
      socket.off('proximity_message', onProximityMessage);
      socket.off('proximity_user_joined', onUserJoined);
      socket.off('proximity_user_left', onUserLeft);
      socket.emit('leave_proximity', { room_id: roomId });
    };
  }, [socket, roomId, user?.user_id]);

  // Auto-scroll
  useEffect(() => {
    if (messages.length > 0) {
      setTimeout(() => flatListRef.current?.scrollToEnd({ animated: true }), 100);
    }
  }, [messages.length]);

  const sendMessage = async (content?: string, image?: string, msgType: string = 'text') => {
    if (sending) return;
    const msgContent = content || inputText.trim();
    if (!msgContent && !image) return;

    setSending(true);
    setInputText('');
    Keyboard.dismiss();

    try {
      if (socket?.connected) {
        socket.emit('send_proximity_message', {
          room_id: roomId,
          content: msgContent || null,
          image: image || null,
          msg_type: msgType,
        });
      } else {
        await fetch(`${BACKEND_URL}/api/proximity/messages`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            room_id: roomId,
            content: msgContent || null,
            image: image || null,
            msg_type: msgType,
          }),
        });
      }
    } catch (e) {
      console.error('Send proximity message error:', e);
    } finally {
      setSending(false);
    }
  };

  const handlePickImage = async () => {
    const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (status !== 'granted') return;
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      quality: 0.5,
      base64: true,
    });
    if (!result.canceled && result.assets[0]?.base64) {
      const base64Data = `data:image/jpeg;base64,${result.assets[0].base64}`;
      await sendMessage(undefined, base64Data, 'image');
    }
  };

  const handleLeaveRoom = async () => {
    try {
      if (socket?.connected) {
        socket.emit('leave_proximity', { room_id: roomId });
      }
      await fetch(`${BACKEND_URL}/api/proximity/leave`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ room_id: roomId }),
      });
    } catch (e) {}
    router.back();
  };

  const formatTime = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const getTimeRemaining = (expiresAt: string) => {
    const diff = new Date(expiresAt).getTime() - Date.now();
    if (diff <= 0) return 'Expired';
    const hrs = Math.floor(diff / 3600000);
    const mins = Math.floor((diff % 3600000) / 60000);
    return `${hrs}h ${mins}m`;
  };

  const renderAvatar = (avatarStr?: string | null, name?: string, size: number = 32) => {
    if (avatarStr) {
      const source = avatarStr.startsWith('data:') || avatarStr.startsWith('http')
        ? { uri: avatarStr }
        : { uri: `data:image/jpeg;base64,${avatarStr}` };
      return <Image source={source} style={{ width: size, height: size, borderRadius: size * 0.38 }} />;
    }
    const initials = (name || '?').charAt(0).toUpperCase();
    return (
      <View style={[styles.avatarSmall, { width: size, height: size, borderRadius: size * 0.38 }]}>
        <Text style={[styles.avatarInitials, { fontSize: size * 0.4 }]}>{initials}</Text>
      </View>
    );
  };

  const renderMessage = ({ item }: { item: ProximityMessage }) => {
    if (item.msg_type === 'system') {
      return (
        <View testID={`msg-${item.message_id}`} style={styles.systemMsgRow}>
          <Text style={styles.systemMsgText}>{item.content}</Text>
        </View>
      );
    }

    const isMine = item.sender_id === user?.user_id;

    return (
      <View testID={`msg-${item.message_id}`} style={[styles.messageRow, isMine ? styles.messageRowMine : styles.messageRowTheirs]}>
        {!isMine && (
          <View style={styles.msgAvatarCol}>
            {renderAvatar(item.sender_avatar, item.sender_username, 28)}
          </View>
        )}
        <View style={[styles.messageBubble, isMine ? styles.bubbleMine : styles.bubbleTheirs]}>
          {!isMine && (
            <Text style={styles.senderName}>{item.sender_username}</Text>
          )}
          {item.image && (
            <Image source={{ uri: item.image }} style={styles.messageImage} resizeMode="cover" />
          )}
          {item.content && (
            <Text style={[styles.messageText, isMine ? styles.textMine : styles.textTheirs]}>
              {item.content}
            </Text>
          )}
          <Text style={styles.messageTime}>{formatTime(item.created_at)}</Text>
        </View>
      </View>
    );
  };

  const renderParticipant = ({ item }: { item: RoomParticipant }) => (
    <View testID={`participant-${item.user_id}`} style={styles.participantItem}>
      {renderAvatar(item.avatar, item.username, 36)}
      <View style={styles.participantInfo}>
        <Text style={styles.participantName}>{item.username}</Text>
        <View style={styles.participantStatusRow}>
          <View style={[styles.statusDot, { backgroundColor: item.is_online ? COLORS.status.online : COLORS.status.offline }]} />
          <Text style={styles.participantStatus}>{item.is_online ? 'Online' : 'Offline'}</Text>
        </View>
      </View>
      {item.user_id === user?.user_id && (
        <Text style={styles.youBadge}>You</Text>
      )}
    </View>
  );

  return (
    <SafeAreaView style={styles.safeArea} edges={['top']}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity testID="prox-chat-back-btn" onPress={handleLeaveRoom} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={24} color={COLORS.text.primary} />
        </TouchableOpacity>
        <View style={styles.headerCenter}>
          <View style={styles.headerTitleRow}>
            <Ionicons name="radio" size={16} color={COLORS.accent.primary} />
            <Text style={styles.headerTitle}>Area Chat</Text>
          </View>
          <Text style={styles.headerSubtitle}>
            {radius || '?'}m radius · {participantCount} {participantCount === 1 ? 'person' : 'people'}
          </Text>
        </View>
        <TouchableOpacity
          testID="show-participants-btn"
          onPress={() => setShowParticipants(!showParticipants)}
          style={styles.participantsBtn}
        >
          <Ionicons name="people" size={22} color={COLORS.accent.primary} />
        </TouchableOpacity>
      </View>

      {/* Expiry Notice */}
      <View style={styles.expiryBanner}>
        <Ionicons name="time-outline" size={14} color={COLORS.status.warning} />
        <Text style={styles.expiryText}>Messages expire after 24 hours</Text>
      </View>

      {/* Participants Panel */}
      {showParticipants && (
        <View style={styles.participantsPanel}>
          <Text style={styles.panelTitle}>IN THIS AREA ({participantCount})</Text>
          <FlatList
            data={participants}
            keyExtractor={(item) => item.user_id}
            renderItem={renderParticipant}
            style={styles.participantsList}
          />
        </View>
      )}

      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={styles.chatContainer}
        keyboardVerticalOffset={0}
      >
        {/* Messages */}
        {loading ? (
          <View style={styles.centerContainer}>
            <ActivityIndicator size="large" color={COLORS.accent.primary} />
          </View>
        ) : (
          <FlatList
            ref={flatListRef}
            data={messages}
            keyExtractor={(item) => item.message_id}
            renderItem={renderMessage}
            contentContainerStyle={styles.messagesList}
            showsVerticalScrollIndicator={false}
            onContentSizeChange={() => flatListRef.current?.scrollToEnd({ animated: false })}
            ListEmptyComponent={
              <View style={styles.emptyChat}>
                <Ionicons name="radio-outline" size={48} color={COLORS.text.tertiary} />
                <Text style={styles.emptyChatText}>Area Chat is Live</Text>
                <Text style={styles.emptyChatSubtext}>
                  Say hi to people nearby! Messages disappear after 24h.
                </Text>
              </View>
            }
          />
        )}

        {/* Input Bar */}
        <View style={styles.inputBar}>
          <TouchableOpacity testID="prox-pick-image-btn" onPress={handlePickImage} style={styles.attachBtn}>
            <Ionicons name="image-outline" size={24} color={COLORS.accent.primary} />
          </TouchableOpacity>
          <View style={styles.inputContainer}>
            <TextInput
              testID="prox-message-input"
              style={styles.messageInput}
              placeholder="Message the area..."
              placeholderTextColor={COLORS.text.tertiary}
              value={inputText}
              onChangeText={setInputText}
              multiline
              maxLength={2000}
            />
          </View>
          <TouchableOpacity
            testID="prox-send-btn"
            onPress={() => sendMessage()}
            style={[styles.sendBtn, (!inputText.trim() || sending) && styles.sendBtnDisabled]}
            disabled={!inputText.trim() || sending}
          >
            {sending ? (
              <ActivityIndicator size="small" color={COLORS.text.inverse} />
            ) : (
              <Ionicons name="send" size={20} color={COLORS.text.inverse} />
            )}
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: COLORS.bg.primary,
  },
  header: {
    height: 64,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 8,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255,255,255,0.06)',
    gap: 4,
  },
  backBtn: {
    width: 44,
    height: 44,
    justifyContent: 'center',
    alignItems: 'center',
  },
  headerCenter: {
    flex: 1,
  },
  headerTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  headerTitle: {
    fontSize: 17,
    fontWeight: '700',
    color: COLORS.text.primary,
  },
  headerSubtitle: {
    fontSize: 12,
    color: COLORS.text.secondary,
    marginTop: 2,
  },
  participantsBtn: {
    width: 44,
    height: 44,
    justifyContent: 'center',
    alignItems: 'center',
  },
  expiryBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: 8,
    backgroundColor: 'rgba(255, 214, 0, 0.06)',
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255, 214, 0, 0.1)',
  },
  expiryText: {
    fontSize: 12,
    color: COLORS.status.warning,
    fontWeight: '500',
  },
  participantsPanel: {
    maxHeight: 200,
    backgroundColor: COLORS.bg.secondary,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255,255,255,0.06)',
    paddingTop: 12,
  },
  panelTitle: {
    fontSize: 10,
    fontWeight: '700',
    color: COLORS.text.tertiary,
    letterSpacing: 1.5,
    paddingHorizontal: 16,
    marginBottom: 8,
  },
  participantsList: {
    paddingHorizontal: 12,
  },
  participantItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 8,
    paddingHorizontal: 4,
    gap: 10,
  },
  participantInfo: {
    flex: 1,
  },
  participantName: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.text.primary,
  },
  participantStatusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    marginTop: 2,
  },
  statusDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },
  participantStatus: {
    fontSize: 11,
    color: COLORS.text.tertiary,
  },
  youBadge: {
    fontSize: 10,
    fontWeight: '700',
    color: COLORS.accent.primary,
    backgroundColor: 'rgba(0,240,255,0.1)',
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 8,
    overflow: 'hidden',
  },
  chatContainer: {
    flex: 1,
  },
  centerContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  messagesList: {
    paddingHorizontal: 12,
    paddingVertical: 16,
    flexGrow: 1,
    justifyContent: 'flex-end',
  },
  messageRow: {
    flexDirection: 'row',
    marginBottom: 6,
    alignItems: 'flex-end',
  },
  messageRowMine: {
    justifyContent: 'flex-end',
  },
  messageRowTheirs: {
    justifyContent: 'flex-start',
  },
  msgAvatarCol: {
    marginRight: 8,
  },
  messageBubble: {
    maxWidth: '78%',
    padding: 10,
    borderRadius: 18,
  },
  bubbleMine: {
    backgroundColor: COLORS.chat.mine_bg,
    borderBottomRightRadius: 4,
    borderWidth: 1,
    borderColor: COLORS.chat.mine_border,
  },
  bubbleTheirs: {
    backgroundColor: COLORS.chat.theirs_bg,
    borderBottomLeftRadius: 4,
    borderWidth: 1,
    borderColor: COLORS.chat.theirs_border,
  },
  senderName: {
    fontSize: 11,
    fontWeight: '700',
    color: COLORS.accent.primary,
    marginBottom: 4,
  },
  messageImage: {
    width: 200,
    height: 200,
    borderRadius: 12,
    marginBottom: 4,
  },
  messageText: {
    fontSize: 15,
    lineHeight: 20,
  },
  textMine: {
    color: COLORS.chat.mine_text,
  },
  textTheirs: {
    color: COLORS.chat.theirs_text,
  },
  messageTime: {
    fontSize: 10,
    color: 'rgba(255,255,255,0.5)',
    marginTop: 4,
    textAlign: 'right',
  },
  systemMsgRow: {
    alignItems: 'center',
    paddingVertical: 8,
  },
  systemMsgText: {
    fontSize: 12,
    color: COLORS.text.tertiary,
    fontStyle: 'italic',
    backgroundColor: COLORS.bg.secondary,
    paddingHorizontal: 16,
    paddingVertical: 6,
    borderRadius: 12,
    overflow: 'hidden',
  },
  emptyChat: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: 60,
  },
  emptyChatText: {
    fontSize: 18,
    fontWeight: '600',
    color: COLORS.text.secondary,
    marginTop: 12,
  },
  emptyChatSubtext: {
    fontSize: 14,
    color: COLORS.text.tertiary,
    marginTop: 4,
    textAlign: 'center',
    paddingHorizontal: 32,
  },
  inputBar: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderTopWidth: 1,
    borderTopColor: 'rgba(255,255,255,0.06)',
    backgroundColor: COLORS.bg.secondary,
    gap: 8,
  },
  attachBtn: {
    width: 44,
    height: 44,
    justifyContent: 'center',
    alignItems: 'center',
  },
  inputContainer: {
    flex: 1,
    minHeight: 44,
    maxHeight: 120,
    borderRadius: 22,
    backgroundColor: COLORS.bg.tertiary,
    paddingHorizontal: 16,
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: COLORS.border.subtle,
  },
  messageInput: {
    color: COLORS.text.primary,
    fontSize: 15,
    paddingVertical: 10,
    maxHeight: 100,
  },
  sendBtn: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: COLORS.accent.primary,
    justifyContent: 'center',
    alignItems: 'center',
  },
  sendBtnDisabled: {
    opacity: 0.4,
  },
  avatarSmall: {
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
});
