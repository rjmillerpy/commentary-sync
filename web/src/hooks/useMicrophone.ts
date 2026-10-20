"use client";

/** The microphone the commentator picked: open while the studio is, with
 * its live level for the mic check. Closed on change and on unmount (rule 71). */

import { useCallback, useEffect, useState } from "react";

import { closeMicrophone, listMicrophones, microphoneFailure, openMicrophone, watchLevel } from "@/lib/microphone";

export interface MicrophoneValue {
  devices: MediaDeviceInfo[];
  deviceId: string | null;
  stream: MediaStream | null;
  level: number;
  error: string | null;
  choose(deviceId: string | null): void;
}

export function useMicrophone(): MicrophoneValue {
  const [deviceId, setDeviceId] = useState<string | null>(null);
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [level, setLevel] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let opened: MediaStream | null = null;
    let isCurrent = true;
    openMicrophone(deviceId)
      .then(async (microphone) => {
        opened = microphone;
        if (!isCurrent) return closeMicrophone(microphone);
        setStream(microphone);
        setError(null);
        setDevices(await listMicrophones()); // labelled now that access is granted
      })
      .catch((failure: unknown) => {
        if (isCurrent) setError(microphoneFailure(failure));
      });
    return () => {
      isCurrent = false;
      if (opened !== null) closeMicrophone(opened);
      setStream(null);
    };
  }, [deviceId]);

  useEffect(() => {
    if (stream === null) return;
    const stop = watchLevel(stream, setLevel);
    return () => {
      stop();
      setLevel(0);
    };
  }, [stream]);

  const choose = useCallback((id: string | null) => setDeviceId(id), []);
  return { devices, deviceId, stream, level, error, choose };
}
