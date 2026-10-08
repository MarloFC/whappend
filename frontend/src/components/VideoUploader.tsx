"use client";

import { useRef, useState, useCallback } from "react";
import { Upload, Film, Mic, Image as ImageIcon, AlertCircle } from "lucide-react";

interface Props {
  onUpload: (file: File) => void;
  isUploading: boolean;
}

const SUPPORTED_EXTS = [
  ".mp4", ".mov", ".webm", ".avi", ".mkv",
  ".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac",
  ".jpg", ".jpeg", ".png", ".webp", ".bmp"
];

export default function VideoUploader({ onUpload, isUploading }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isValidMedia = (file: File) => {
    const isMime =
      file.type.startsWith("video/") ||
      file.type.startsWith("audio/") ||
      file.type.startsWith("image/");
    const ext = "." + (file.name.split(".").pop()?.toLowerCase() || "");
    return isMime || SUPPORTED_EXTS.includes(ext);
  };

  const handleFile = useCallback(
    (file: File) => {
      setError(null);
      if (!isValidMedia(file)) {
        setError("Please upload a supported Video, Audio, or Image file (MP4, MP3, WAV, JPG, PNG…)");
        return;
      }
      if (file.size > 500 * 1024 * 1024) {
        setError("File too large. Maximum size is 500 MB.");
        return;
      }
      onUpload(file);
    },
    [onUpload]
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [handleFile]
  );

  return (
    <div className="w-full max-w-2xl mx-auto">
      <div
        className={`uploader-zone ${isDragging ? "uploader-zone--active" : ""} ${isUploading ? "uploader-zone--uploading" : ""}`}
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={onDrop}
        onClick={() => !isUploading && inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          type="file"
          accept="video/*,audio/*,image/*"
          style={{ position: "absolute", width: "1px", height: "1px", opacity: 0, overflow: "hidden", clip: "rect(0,0,0,0)", whiteSpace: "nowrap" }}
          onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }}
        />

        <div className="uploader-icon-group">
          {isUploading ? (
            <div className="spinner" />
          ) : (
            <div className="uploader-multi-icons">
              <span className="icon-pill icon-pill--video" title="Video"><Film size={22} /></span>
              <span className="icon-pill icon-pill--audio" title="Audio"><Mic size={22} /></span>
              <span className="icon-pill icon-pill--image" title="Image"><ImageIcon size={22} /></span>
            </div>
          )}
        </div>

        <h3 className="uploader-title">
          {isUploading ? "Uploading & Analyzing…" : "Drop your media here"}
        </h3>
        <p className="uploader-subtitle">
          {isUploading
            ? "Extracting intelligence from your file"
            : "Video · Audio · Image (MP4, MP3, WAV, JPG, PNG up to 500 MB)"}
        </p>

        {!isUploading && (
          <button className="btn btn-primary" type="button">
            <Upload size={16} />
            Select Media File
          </button>
        )}
      </div>

      {error && (
        <div className="error-banner">
          <AlertCircle size={16} />
          {error}
        </div>
      )}
    </div>
  );
}
