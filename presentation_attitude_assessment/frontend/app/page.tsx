"use client";

import { useSyncExternalStore } from "react";
import App from "../src/App";
import ModelPreview from "../src/ModelPreview";

function subscribe() {
  return () => {};
}

function previewFromUrl() {
  return new URLSearchParams(window.location.search).get("preview") ===
    "assessment";
}

export default function Page() {
  const preview = useSyncExternalStore<boolean | null>(
    subscribe,
    previewFromUrl,
    () => null,
  );

  if (preview === null) {
    return <main className="p-6" role="status">화면을 준비하고 있어요…</main>;
  }
  return preview ? <ModelPreview /> : <App />;
}
