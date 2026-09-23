import React, { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import * as ImagePicker from 'expo-image-picker';
import * as DocumentPicker from 'expo-document-picker';

import { AIOrb } from '../components/ambient/IntelligenceOrb';
import { setPendingPapers, type PendingPaper } from '../lib/media/pendingPaper';
import { uriToBase64 } from '../lib/media/toBase64';
import { ScreenBackground } from '../components/layout/ScreenBackground';
import { ErrorState } from '../components/states/ErrorState';
import { phoneTokens } from '../design/colors';
import * as typography from '../design/typography';

/**
 * Scene 5 (v2 frame 05): "add a paper", as a conversation, not a file
 * dialog dropped on the person unannounced — Nura's own line, then three
 * quiet options and an honest way out ("I have no papers today", never
 * forced). A denied camera/library permission gets its own calm line and
 * a way forward (Settings), never a silent no-op.
 */
export default function AddPaper() {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [permissionDenied, setPermissionDenied] = useState<'camera' | 'library' | null>(null);

  const goRead = (papers: PendingPaper[]) => {
    if (papers.length === 0) return;
    setPendingPapers(papers);
    router.push({ pathname: '/reading', params: { label: papers[0].label } });
  };

  const takePhoto = async () => {
    setBusy('photo');
    try {
      const perm = await ImagePicker.requestCameraPermissionsAsync();
      if (!perm.granted) {
        setPermissionDenied('camera');
        return;
      }
      const result = await ImagePicker.launchCameraAsync({ base64: true, quality: 0.8 });
      if (result.canceled || !result.assets[0]?.base64) return;
      const asset = result.assets[0];
      goRead([
        {
          data: asset.base64!,
          contentType: asset.mimeType ?? 'image/jpeg',
          capturedAt: new Date().toISOString(),
          label: 'a photo',
        },
      ]);
    } finally {
      setBusy(null);
    }
  };

  const chooseFile = async () => {
    setBusy('file');
    try {
      const result = await DocumentPicker.getDocumentAsync({ type: ['application/pdf', 'image/*'], multiple: false });
      if (result.canceled || !result.assets[0]) return;
      const asset = result.assets[0];
      const data = await uriToBase64(asset.uri);
      goRead([
        {
          data,
          contentType: asset.mimeType ?? 'application/pdf',
          capturedAt: new Date().toISOString(),
          label: asset.name ?? 'a file',
        },
      ]);
    } finally {
      setBusy(null);
    }
  };

  const chooseManyPhotos = async () => {
    setBusy('many');
    try {
      const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!perm.granted) {
        setPermissionDenied('library');
        return;
      }
      const result = await ImagePicker.launchImageLibraryAsync({ base64: true, allowsMultipleSelection: true, quality: 0.8 });
      if (result.canceled || result.assets.length === 0) return;
      goRead(
        result.assets
          .filter((a) => a.base64)
          .map((a, i) => ({
            data: a.base64!,
            contentType: a.mimeType ?? 'image/jpeg',
            capturedAt: new Date().toISOString(),
            label: `photo ${i + 1}`,
          })),
      );
    } finally {
      setBusy(null);
    }
  };

  if (permissionDenied) {
    return (
      <ScreenBackground style={styles.screen}>
        <ErrorState
          title={permissionDenied === 'camera' ? "Nura can't use the camera yet." : "Nura can't open your photos yet."}
          why="Turn on the permission in your phone's Settings, then come back and try again."
          ctaLabel="Try again"
          onPress={() => setPermissionDenied(null)}
          testID="add-paper-permission-denied"
        />
      </ScreenBackground>
    );
  }

  return (
    <ScreenBackground style={styles.screen}>
      <View style={styles.intro}>
        <AIOrb size="sm" stateOverride="idle" />
        <Text style={styles.introText}>Now show me a paper. A blood test helps the most.</Text>
      </View>

      <Option
        icon="📷"
        title="Take a photo"
        subtitle="Hold it flat, in daylight"
        busy={busy === 'photo'}
        onPress={takePhoto}
        testID="add-paper-camera"
      />
      <Option
        icon="📄"
        title="Choose a file"
        subtitle="A PDF from the hospital or a photo"
        busy={busy === 'file'}
        onPress={chooseFile}
        testID="add-paper-file"
      />
      <Option
        icon="➕"
        title="Choose many photos"
        subtitle="I will read them one by one"
        busy={busy === 'many'}
        onPress={chooseManyPhotos}
        testID="add-paper-many"
      />

      <View style={{ flex: 1 }} />

      <Pressable
        style={styles.noPapers}
        onPress={() => router.replace('/home')}
        accessibilityRole="button"
        accessibilityLabel="I have no papers today"
        testID="add-paper-none"
      >
        <Text style={styles.noPapersText}>I have no papers today</Text>
      </Pressable>
    </ScreenBackground>
  );
}

function Option({
  icon,
  title,
  subtitle,
  busy,
  onPress,
  testID,
}: {
  icon: string;
  title: string;
  subtitle: string;
  busy: boolean;
  onPress: () => void;
  testID: string;
}) {
  return (
    <Pressable
      style={styles.option}
      onPress={onPress}
      disabled={busy}
      accessibilityRole="button"
      accessibilityLabel={`${title}. ${subtitle}`}
      testID={testID}
    >
      <View style={styles.optionIcon}>
        <Text style={{ fontSize: typography.fontSize[18] }}>{icon}</Text>
      </View>
      <View style={{ flex: 1 }}>
        <Text style={styles.optionTitle}>{title}</Text>
        <Text style={styles.optionSubtitle}>{busy ? 'Opening…' : subtitle}</Text>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  screen: { paddingHorizontal: 20, paddingTop: 60, gap: 12 },
  intro: { flexDirection: 'row', alignItems: 'flex-start', gap: 10, marginBottom: 8 },
  introText: { flex: 1, color: phoneTokens.c, fontSize: typography.fontSize[20], fontWeight: '300', lineHeight: 25, marginTop: 6 },
  option: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
    minHeight: 66,
    borderRadius: 22,
    paddingHorizontal: 16,
    backgroundColor: 'rgba(255,255,255,0.10)',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.22)',
  },
  optionIcon: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: 'rgba(255,255,255,0.10)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  optionTitle: { color: phoneTokens.c, fontSize: typography.fontSize[16], fontWeight: '500' },
  optionSubtitle: { color: 'rgba(251,246,240,0.7)', fontSize: typography.fontSize[13], marginTop: 2 },
  noPapers: { minHeight: 56, borderRadius: 999, backgroundColor: 'rgba(255,255,255,0.10)', borderWidth: 1, borderColor: 'rgba(255,255,255,0.22)', alignItems: 'center', justifyContent: 'center', marginBottom: 40 },
  noPapersText: { color: phoneTokens.c, fontSize: typography.fontSize[15.5] },
});
