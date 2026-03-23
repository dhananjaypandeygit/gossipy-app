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
import { useAuth } from '../../../contexts/AuthContext';
import COLORS from '../../../constants/colors';

const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

interface Message {
  message_id: string;
  conversation_id: string;
  sender_id: string;
  content: string | null;
  image: string | null;
  msg_type: string;
  read: boolean;
  created_at: string;
}

export default function ChatScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { user, token, socket } = useAuth();
  const router = useRouter();
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(true);
  const [inputText, setInputText] = useState('');
  const [sending, setSending] = useState(false);
  const [otherUser, setOtherUser] = useState<any>(null);
  const [isTyping, setIsTyping] = useState(false);
  const flatListRef = useRef<FlatList>(null);
  const typingTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Fetch conversation info and messages
  useEffect(() => {
    const fetchData = async () => {
      try {
        // Fetch conversation details
        const convRes = await fetch(`${BACKEND_URL}/api/conversations`, {
          headers: { 'Authorization': `Bearer ${token}` },
        });
        if (convRes.ok) {
          const convData = await convRes.json();
          const conv = convData.conversations.find((c: any) => c.conversation_id === id);
          if (conv?.other_user) {
            setOtherUser(conv.other_user);
          }
        }

        // Fetch messages
        const msgRes = await fetch(`${BACKEND_URL}/api/conversations/${id}/messages`, {
          headers: { 'Authorization': `Bearer ${token}` },
        });
        if (msgRes.ok) {
          const msgData = await msgRes.json();
          setMessages(msgData.messages);
        }
      } catch (e) {
        console.error('Fetch chat data error:', e);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [id, token]);

  // Socket.IO: join room and listen for messages
  useEffect(() => {
    if (!socket || !id) return;

    socket.emit('join_conversation', { conversation_id: id });

    const onNewMessage = (msg: Message) => {
      if (msg.conversation_id === id) {
        setMessages(prev => {
          if (prev.some(m => m.message_id === msg.message_id)) return prev;
          return [...prev, msg];
        });
        // Mark as read if from other user
        if (msg.sender_id !== user?.user_id) {
          fetch(`${BACKEND_URL}/api/messages/read`, {
            method: 'POST',
            headers: {
              'Authorization': `Bearer ${token}`,
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({ conversation_id: id }),
          }).catch(() => {});
        }
      }
    };

    const onUserTyping = (data: any) => {
      if (data.conversation_id === id && data.user_id !== user?.user_id) {
        setIsTyping(data.is_typing);
        if (data.is_typing) {
          setTimeout(() => setIsTyping(false), 3000);
        }
      }
    };

    const onMessagesRead = (data: any) => {
      if (data.conversation_id === id) {
        setMessages(prev =>
          prev.map(m =>
            m.sender_id === user?.user_id ? { ...m, read: true } : m
          )
        );
      }
    };

    socket.on('new_message', onNewMessage);
    socket.on('user_typing', onUserTyping);
    socket.on('messages_read', onMessagesRead);

    return () => {
      socket.off('new_message', onNewMessage);
      socket.off('user_typing', onUserTyping);
      socket.off('messages_read', onMessagesRead);
      socket.emit('leave_conversation', { conversation_id: id });
    };
  }, [socket, id, user?.user_id, token]);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    if (messages.length > 0) {
      setTimeout(() => {
        flatListRef.current?.scrollToEnd({ animated: true });
      }, 100);
    }
  }, [messages.length]);

  const handleTyping = useCallback((text: string) => {
    setInputText(text);
    if (socket?.connected && id) {
      socket.emit('typing', { conversation_id: id, is_typing: true });
      if (typingTimeoutRef.current) clearTimeout(typingTimeoutRef.current);
      typingTimeoutRef.current = setTimeout(() => {
        socket.emit('typing', { conversation_id: id, is_typing: false });
      }, 2000);
    }
  }, [socket, id]);

  const sendMessage = async (content?: string, image?: string, msgType: string = 'text') => {
    if (sending) return;
    const messageContent = content || inputText.trim();
    if (!messageContent && !image) return;

    setSending(true);
    setInputText('');
    Keyboard.dismiss();

    // Stop typing indicator
    if (socket?.connected) {
      socket.emit('typing', { conversation_id: id, is_typing: false });
    }

    try {
      if (socket?.connected) {
        socket.emit('send_message', {
          conversation_id: id,
          content: messageContent || null,
          image: image || null,
          msg_type: msgType,
        });
      } else {
        // Fallback to REST
        await fetch(`${BACKEND_URL}/api/messages`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            conversation_id: id,
            content: messageContent || null,
            image: image || null,
            msg_type: msgType,
          }),
        });
      }
    } catch (e) {
      console.error('Send message error:', e);
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
      await sendMessage(null, base64Data, 'image');
    }
  };

  const formatTime = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const renderAvatar = (size: number = 36) => {
    if (otherUser?.avatar) {
      const source = otherUser.avatar.startsWith('data:') || otherUser.avatar.startsWith('http')
        ? { uri: otherUser.avatar }
        : { uri: `data:image/jpeg;base64,${otherUser.avatar}` };
      return <Image source={source} style={{ width: size, height: size, borderRadius: size * 0.38 }} />;
    }
    const initials = (otherUser?.username || '?').charAt(0).toUpperCase();
    return (
      <View style={[styles.avatarSmall, { width: size, height: size, borderRadius: size * 0.38 }]}>
        <Text style={[styles.avatarInitials, { fontSize: size * 0.4 }]}>{initials}</Text>
      </View>
    );
  };

  const renderMessage = ({ item, index }: { item: Message; index: number }) => {
    const isMine = item.sender_id === user?.user_id;
    const showAvatar = !isMine && (index === 0 || messages[index - 1]?.sender_id !== item.sender_id);

    return (
      <View
        testID={`message-${item.message_id}`}
        style={[styles.messageRow, isMine ? styles.messageRowMine : styles.messageRowTheirs]}
      >
        {!isMine && showAvatar ? (
          <View style={styles.messageAvatarContainer}>{renderAvatar(28)}</View>
        ) : !isMine ? (
          <View style={{ width: 36 }} />
        ) : null}

        <View style={[styles.messageBubble, isMine ? styles.bubbleMine : styles.bubbleTheirs]}>
          {item.image && (
            <Image
              source={{ uri: item.image }}
              style={styles.messageImage}
              resizeMode="cover"
            />
          )}
          {item.content && (
            <Text style={[styles.messageText, isMine ? styles.messageTextMine : styles.messageTextTheirs]}>
              {item.content}
            </Text>
          )}
          <View style={styles.messageFooter}>
            <Text style={styles.messageTime}>{formatTime(item.created_at)}</Text>
            {isMine && (
              <Ionicons
                name={item.read ? 'checkmark-done' : 'checkmark'}
                size={14}
                color={item.read ? COLORS.accent.primary : COLORS.text.tertiary}
                style={{ marginLeft: 4 }}
              />
            )}
          </View>
        </View>
      </View>
    );
  };

  return (
    <SafeAreaView style={styles.safeArea} edges={['top']}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity
          testID="chat-back-btn"
          onPress={() => router.back()}
          style={styles.backBtn}
        >
          <Ionicons name="arrow-back" size={24} color={COLORS.text.primary} />
        </TouchableOpacity>

        <View style={styles.headerUserInfo}>
          {renderAvatar(36)}
          <View style={styles.headerTextContainer}>
            <Text style={styles.headerUsername} numberOfLines={1}>
              {otherUser?.username || 'Loading...'}
            </Text>
            <Text style={styles.headerStatus}>
              {isTyping ? 'typing...' : otherUser?.is_online ? 'Online' : 'Offline'}
            </Text>
          </View>
        </View>
      </View>

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
            onContentSizeChange={() => {
              flatListRef.current?.scrollToEnd({ animated: false });
            }}
            ListEmptyComponent={
              <View style={styles.emptyChat}>
                <Ionicons name="chatbubble-outline" size={48} color={COLORS.text.tertiary} />
                <Text style={styles.emptyChatText}>No messages yet</Text>
                <Text style={styles.emptyChatSubtext}>Say hello!</Text>
              </View>
            }
          />
        )}

        {/* Typing Indicator */}
        {isTyping && (
          <View style={styles.typingContainer}>
            <View style={styles.typingDots}>
              <View style={styles.typingDot} />
              <View style={[styles.typingDot, { opacity: 0.7 }]} />
              <View style={[styles.typingDot, { opacity: 0.4 }]} />
            </View>
            <Text style={styles.typingText}>{otherUser?.username} is typing</Text>
          </View>
        )}

        {/* Input Bar */}
        <View style={styles.inputBar}>
          <TouchableOpacity
            testID="pick-image-btn"
            onPress={handlePickImage}
            style={styles.attachBtn}
          >
            <Ionicons name="image-outline" size={24} color={COLORS.accent.primary} />
          </TouchableOpacity>

          <View style={styles.inputContainer}>
            <TextInput
              testID="message-input"
              style={styles.messageInput}
              placeholder="Type a message..."
              placeholderTextColor={COLORS.text.tertiary}
              value={inputText}
              onChangeText={handleTyping}
              multiline
              maxLength={2000}
            />
          </View>

          <TouchableOpacity
            testID="send-message-btn"
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
  headerUserInfo: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  headerTextContainer: {
    flex: 1,
  },
  headerUsername: {
    fontSize: 17,
    fontWeight: '700',
    color: COLORS.text.primary,
  },
  headerStatus: {
    fontSize: 12,
    color: COLORS.status.online,
    fontWeight: '500',
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
    marginBottom: 4,
    alignItems: 'flex-end',
  },
  messageRowMine: {
    justifyContent: 'flex-end',
  },
  messageRowTheirs: {
    justifyContent: 'flex-start',
  },
  messageAvatarContainer: {
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
  messageTextMine: {
    color: COLORS.chat.mine_text,
  },
  messageTextTheirs: {
    color: COLORS.chat.theirs_text,
  },
  messageFooter: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'flex-end',
    marginTop: 4,
  },
  messageTime: {
    fontSize: 10,
    color: 'rgba(255,255,255,0.5)',
  },
  typingContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 6,
    gap: 8,
  },
  typingDots: {
    flexDirection: 'row',
    gap: 3,
  },
  typingDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: COLORS.accent.primary,
  },
  typingText: {
    fontSize: 12,
    color: COLORS.text.secondary,
    fontStyle: 'italic',
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
    shadowColor: COLORS.accent.primary,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.3,
    shadowRadius: 4,
    elevation: 4,
  },
  sendBtnDisabled: {
    opacity: 0.4,
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
