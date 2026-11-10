import { useAuthImage } from "../../hooks/useAuthImage";
import { useLightbox } from "./Lightbox";

interface AuthImageProps {
  /** Relative attachment path, e.g. "/files/<entity>/<file>.jpg". Pass
   * `undefined`/`null` when there is no image and the component renders
   * nothing. */
  path: string | null | undefined;
  alt?: string;
  className?: string;
  style?: React.CSSProperties;
  title?: string;
}

/** <img> for images that live behind the master guard. Clicks open the
 * full-screen lightbox.
 *
 * A plain <img src="/files/..."> cannot carry an Authorization header, so
 * on any non-loopback origin the backend answers 401 and the picture shows
 * broken. This wrapper fetches through useAuthImage (which caches by path,
 * so N rows showing the same icon still issue one request) and hands the
 * resulting blob URL to a normal <img>. */
export function AuthImage({
  path,
  alt = "",
  className,
  style,
  title,
}: AuthImageProps) {
  const url = useAuthImage(path);
  const { open } = useLightbox();
  if (!url) return null;
  return (
    <img
      className={className}
      style={{ cursor: "zoom-in", ...style }}
      src={url}
      alt={alt}
      title={title}
      onClick={(e) => {
        e.stopPropagation();
        open(url, alt);
      }}
    />
  );
}