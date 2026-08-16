import { useEffect, useState } from "react";

/** Object URL for a File/Blob, recreated whenever the source changes and
 * revoked on cleanup — the browser otherwise leaks one per pick. */
export function useObjectUrl(source: Blob | null | undefined): string | null {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!source) {
      setUrl(null);
      return;
    }
    const objectUrl = URL.createObjectURL(source);
    setUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [source]);

  return url;
}
